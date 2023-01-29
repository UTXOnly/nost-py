import os
import json
import asyncio
import websockets
import hmac
import hashlib
from time import time
#from ddtrace import tracer
from sqlalchemy import create_engine, Column, String, Integer, JSON, ARRAY, text, cast, Text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker, Query, sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.dialects.postgresql import array
from psycopg2.extras import Json
import logging
from typing import List


logging.basicConfig(level=logging.DEBUG)

# Database setup
DATABASE_URL = os.environ.get("DATABASE_URL")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Event(Base):
    __tablename__ = "event_table"

    id = Column(String, primary_key=True)
    pubkey = Column(String)
    kind = Column(Integer)
    created_at = Column(Integer)
    tags = Column(Text)
    content = Column(String)
    sig = Column(String)
    

    def __init__(self, id, pubkey, kind, created_at, tags:str, content, sig):
        self.id = id
        self.pubkey = pubkey
        self.kind = kind
        self.created_at = created_at
        self.tags = tags
        self.content = content
        self.sig = sig


    @staticmethod
    def to_dict(event):
        return {
            "id": event.id,
            "pubkey": event.pubkey,
            "kind": event.kind,
            "created_at": event.created_at,
            "tags": event.tags,
            "content": event.content,
            "sig": event.sig
        }

#tag_filter = TagFilter()
class EventEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Event):
            return obj.to_dict()
        return json.JSONEncoder.default(self, obj)

Base.metadata.create_all(bind=engine)

def deserialize_tags(tags):
    deserialize_tag = tuple({"type": tag[0], "value": tag[1], "relay": tag[2]} for tag in tags)
    return deserialize_tag


connected_websockets = set()
async def event_handler(websocket, path):
    connected_websockets.add(websocket)
    while True:
        try:
            message = await websocket.recv()
            logging.debug(f"Received event: {message}")
            message = json.loads(message)
            if message[0] == "EVENT":
                event = message[1]
                id = event.get("id")
                pubkey = event.get("pubkey")
                created_at = event.get("created_at")
                kind = event.get("kind")
                tags = event.get("tags")
                content = event.get("content")
                sig = event.get("sig")

                new_event = Event(id=id, pubkey=pubkey, kind=kind, created_at=created_at, tags=tags, content=content, sig=sig)
                logging.debug("Event object created with ID: %s, pubkey: %s, kind: %s, created_at: %s, tags: %s, content: %s, sig: %s", id, pubkey, kind, created_at, tags, content, sig)
                with SessionLocal() as db:
                    try:
                        event_dict = Event.to_dict(new_event)
                        db.add(new_event)
                        db.commit()
                        query = db.query(Event).filter_by(id=id)
                        entered = query.first()
                        logging.debug("Results of querying this entry from db: ID: %s, pubkey: %s, kind: %s, created_at: %s, tags: %s, content: %s, sig: %s", entered.id, entered.pubkey, entered.kind, entered.created_at, entered.tags, entered.content, entered.sig)
    
                    except Exception as e:
                        logging.error("An error occurred while inserting event into database: %s", e)
            elif message[0] == "REQ":
                subscription_id = message[1]
                filters = message[2]
                with SessionLocal() as db:
                    query = db.query(Event)
                    for filter_name, filter_value in filters.items():
                        if filter_name == "ids":
                            query = query.filter(Event.id.in_(filter_value))
                        elif filter_name == "kinds":
                            query = query.filter(Event.kind.in_(filter_value))
                        elif filter_name == "authors":
                            query = query.filter(Event.pubkey.in_(filter_value))
                        elif filter_name == "since":
                            query = query.filter(Event.created_at >= filter_value)
                        elif filter_name == "until":
                            query = query.filter(Event.created_at <= filter_value)
                        elif filter_name == "#e":
                            query = query.filter(Event.tags.contains(filter_value))
                        elif filter_name == "#p":
                            query = query.filter(Event.tags.contains(filter_value))
                        elif filter_name == "limit":
                            limit_value = int(filter_value)
                            query = query.limit(limit_value)
                    events = query.all()
                    #response = json.dumps([event.to_dict() for event in events])
                    response = json.dumps([event.to_dict() for event in events], cls=EventEncoder)

                    await websocket.send(response)

                    try:
                        logging.debug(f"Query: {str(query)}")
                        t = text("SELECT * FROM event_table")
                        result = db.execute(t)
                        #for row in result:
                        #    print(row.column1, row.column2, row.column3)
                        logging.debug("Entries: %s", result)
                        logging.debug("Entries_plain: %s", {result})
                        for row in result:
                            logging.debug("Unfiltered ID: %s Kind: %s Pubkey: %s Since: %s", row.id, row.kind, row.pubkey, row.since)
                        #results = db.query().all()
                        results = query.all()
                        limit_int = query.limit(limit_value)
                        logging.debug("Entries: %s", {str(results)})
                        for row in results:
                            logging.debug("ID: %s Kind: %s Pubkey: %s Since: %s", row.id, row.kind, row.pubkey, row.since)
                        logging.debug("Results of querying the database: {}".format([{'id': r.id, 'pubkey': r.pubkey, 'kind': r.kind, 'created_at': r.created_at, 'tags': r.tags, 'content': r.content, 'sig': r.sig} for r in results]))
                        logging.debug(f"Query {results}")
                        #results_json = [Event.to_dict(r) for r in results]
                        #logging.debug(f"Received event JSON: {results_json}")
                        logging.debug("String test: %s", {str(results)})
                        logging.debug("JSON test: {}".format(json.dumps(results)))
                            #response = json.dumps(results)
                        #response = results
                        await websocket.send(json.dumps(results))
                        logging.debug("Response JSON: ".format(results))
                        
                        logging.debug("Successfully sent events to the client.")
                    except Exception as e:
                        logging.error("An error occurred while querying events: %s", e)
            

        finally:
            #await websocket.close()
            logging.debug("Websocket connection closed.")


if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(
        websockets.serve(event_handler, "0.0.0.0", 8008)
    )
    asyncio.get_event_loop().run_forever()
                    

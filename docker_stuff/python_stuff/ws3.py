import os
import json
import asyncio
import websockets
import hmac
import hashlib
from time import time
#from ddtrace import tracer
from sqlalchemy import create_engine, Column, String, Integer, JSON, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker, Query
from sqlalchemy.ext.declarative import declarative_base


import logging
import json
from typing import List


logging.basicConfig(level=logging.DEBUG)

# Database setup
DATABASE_URL = os.environ.get("DATABASE_URL")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Event(Base):
    __tablename__ = "event"

    id = Column(String, primary_key=True)
    pubkey = Column(String)
    kind = Column(Integer)
    created_at = Column(Integer)
    tags = Column(JSON)
    e_tags = Column(JSON)
    p_tags = Column(JSON)
    content = Column(String)
    sig = Column(String)

    def __init__(self, id, pubkey, kind, created_at, tags, e_tags, p_tags, content, sig):
        self.id = id
        self.pubkey = pubkey
        self.kind = kind
        self.created_at = created_at
        self.tags = tags
        self.e_tags = e_tags
        self.p_tags = p_tags
        self.content = content
        self.sig = sig

    @staticmethod
    def from_dict(event_dict):
        return Event(**event_dict)

    @staticmethod
    def to_dict(event):
        return {
            "id": event.id,
            "pubkey": event.pubkey,
            "kind": event.kind,
            "created_at": event.created_at,
            "tags": event.tags,
            "e_tags": event.e_tags,
            "p_tags": event.p_tags,
            "content": event.content,
            "sig": event.sig
        }
class TagFilter:
    def apply(self, query: Query, tags: List[str], tag_type: str) -> Query:
        if not tags:
            return query
        if tag_type == "#e":
            return query.filter(Event.e_tags.any(lambda tag: tag["value"] in tags))
        elif tag_type == "#p":
            return query.filter(Event.p_tags.any(lambda tag: tag["value"] in tags))

tag_filter = TagFilter()

class Filter:
    def __init__(
            self, 
            ids: "list[str]"=None, 
            kinds: "list[int]"=None, 
            authors: "list[str]"=None, 
            since: int=None, 
            until: int=None, 
            tags: "dict[str, list[str]]"=None,
            limit: int=None) -> None:
        self.ids = ids
        self.kinds = kinds
        self.authors = authors
        self.since = since
        self.until = until
        self.tags = tags
        self.limit = limit

    def apply(self, query: Query) -> Query:
        if self.ids:
            query = query.filter(Event.id.in_(self.ids))
        if self.kinds:
            query = query.filter(Event.kind.in_(self.kinds))
        if self.authors:
            query = query.filter(Event.pubkey.in_(self.authors))
        if self.since:
            query = query.filter(Event.created_at >= self.since)
        if self.until:
            query = query.filter(Event.created_at <= self.until)
        if self.limit:
            query = query.limit(self.limit)
        if self.tags:
            query = tag_filter.apply(query, self.tags.get("#e", []), "#e")
        if self.tags:
            query = tag_filter.apply(query, self.tags.get("#p", []), "#p")
        return query


Base.metadata.create_all(bind=engine)


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

                # Deserialize tags
                deserialized_tags = []
                for tag in tags:
                    tag_type = tag[0]
                    tag_value = tag[1]
                    tag_relay = tag[2]
                    deserialized_tags.append({"type": tag_type, "value": tag_value, "relay": tag_relay})

                new_event = Event(id=id, pubkey=pubkey, kind=kind, created_at=created_at, tags=deserialized_tags, content=content, sig=sig)
                logging.debug("Event object created with ID: %s, pubkey: %s, kind: %s, created_at: %s, tags: %s, content: %s, sig: %s", id, pubkey, kind, created_at, deserialized_tags, content, sig)
                with SessionLocal() as db:
                    try:
                        event_dict = Event.to_dict(new_event)
                        db.execute("INSERT INTO event (id, pubkey, kind, created_at, tags, content, sig) VALUES (:id, :pubkey, :kind, :created_at, :tags, :content, :sig)", event_dict)
                        logging.debug("Inserted event into database: ", event_dict)
                    except Exception as e:
                        logging.error("An error occurred while inserting event into database: %s", e)
                        await websocket.send(json.dumps({"error": str(e)}))
            elif message[0] == "REQ":
                subscription_id = message[1]
                filters = message[2]
                with SessionLocal() as db:
                        query = db.query(Event)
                        for filter_name, filter_value in filters.items():
                            filter_value = filter_value if isinstance(filter_value, (list, tuple, set)) else [filter_value]

                            if filter_name == "ids":
                                query = query.filter(Event.id.in_(filter_value))
                                logging.debug(f"Filtering events by id: {filter_value}")
                            elif filter_name == "kinds":
                                query = query.filter(Event.kind.in_(filter_value))
                                logging.debug(f"Filtering events by kind: {filter_value}")
                            elif filter_name == "authors":
                                query = query.filter(Event.pubkey.in_(filter_value))
                                logging.debug(f"Filtering events by authors: {filter_value}")
                            elif filter_name == "since":
                                query = query.filter(Event.created_at >= filter_value)
                                logging.debug(f"Filtering events created since: {filter_value}")
                            elif filter_name == "until":
                                query = query.filter(Event.created_at <= filter_value)
                                logging.debug(f"Filtering events created until: {filter_value}")
                            elif filter_name == "#e":
                                query = query.filter(text("e_tags->'value' IN (SELECT jsonb_array_elements(:filter_value))").params(filter_value=filter_value))

                                logging.debug(f"Filtering events e tags: {filter_value}")
                            elif filter_name == "#p":
                                query = query.filter(text("p_tags->'value' IN (SELECT jsonb_array_elements(:filter_value))").params(filter_value=filter_value))

                                logging.debug(f"Filtering events p tags: {filter_value}")
                            
                            elif filter_name == "limit":
                                query = query.limit(filter_value)
                                logging.debug(f"Filtering limits: {filter_value}")
                
                        try:
                            results = query.all()
                            logging.debug(f"Received event: {results}")
                            results_json = [Event.to_dict(r) for r in results]
                            logging.debug(f"Received event JSON: {results_json}")
                            response = json.dumps(results_json)
                            await websocket.send(response)
                            logging.debug("Response JSON: {}".format(response))
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
                    

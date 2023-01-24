import os
import json
import asyncio
import websockets
import hmac
import hashlib
from time import time
#from ddtrace import tracer
from sqlalchemy import create_engine, Column, String, Integer, JSON
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
import logging


logging.basicConfig(level=logging.DEBUG)

# Database setup
DATABASE_URL = os.environ.get("DATABASE_URL")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Event(Base):
    __tablename__ = 'event'

    id = Column(String, primary_key=True, index=True)
    pubkey = Column(String, index=True)
    kind = Column(Integer, index=True)
    created_at = Column(Integer, index=True)
    tags = Column(JSON)
    content = Column(String)
    sig = Column(String)

    def __init__(self, id: str, pubkey: str, kind: int, created_at: int, tags: list, content: str, sig: str):
        self.id = id
        self.pubkey = pubkey
        self.kind = kind
        self.created_at = created_at
        self.tags = tags
        self.content = content
        self.sig = sig
    def to_dict(self):
            return {
                "id": self.id,
                "pubkey": self.pubkey,
                "kind": self.kind,
                "created_at": self.created_at,
                "tags": self.tags,
                "content": self.content,
                "sig": self.sig
            }

Base.metadata.create_all(bind=engine)

import json
from typing import List
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
                ids = filters.get("ids", [])
                authors = filters.get("authors", [])
                kinds = filters.get("kinds", [])
                e_tags = filters.get("#e", [])
                p_tags = filters.get("#p", [])
                since = filters.get("since", None)
                until = filters.get("until", None)
                limit = filters.get("limit", None)

                # Use filters to query events from database and send to websocket
                with SessionLocal() as db:
                    query = db.query(Event)
                    if ids:
                        query = query.filter(Event.id.in_(ids))
                    if authors:
                        query = query.filter(Event.pubkey.in_(authors))
                    #if kinds:
                    #    query = query.filter(Event.kinds.in_(kinds))
                    ##if e_tags:
                    #    query = query.filter(Event.tags.any(and_(EventTag.type == "e", EventTag.value.in_(e_tags))))
                    #if p_tags:
                    #    query = query.filter(Event.tags.any(and_(EventTag.type == "p", EventTag.value.in_(p_tags))))
                    #if since:
                    #    query = query.filter(Event.created_at >= since)
                    if until:
                        query = query.filter(Event.created_at <= until)
                    if limit:
                        query = query.limit(limit)
                    try:
                        results = query.all()
                        logging.debug(f"Received event: {results}")
                        results_json = [Event.to_dict(r) for r in results]
                        logging.debug(f"Received event JSON: {results_json}")
                        response = json.dumps(results_json)
                        await websocket.send(response)
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
                    

import os
import json
import asyncio
import websockets
import hmac
import hashlib
from time import time
#from ddtrace import tracer
from sqlalchemy import create_engine, Column, String, Integer, JSON, Query
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
        if self.tags:
            query = query.filter(Event.e_tags.in(lambda tag: tag["value"] in self.tags))
        if self.p_tags:
            query = query.filter(Event.p_tags.any(lambda tag: tag["value"] in self.p_tags))
        if self.limit:
            query = query.limit(self.limit)
        return query

class TagFilter:
    def apply(self, query: Query, tags: List[str]) -> Query:
        if not tags:
            return query
        return query.filter(Event.e_tags.any(lambda tag: tag["value"] in tags))

tag_filter = TagFilter()




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
                with SessionLocal() as db:
                    query = db.query(Event)
                    for filter in filters:
                        query = filter.apply(query)
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
                    

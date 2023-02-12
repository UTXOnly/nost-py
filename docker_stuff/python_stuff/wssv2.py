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


connected_websockets = set()
async def event_handler(websocket, path):
    connected_websockets.add(websocket)
    while True:
        try:
            message = await websocket.recv()
            logging.debug(f"Received message: {message}")
            message = json.loads(message)
            if message["type"] == "REQ":
                subscription_id = message["subscription_id"]
                filters = message["filters"]
                with SessionLocal() as db:
                    events = db.query(Event).filter(Event.id.in_(filters["ids"]), Event.pubkey.in_(filters["authors"]), Event.kind.in_(filters["kinds"]),Event.created_at>= filters["since"],Event.created_at<= filters["until"], Event.subscription_id == subscription_id).all()
                event_json = json.dumps({"events": events})
                await websocket.send(event_json)
            
            elif message["type"] == "EVENT":
                event = message["event"]
                pubkey = event.get("pubkey")
                kind = event.get("kind")
                created_at = event.get("created_at")
                tags = event.get("tags")
                content = event.get("content")
                id = event.get("id")
                sig = event.get("sig")
                subscription_id = message["subscription_id"]
                event_data = json.dumps([pubkey, created_at, kind, tags, content], sort_keys=True)
                computed_id = hashlib.sha256(event_data.encode()).hexdigest()
                new_event = Event(id=id, pubkey=pubkey, kind=kind, created_at=created_at, tags=tags, content=content, sig=sig, subscription_id = subscription_id)
                with SessionLocal() as db:
                    try:
                        event_dict = Event.to_dict(new_event)
                        db.execute("INSERT INTO event (id, pubkey, kind, created_at, tags, content, sig, subscription_id) VALUES (:id, :pubkey, :kind, :created_at, :tags, :content, :sig, :subscription_id)", event_dict)
                        db.commit()
                        logging.debug(f"Event submitted to database: {event_dict}")
                        await websocket.send(json.dumps({"message": "Event received and processed"}))
                    except IntegrityError as e:
                        db.rollback()
                        logging.error(e)
                        await websocket.send(json.dumps({"error": e}))
                        await websocket.close()
               
        except Exception as e:
            logging.error(e)
            break





if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(
        websockets.serve(event_handler, "0.0.0.0", 8008)
    )
    asyncio.get_event_loop().run_forever()


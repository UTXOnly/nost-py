import os
import json
import hmac
import hashlib
import logging
import asyncio
import websockets
from sqlalchemy.orm import Session
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import create_engine, Column, String, Integer, JSON, ARRAY, text, cast, Text

def calc_event_id(public_key:str, created_at:int, kind_number:int, tags:list, content:str) -> str:
    """
    This function calculates the event id using the provided information
    """
    # do some computation to calculate event id
    event_id = hashlib.sha256((str(public_key) + str(created_at) + str(kind_number) + str(tags) + str(content)).encode()).hexdigest()
    return event_id

class Event:
    __tablename__ = "event_table"
    id = Column(String, primary_key=True)
    pubkey = Column(String)
    kind = Column(Integer)
    created_at = Column(Integer)
    tags = Column(Text)
    content = Column(String)
    sig = Column(String)
    def __init__(self, pubkey:str, created_at:int, kind:int, tags:list, content:str):
        self.pubkey = pubkey
        self.created_at = created_at
        self.kind = kind
        self.tags = tags
        self.content = content
    def calc_id(self):
        return calc_event_id(
            public_key=self.pubkey,
            created_at=self.created_at,
            kind_number=self.kind,
            tags=[tag.serialize() for tag in self.tags],
            content=self.content,
        )
    def __str__(self):
        return f"Event(id={self.id}, pubkey={self.pubkey}, kind={self.kind}, created_at={self.created_at}, tags={self.tags}, content={self.content}, sig={self.sig})"
    
    def get_tags_keys(self, tag_type: str):
        return set(tag.key for tag in self.tags if tag.type == tag_type)
    @property
    def e_tags(self):
        return self.get_tags_keys("e")
    @property
    def p_tags(self):
        return self.get_tags_keys("p")
    
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
            "content": event.content,
            "sig": event.sig
        }

def save_event(received_data: dict):
    event = Event.from_dict(received_data)
    session = Session()
    session.add(event)
    session.commit()
    session.close()

def notify_connected_clients(received_data: dict):
    event = Event.from_dict(received_data)
    for ws in connected_websockets:
        ws.send(event.to_json())
connected_websockets = set()
async def event_handler(websocket, path):
    connected_websockets.add(websocket)
    while True:
        try:
            event_data = await websocket.recv()
            logging.debug(f"Received event: {event_data}")
            received_data = json.loads(event_data)
            logging.debug(f"event_data is: {received_data}")
            #           # Verify the signature of the event
            ###secret_key = "your_secret_key"
            ###signature = received_data["sig"]
            ###del received_data["sig"]
            ##message = json.dumps(received_data)
            ##computed_signature = hmac.new(secret_key.encode(), message.encode(), hashlib.sha256).hexdigest()
            #if not hmac.compare_digest(computed_signature, signature):
            #    raise ValueError("Invalid signature")
            


            if event_data[0] == "EVENT":
                event = event_data[1]
                id = event.get("id")
                pubkey = event.get("pubkey")
                created_at = event.get("created_at")
                kind = event.get("kind")
                tags = event.get("tags")
                content = event.get("content")
                sig = event.get("sig")

            # Save the event to the database
            save_event(received_data)
            
            # Notify connected websockets of the new event
            notify_connected_clients(received_data)
        except Exception as e:
            logging.exception(e)
            break
        finally:
            connected_websockets.remove(websocket)
    
DATABASE_URL = os.environ.get("DATABASE_URL")
engine = create_engine(DATABASE_URL)

if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(
        websockets.serve(event_handler, "0.0.0.0", 8008)
    )
    asyncio.get_event_loop().run_forever()


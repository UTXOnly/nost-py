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

DATABASE_URL = os.environ.get("DATABASE_URL")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

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
    def __init__(self,id:str, pubkey:str, created_at:int, kind:list[int], tags:list, content:str):
        self.id = id
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


#def save_event(received_data: dict):
#    
#    event = received_data
#    session = Session()
#    logging.debug("Adding event to session")
#    session.add(event)
#    logging.debug("Committing event to session")
#    session.commit()
#    #logging.debug("Closing session")
#    #session.close()

#def notify_connected_clients(received_data: dict):
#    event = Event.from_dict(received_data)
#    for ws in connected_websockets:
#        logging.debug("Sending event to connected websockets")
#        ws.send(event.to_json())

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
            ##commented_signature = hmac.new(secret_key.encode(), message.encode(), hashlib.sha256).hexdigest()
            #if not hmac.compare_digest(computed_signature, signature):
            #    raise ValueError("Invalid signature")
            
            if received_data[0] == "EVENT":
                event = received_data[1]
                id = event.get("id")
                pubkey = event.get("pubkey")
                created_at = event.get("created_at")
                kind = event.get("kind")
                tags = event.get("tags")
                content = event.get("content")
                sig = event.get("sig")

                new_event = Event(id=id, pubkey=pubkey, kind=kind, created_at=created_at, tags=tags, content=content, sig=sig)
                
            # Save the event to the database
                #save_event(new_event_dict)
                with SessionLocal() as db:
                    try:
                        event_dict = Event.to_dict(new_event)
                        #db.execute("INSERT INTO event (id, pubkey, kind, created_at, tags, content, sig) VALUES (:id, :pubkey, :kind, :created_at, :tags, :content, :sig)", event_dict)
                        db.execute(text("INSERT INTO event_table (id, pubkey, kind, created_at, tags, content, sig) VALUES (:id, :pubkey, :kind, :created_at, :tags, :content, :sig)"), event_dict)

                        logging.debug("Inserted event into database: %s", event_dict)
                        query = db.query(Event).filter_by(id=id)
                        entered = query.first()
                        logging.debug("Results of querying this entry from db: ID: %s, pubkey: %s, kind: %s, created_at: %s, tags: %s, content: %s, sig: %s", entered.id, entered.pubkey, entered.kind, entered.created_at, entered.tags, entered.content, entered.sig)
                    except Exception as e:
                        logging.error("An error occurred while inserting event into database: %s", e)
                        await websocket.send(json.dumps({"error": str(e)}))
            
            # Notify connected websockets of the new event
            #notify_connected_clients(received_data)
        except Exception as e:
            logging.exception(e)
            break
        finally:
            #await websocket.close()
            logging.debug("Websocket connection closed.")

if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(
        websockets.serve(event_handler, "0.0.0.0", 8008)
    )
    asyncio.get_event_loop().run_forever()

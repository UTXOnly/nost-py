import asyncio
import json
import uuid
import sys
import websockets
from time import time
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List
import logging

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(levelname)s %(message)s', datefmt='%Y-%m-%d %H:%M:%S', handlers=[logging.StreamHandler(sys.stdout)])

def content_section():
    content = "This is a test from nost-py, a relay written in Python. If you are seeing this, I am sucessuflly storing events and serving client quieries"
    return content

class RelayWorker:
    async def set_port(self, port):
        self.port = port

class DBWorker:
    async def set_port(self, port, with_worker):
        self.port = port
        self.with_worker = with_worker

class EventWorker:
    async def set_port(self, port):
        self.port = port

relay_worker = RelayWorker()
db_worker = DBWorker()
event_worker = EventWorker()

def normalize_relay_url(relay_url: str) -> str:
    """
    Normalize a relay URL by removing trailing slashes and converting it to lowercase.

    :param relay_url: The relay URL to normalize.
    :return: The normalized relay URL.
    """
    return relay_url.rstrip("/").lower()


def methods(action: str, id: str, relays: List[str], settings: Dict[str, any]) -> Dict[str, any]:
    if action == "getRelayStatus":
        relay_work = {
            "action": "status",
        }
        ticket = {
            "id": id,
            "relayWork": relay_work,
            "type": "status",
        }
        return ticket
    elif action == "publish":
        relay_work = {
            "action": "publish",
            "relays": relays,
        }
        event = settings.get("event") 
        if not event: 
            logging.error("event data is missing")
            return 
        content = content_section()
        db_work = {
            "action": "save",
        }
        ticket = {
            "id": id,
            "relayWork": relay_work,
            "dbWork": db_work,
            "event": event,
            "content": content,
            "type": "publish",
        }
        return ticket


async def main():
    id = str(uuid.uuid4())
    settings = {"event": "event data", "authors": ["npub1g5pm4gf8hh7skp2rsnw9h2pvkr32sdnuhkcx9yte7qxmrg6v4txqqudjqv"]}
    relays = ["nostr.bostonbtc.com", "nostr.dojotunnel.online"]
    content = content_section()
    settings["content"] = content
    ticket = methods("publish", id, relays, settings)
    if not ticket:
        return
    async with websockets.connect('ws://localhost:8008') as websocket:
        logging.debug("Sending Ticket: %s", json.dumps(ticket))
        await websocket.send(json.dumps(ticket))
        response = await websocket.recv()
        logging.debug("Response: %s", response)
        if response == '{"message": "Event received and processed"}':
            logging.debug("Event processed successfully")
            return
        else:
            logging.debug("Event processing failed")

asyncio.run(main())




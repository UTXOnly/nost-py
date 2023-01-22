import asyncio
import json
import uuid
import websockets
from time import time
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List

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
            "event": settings["event"],
        }
        db_work = {
            "action": "save",
        }
        ticket = {
            "id": id,
            "relayWork": relay_work,
            "dbWork": db_work,
            "type": "publish",
        }
        return ticket
    elif action == "getFeed":
        filter = {}
        if "authors" in settings and settings["authors"]:
            filter["authors"] = settings["authors"]
        relays = settings.get("relays", [])
        relays = [normalize_relay_url(relay) for relay in relays]

        relay_work = {
            "action": "get",
            "sub_name": "events",
            "filter": filter,
            "relays": relays
        }
        db_work = {
            "action": "save",
        }
        ticket = {
            "id": id,
            "relay_work": relay_work,
            "db_work": db_work,
            "type": "call"
        }
        return ticket

relay_queue = asyncio.Queue()
db_queue = asyncio.Queue()
event_queue = asyncio.Queue()


async def main():
    id = str(uuid.uuid4())
    settings = {"authors": ["npub1g5pm4gf8hh7skp2rsnw9h2pvkr32sdnuhkcx9yte7qxmrg6v4txqqudjqv"]}
    ticket = methods("getEvents", id, [], settings)
    async with websockets.connect('ws://localhost:8008') as websocket:
        await websocket.send(json.dumps(ticket))
        response = await websocket.recv()
        print(response)

asyncio.run(main())






import asyncio
import json
import websockets
import random
import string
import hmac
import hashlib
from time import time
import logging
import sys

logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)


base_url = 'ws://172.20.0.2:8008'

def create_random_event():
    # Generate random pubkey, kind, and payload values
    pubkey = "npub1g5pm4gf8hh7skp2rsnw9h2pvkr32sdnuhkcx9yte7qxmrg6v4txqqudjqv"
    kind = 1 #random.randint(0, 10)
    created_at = int(time())
    tags = []
    content = "This is a test from nost-py, a relay written in Python. If you are seeing this, I am sucessuflly storing events and serving client quieries"

    event = {
        "pubkey": pubkey,
        "kind": kind,
        "created_at": created_at,
        "tags": tags,
        "content": content
    }
    event_data = json.dumps([pubkey, created_at, kind, tags, content], sort_keys=True)
    print(event_data)

    event_id = hashlib.sha256(event_data.encode()).hexdigest()
    print(event_id)
    
    # decode the pubkey string before using it in the hmac
    
    sig = hmac.new(pubkey.encode(), event_data.encode(), hashlib.sha256).hexdigest()
    print(sig)

    event["id"] = event_id
    event["sig"] = sig
    return event

# Create the event to be posted
#event = create_random_event()

async def post_event(note: dict, subscription_id: str):
    """
    Sends a message to the websocket server with the provided nostr note and subscription ID
    """
    retries = 0
    max_retries = 5
    retry_interval = 5  # seconds
    while retries < max_retries:
        try:
            async with websockets.connect(base_url) as websocket:
                logging.debug(f"Connected to {base_url}")
                async def ping():
                    while True:
                        await asyncio.sleep(30)
                        await websocket.ping()
                pinger = asyncio.create_task(ping())
                try:
                    event_data = json.dumps({"EVENT": note, "subscription_id": subscription_id})
                    await websocket.send(event_data)
                    response = await websocket.recv()
                    logging.debug(response)
                    pinger.cancel()
                    return json.loads(response)
                finally:
                    pinger.cancel()
                    await websocket.close()
        except websockets.exceptions.ConnectionClosedError as e:
            retries += 1
            logging.debug(f"Error: {e}. Retrying...")
            await asyncio.sleep(retry_interval)
    logging.error("Error: Could not connect to websocket. Giving up.")


run_once = True

async def main():
    global run_once
    while run_once:
        event = create_random_event()
        post_response = await post_event(note=event, subscription_id=str(3))
        print(post_response)
        run_once = False

if __name__ == "__main__":
    asyncio.run(main())
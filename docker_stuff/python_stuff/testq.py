import asyncio
import json
import websockets
import logging
import sys

logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)

base_url = 'ws://172.20.0.2:8008'

async def query_events():
    for i in range(3):
        try:
            async with websockets.connect(base_url) as websocket:
                filters = [
                    {
                        #"ids": [str("e9ee06475d048310f8a2b12dd1fd388d1459b05bae4043633ca0340c59329b3c")],
                        "authors": ["04fba1b83137d7d0870027371e2ccea297aa3f11770a69e60e262bab143e8eb16b1945f7817426578d999a5ebcd3f233df01b00e107b74e026ab8534dca63b75c8"],
                        #"kinds": [1, 4],
                        #"#e": [str("0xabcdef")],
                        #"#p": [str("npub1g5pm4gf8hh7skp2rsnw9h2pvkr32sdnuhkcx9yte7qxmrg6v4txqqudjqv")],
                        "since": 1600000000,
                        "until": 1600001000,
                        "limit": 10
                    }
                ]

                query_message = json.dumps({"REQ": "query", "subscription_id": str(3), "filters": filters})
                await websocket.send(query_message)
                response = await websocket.recv()
                await websocket.close()
                return response
        except websockets.exceptions.ConnectionClosedError as e:
            print(f"Error: {e}. Retrying...")
            await asyncio.sleep(1)
    print("Error: Could not connect to websocket. Giving up.")

async def main():
    result = await query_events()
    print(result)

if __name__ == "__main__":
    asyncio.run(main())

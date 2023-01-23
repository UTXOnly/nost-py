import json
import hashlib
import ecdsa
import time
import logging
from websocket import create_connection

logging.basicConfig(level=logging.DEBUG)

# Create a mock event
def create_mock_event(pubkey, privkey):
    event = {}
    event["pubkey"] = pubkey
    event["created_at"] = int(time.time())
    event["kind"] = 0
    event["tags"] = []
    event["content"] = "This is a test from nost-py, a simple containerized Nostr relay written in Python. If you are seeing this, I am sucessuflly storing events and serving client quieries https://nostr.build/i/nostr.build_7211.jpg"
    event_data = json.dumps([event["pubkey"], event["created_at"], event["kind"], event["tags"], event["content"]], separators=(',',':')).encode('utf-8')
    event["id"] = hashlib.sha256(event_data).hexdigest()
    event["sig"] = privkey.sign_deterministic(event_data, hashfunc=hashlib.sha256).hex()
    return event


hex_string = "6e7365633167683777737a786839707171707277787170306c33776c663475356a72743061796870713539366a766d36653930757963796b733778736865710a"

# convert hex string to bytes
bytes_data = bytes.fromhex(hex_string)

# create SHA256 hash object
hash_object = hashlib.sha256()

# update the hash object with the bytes data
hash_object.update(bytes_data)

# get the 32-bit hex string representation of the hash
print(hash_object.hexdigest())

# convert hex string to bytes
privkey_bytes = bytes.fromhex(hash_object.hexdigest())

# Create the signing key
sk = ecdsa.SigningKey.from_string(privkey_bytes, curve=ecdsa.SECP256k1)

# Get the public key
vk = sk.verifying_key
pubkey = '04' + vk.to_string().hex()

# Connect to WebSocket server
ws = create_connection("ws://localhost:8008/")

# Send the event to the server
event = create_mock_event(pubkey, sk)
ws.send(json.dumps({"EVENT": event}))


ws.close()


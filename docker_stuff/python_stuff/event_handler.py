import os
import json
import logging
from logging.handlers import RotatingFileHandler
import inspect
from typing import List, Dict, Any, Optional

import uvicorn
import secp256k1
from ddtrace import tracer
from datadog import initialize, statsd
import redis
from sqlalchemy import create_engine, Column, String, Integer, JSON, desc
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, class_mapper
from sqlalchemy.exc import SQLAlchemyError
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse

options: Dict[str, Any] = {
    'statsd_host': '172.28.0.5',
    'statsd_port': 8125
}

initialize(**options)

tracer.configure(hostname='172.28.0.5', port=8126)
redis_client: redis.Redis = redis.Redis(host='172.28.0.6', port=6379)

logger: logging.Logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

log_file: str = './logs/event_handler.log'
handler: RotatingFileHandler = RotatingFileHandler(log_file, maxBytes=1000000, backupCount=5)
formatter: logging.Formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

DATABASE_URL: str = os.environ.get("DATABASE_URL")

engine: create_engine = create_engine(DATABASE_URL, echo=True)
Base: declarative_base = declarative_base()

class Event(Base):
    __tablename__: str = 'event'

    id: Column = Column(String, primary_key=True, index=True)
    pubkey: Column = Column(String, index=True)
    kind: Column = Column(Integer, index=True)
    created_at: Column = Column(Integer, index=True)
    tags: Column = Column(JSON)
    content: Column = Column(String)
    sig: Column = Column(String)

    def __init__(self, id: str, pubkey: str, kind: int, created_at: int, tags: List, content: str, sig: str) -> None:
        self.id = id
        self.pubkey = pubkey
        self.kind = kind
        self.created_at = created_at
        self.tags = tags
        self.content = content
        self.sig = sig

logger.info("Creating database metadata")
Base.metadata.create_all(bind=engine)
app: FastAPI = FastAPI()

Session: sessionmaker = sessionmaker(bind=engine)
session: Session = Session()

async def verify_signature(event_id: str, pubkey: str, sig: str) -> bool:
    try:
        pub_key: secp256k1.PublicKey = secp256k1.PublicKey(bytes.fromhex("02" + pubkey), True)
        result: bool = pub_key.schnorr_verify(bytes.fromhex(event_id), bytes.fromhex(sig), None, raw=True)
        if result:
            logger.info(f"Verification successful for event: {event_id}")
        else:
            logger.error(f"Verification failed for event: {event_id}")
        return result
    except (ValueError, TypeError, secp256k1.Error) as e:
        logger.error(f"Error verifying signature for event {event_id}: {e}")
        return False

@app.post("/new_event")
async def handle_new_event(request: Request) -> JSONResponse:
    event_dict: Dict[str, Any] = await request.json()
    pubkey: str = event_dict.get("pubkey", "")
    kind: int = event_dict.get("kind", 0)
    created_at: int = event_dict.get("created_at", 0)
    tags: List = event_dict.get("tags", [])
    content: str = event_dict.get("content", "")
    event_id: str = event_dict.get("id", "")
    sig: str = event_dict.get("sig", "")

    if not await verify_signature(event_id, pubkey, sig):
        raise HTTPException(status_code=401, detail="Signature verification failed")

    try:
        delete_message: Optional[str] = None
        if kind in {0, 3}:
            delete_message = f"Deleting existing metadata for pubkey {pubkey}"
            session.query(Event).filter_by(pubkey=pubkey, kind=kind).delete()
            statsd.decrement('nostr.event.added.count', tags=["func:new_event"])
            statsd.increment('nostr.event.deleted.count', tags=["func:new_event"])

        existing_event: Optional[Event] = session.query(Event).filter_by(id=event_id).scalar()
        if existing_event is not None:
            #["OK", "b1a649ebe8...", true, "duplicate: already have this event"]
            raise HTTPException(status_code=409, detail=f"Event with ID {event_id} already exists")

        new_event: Event = Event(
            id=event_id,
            pubkey=pubkey,
            kind=kind,
            created_at=created_at,
            tags=tags,
            content=content,
            sig=sig
        )

        session.add(new_event)
        session.commit()
        response = {'event': "OK", 'subscription_id': "n0stafarian419", 'results_json': "true"}
        statsd.increment('nostr.event.added.count', tags=["func:new_event"])
        return JSONResponse(content=response, status_code=200)

    except SQLAlchemyError as e:
        logger.exception(f"Error saving event: {e}")
        raise HTTPException(status_code=500, detail="Failed to save event to database")

    finally:
        if delete_message:
            logger.debug(delete_message.format(pubkey=pubkey))

def serialize(model: Event) -> Dict[str, Any]:
    # Helper function to convert an SQLAlchemy model instance to a dictionary
    columns: List[str] = [c.key for c in class_mapper(model.__class__).columns]
    return dict((c, getattr(model, c)) for c in columns)

async def event_query(filters: str) -> List[Dict[str, Any]]:
    serialized_events: List[Dict[str, Any]] = []
    try:
        results: List[Dict[str, Any]] = json.loads(filters)
        logger.debug(f"Filter variable is: {filters}")
        list_index: int = 0
        index: int = 2
        output_list: List[Dict[str, Any]] = []

        for request in results:
            extracted_dict: Dict[str, Any] = results[list_index][str(index)]
            logger.debug(f"Extracted Dictionary is: {extracted_dict}")
            if isinstance(request, dict):
                output_list.append(extracted_dict)
                logger.debug(f"Results variable is: {request}")
            redis_get: str = str(results[list_index][str(index)])

            try:
                cached_result: bytes = redis_client.get(redis_get)
                logger.debug(f"Cached resuts = {cached_result}")
                if cached_result == "b'[]'":
                    cached_result = None
                    return serialized_events
                index += 1
                list_index += 1
                # b'[]' is the problem response
                if cached_result:
                    query_result: bytes = cached_result
                    query_result_utf8: str = query_result.decode('utf-8')
                    logger.debug(f"Query results UTF 8 = {query_result_utf8}")
                    query_result_cleaned: str = query_result_utf8[2:-1].strip()
                    logger.debug(f"Query result CLEANED = {query_result_cleaned}")
                    logger.debug(f"Query result found in cache. ({inspect.currentframe().f_lineno})")
                    if len(query_result_cleaned) > 2:
                        statsd.increment('nostr.event.found.redis.count', tags=["func:event_query"])
                        serialized_events.append(query_result_cleaned)

                else:
                    try:
                        query = session.query(Event)
                        conditions: Dict[str, Any] = {
                            "authors": lambda x: Event.pubkey.in_(x),
                            "kinds": lambda x: Event.kind.in_(x),
                            "#e": lambda x: Event.tags.in_(x),
                            "#p": lambda x: Event.tags.in_(x),
                            "#d": lambda x: Event.tags.in_(x),
                            "since": lambda x: Event.created_at > x,
                            "until": lambda x: Event.created_at < x
                        }

                        for index, dict_item in enumerate(output_list):
                            query_limit: int = int(min(dict_item.get('limit', 100), 100))
                            if 'limit' in dict_item:
                                del dict_item['limit']
                            for key, value in dict_item.items():
                                logger.debug(f"Key value is: {key}, {value}")
                                if key in ["#e", "#p", "#d"]:
                                    logger.debug(f"Tag key is : {key} , value is {value} and of type: {type(value)}")
                                    #logger.debug(f"COnditions/values are: {(conditions[key](value))}")
                                    value = value[1]
                                query = query.filter(conditions[key](value))

                        #for key, value in output_list:
                        #    query_limit: int = int(min(value.get('limit', 100), 100))
                        #    if 'limit' in value:
                        #        del value['limit']
                        #        logger.debug(f"Key value is: {key}, {value}")
                        #        if key in ["#e", "#p", "#d"]:
                        #            logger.debug(f"Tag key is : {key} , value is {value} and of type: {type(value)}")
                        #            logger.debug(f"COnditions/values are: {(conditions[key](value))}")
                        #            value = value[1]
                        #        #Value var from output list is passed as an argument to the lambda functions that are the values in the dictionary
                        #        query = query.filter(conditions[key](value))


                        query_result: List[Event] = query.order_by(desc(Event.created_at)).limit(query_limit).all()
                        statsd.increment('nostr.event.queried.postgres', tags=["func:event_query"])
                        serialized_events = [serialize(event) for event in query_result]
                        logger.debug(f"serialized events are: {serialized_events}")
                        redis_client.set(redis_get, str(serialized_events))  
                        redis_client.expire(redis_get, 1800)
                        logger.debug(f"Query result stored in cache. Stored as: filters: {redis_get} values: {str(serialized_events)} ({inspect.currentframe().f_lineno})")

                    except Exception as e:
                        error_message = str(e)
                        logger.error(f"Error occurred: {error_message} ({inspect.currentframe().f_lineno})")

                    finally:
                        logger.debug("FINISH PG BLOCK")

            except Exception as e:
                logger.error(f"Error retrieving cached result: {e}")

        logger.debug(f"Output list is: {output_list} and length is: {len(output_list)}")

    except Exception as e:
        logger.error(f"Error parsing filters: {e}")

    return serialized_events

@app.post("/subscription")
async def handle_subscription(request: Request) -> JSONResponse:
    try:
        response: Optional[Dict[str, Any]] = None
        payload: Dict[str, Any] = await request.json()
        subscription_dict: Dict[str, Any] = payload.get('event_dict', {})
        subscription_id: str = payload.get('subscription_id', "")
        filters: str = subscription_dict

        serialized_events: List[Dict[str, Any]] = await event_query(json.dumps(filters))

        if len(serialized_events) < 2:
            response = None
        else:
            response = {'event': "EVENT", 'subscription_id': subscription_id, 'results_json': serialized_events}

    except Exception:
        raise HTTPException(status_code=500, detail="An error occurred while processing the subscription")
    finally:
        try:
            if response is None:
                response = {'event': "EOSE", 'subscription_id': subscription_id, 'results_json': "None"}
            return JSONResponse(content=response, status_code=200)
        except Exception as e:
            return JSONResponse(content={'error': str(e)}, status_code=500)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=80)

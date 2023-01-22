import os
import asyncio
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from your_orm_code import Event  # import the Event class

DATABASE_URL = os.environ.get("DATABASE_URL")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

async def query_db(authors: list):
    async with SessionLocal() as db:
        query = db.query(Event).filter(Event.pubkey.in_(authors))
        # you can add more filters if required
        # query = query.filter(Event.kind.in_(kind))
        # query = query.filter(Event.created_at.between(since, until))
        result = query.all()
        return result

async def main():
    authors = [str("npub1g5pm4gf8hh7skp2rsnw9h2pvkr32sdnuhkcx9yte7qxmrg6v4txqqudjqv")]
    query_result = await query_db(authors)
    print(query_result)

if __name__ == "__main__":
    asyncio.run(main())


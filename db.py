from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase,sessionmaker
from dotenv import load_dotenv
import os

load_dotenv()

DATABASE_URL=os.getenv("postgreSQL")

engine=create_engine(DATABASE_URL,
                     pool_pre_ping=True,
                     pool_recycle=300)
sessionLocal=sessionmaker(bind=engine, autoflush=False,autocommit=False)
class Base(DeclarativeBase):
    pass
def get_db():
    db=sessionLocal()
    try:
        yield db
    finally:
        db.close()


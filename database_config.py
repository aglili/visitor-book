import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from dotenv import  load_dotenv
from logger import get_logger
logger = get_logger(__name__)

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL","postgresql://postgres:jailer23$@localhost:5432/visitor_db")



engine = create_engine(url=DATABASE_URL)


sessionLocal = sessionmaker(bind=engine,autoflush=False,autocommit=False)


Base = declarative_base()



def get_db():
    db = sessionLocal()
    logger.debug("Creating a new database session")
    try:
        yield db
    except Exception as e:
        logger.error(f"An error occurred while using the database session: {e}")
        raise
    finally:
        db.close()
        logger.debug("Closing the database session")


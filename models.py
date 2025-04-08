from sqlalchemy import  Integer,Column,String
from database_config import Base



class Visitor(Base):
    __tablename__ = "visitors"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True, nullable=False)
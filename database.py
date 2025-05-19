from sqlalchemy import create_engine, Column, Integer, String, Text, Time
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Database setup
Base = declarative_base()
engine = create_engine('sqlite:///schedule_bot.db')
Session = sessionmaker(bind=engine)

# Model for scheduled messages
class ScheduledMessage(Base):
    __tablename__ = 'scheduled_messages'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer)
    chat_id = Column(Integer)
    message_text = Column(Text)
    day_of_week = Column(Integer)  # 0-6 (Monday-Sunday)
    time = Column(Time)
    target_chat_id = Column(String)
    target_chat_title = Column(String)


# Create tables
def create_tables():
    Base.metadata.create_all(engine)


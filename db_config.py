from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, Text, Float, Date, ForeignKey, Table
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.dialects.postgresql import ARRAY
from datetime import datetime
import json
from config import settings

# Database setup
engine = create_engine(settings.database_url)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Association table for many-to-many relationship between meetings and attendees
meeting_attendees = Table(
    'meeting_attendees',
    Base.metadata,
    Column('meeting_id', Integer, ForeignKey('meetings.id'), primary_key=True),
    Column('user_id', Integer, ForeignKey('users.id'), primary_key=True)
)

# Database Models
class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=False)
    timezone = Column(String, default="UTC")
    calendar_provider = Column(String, default="google")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    organized_meetings = relationship("Meeting", back_populates="organizer", foreign_keys="Meeting.organizer_id")
    attended_meetings = relationship("Meeting", secondary=meeting_attendees, back_populates="attendees")
    action_items = relationship("ActionItem", back_populates="assignee")

class Meeting(Base):
    __tablename__ = "meetings"
    
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    description = Column(Text)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    location = Column(String)
    meeting_link = Column(String)
    priority = Column(String, default="medium")
    status = Column(String, default="scheduled")
    organizer_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    calendar_event_id = Column(String)
    recording_path = Column(String)
    transcript_path = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    organizer = relationship("User", back_populates="organized_meetings", foreign_keys=[organizer_id])
    attendees = relationship("User", secondary=meeting_attendees, back_populates="attended_meetings")
    minutes = relationship("MinutesOfMeeting", back_populates="meeting", uselist=False)
    action_items = relationship("ActionItem", back_populates="meeting")
    transcription = relationship("Transcription", back_populates="meeting", uselist=False)

class MinutesOfMeeting(Base):
    __tablename__ = "minutes_of_meeting"
    
    id = Column(Integer, primary_key=True, index=True)
    meeting_id = Column(Integer, ForeignKey("meetings.id"), nullable=False)
    summary = Column(Text, nullable=False)
    key_decisions = Column(Text)  # JSON string
    discussion_points = Column(Text)  # JSON string
    next_meeting_date = Column(DateTime)
    pdf_path = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    meeting = relationship("Meeting", back_populates="minutes")
    
    @property
    def key_decisions_list(self):
        return json.loads(self.key_decisions) if self.key_decisions else []
    
    @key_decisions_list.setter
    def key_decisions_list(self, value):
        self.key_decisions = json.dumps(value)
    
    @property
    def discussion_points_list(self):
        return json.loads(self.discussion_points) if self.discussion_points else []
    
    @discussion_points_list.setter
    def discussion_points_list(self, value):
        self.discussion_points = json.dumps(value)

class ActionItem(Base):
    __tablename__ = "action_items"
    
    id = Column(Integer, primary_key=True, index=True)
    meeting_id = Column(Integer, ForeignKey("meetings.id"), nullable=False)
    title = Column(String, nullable=False)
    description = Column(Text)
    assignee_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    due_date = Column(Date)
    priority = Column(String, default="medium")
    status = Column(String, default="pending")
    completed_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    meeting = relationship("Meeting", back_populates="action_items")
    assignee = relationship("User", back_populates="action_items")

class Transcription(Base):
    __tablename__ = "transcriptions"
    
    id = Column(Integer, primary_key=True, index=True)
    meeting_id = Column(Integer, ForeignKey("meetings.id"), nullable=False)
    content = Column(Text, nullable=False)
    language = Column(String, default="en")
    confidence_score = Column(Float)
    audio_file_path = Column(String, nullable=False)
    processing_time = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    meeting = relationship("Meeting", back_populates="transcription")

# Database utility functions
def get_db():
    """Dependency to get database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def create_tables():
    """Create all database tables."""
    Base.metadata.create_all(bind=engine)

def drop_tables():
    """Drop all database tables."""
    Base.metadata.drop_all(bind=engine)

def reset_database():
    """Reset database by dropping and recreating all tables."""
    drop_tables()
    create_tables()

# Initialize database
if __name__ == "__main__":
    create_tables()
    print("Database tables created successfully!")

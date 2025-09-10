# db.py
from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from datetime import datetime
import uuid

DATABASE_URL = "sqlite+aiosqlite:///./slides.db"

Base = declarative_base()


class Slide(Base):
    __tablename__ = "slides"
    id = Column(Integer, primary_key=True, index=True)
    uuid = Column(String, unique=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False)
    path = Column(String, nullable=False)
    filename = Column(String, nullable=False)
    uploaded_at = Column(DateTime, default=datetime.utcnow)

    view_states = relationship("ViewState", back_populates="slide", cascade="all, delete")


class ViewState(Base):
    __tablename__ = "view_states"
    id = Column(Integer, primary_key=True, index=True)
    slide_id = Column(Integer, ForeignKey("slides.id", ondelete="CASCADE"))
    zoom_level = Column(Float, nullable=False)
    center_x = Column(Float, nullable=False)
    center_y = Column(Float, nullable=False)
    rotation = Column(Float, default=0.0)
    saved_at = Column(DateTime, default=datetime.utcnow)

    slide = relationship("Slide", back_populates="view_states")


engine = create_async_engine(DATABASE_URL, echo=False, future=True)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

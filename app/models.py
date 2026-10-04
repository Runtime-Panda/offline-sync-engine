import uuid
from datetime import datetime
from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship
from app.database import Base


class Document(Base):
    __tablename__ = "documents"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    title = Column(String, nullable=False)
    content = Column(JSON, nullable=False, default=dict)
    version = Column(Integer, nullable=False, default=1)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    revisions = relationship("DocumentRevision", back_populates="document", cascade="all, delete-orphan")


class DocumentRevision(Base):
    __tablename__ = "document_revisions"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    document_id = Column(String, ForeignKey("documents.id"), nullable=False)
    version = Column(Integer, nullable=False)
    title = Column(String, nullable=False)
    content = Column(JSON, nullable=False)
    device_id = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    document = relationship("Document", back_populates="revisions")


class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"

    key = Column(String, primary_key=True)
    response_code = Column(Integer, nullable=False)
    response_body = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
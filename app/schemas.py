from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class DocumentCreate(BaseModel):
    title: str
    content: Dict[str, Any]


class DocumentResponse(BaseModel):
    id: str
    title: str
    content: Dict[str, Any]
    version: int

    class Config:
        from_attributes = True


class SyncRequest(BaseModel):
    idempotency_key: str
    device_id: str
    document_id: str
    base_version: int
    changes: Dict[str, Any]


class RevisionResponse(BaseModel):
    id: str
    version: int
    title: str
    content: Dict[str, Any]
    device_id: str
    created_at: Any

    class Config:
        from_attributes = True
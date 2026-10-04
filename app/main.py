from typing import List
from fastapi import Depends, FastAPI, HTTPException, Response
from sqlalchemy.orm import Session

from app.database import Base, engine, get_db
from app.models import Document, DocumentRevision
from app.schemas import DocumentCreate, DocumentResponse, RevisionResponse, SyncRequest
from app.sync_engine import process_sync

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Offline Sync Engine")


@app.post("/documents", response_model=DocumentResponse, status_code=201)
def create_document(doc_in: DocumentCreate, db: Session = Depends(get_db)):
    doc = Document(title=doc_in.title, content=doc_in.content, version=1)
    db.add(doc)
    db.commit()
    db.refresh(doc)

    rev = DocumentRevision(
        document_id=doc.id,
        version=1,
        title=doc.title,
        content=doc.content,
        device_id="system_init",
    )
    db.add(rev)
    db.commit()

    return doc


@app.get("/documents/{doc_id}", response_model=DocumentResponse)
def get_document(doc_id: str, db: Session = Depends(get_db)):
    doc = db.query(Document).filter_by(id=doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@app.post("/sync")
def sync_document(
    req: SyncRequest, response: Response, db: Session = Depends(get_db)
):
    code, body = process_sync(
        db,
        req.idempotency_key,
        req.device_id,
        req.document_id,
        req.base_version,
        req.changes,
    )
    response.status_code = code
    return body


@app.get("/documents/{doc_id}/revisions", response_model=List[RevisionResponse])
def get_revisions(doc_id: str, db: Session = Depends(get_db)):
    revisions = (
        db.query(DocumentRevision)
        .filter_by(document_id=doc_id)
        .order_by(DocumentRevision.version.asc())
        .all()
    )
    return revisions


@app.post("/documents/{doc_id}/restore/{version}", response_model=DocumentResponse)
def restore_version(doc_id: str, version: int, db: Session = Depends(get_db)):
    target_rev = (
        db.query(DocumentRevision)
        .filter_by(document_id=doc_id, version=version)
        .first()
    )
    if not target_rev:
        raise HTTPException(status_code=404, detail="Revision version not found")

    doc = db.query(Document).filter_by(id=doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    doc.title = target_rev.title
    doc.content = target_rev.content
    doc.version += 1

    new_rev = DocumentRevision(
        document_id=doc.id,
        version=doc.version,
        title=doc.title,
        content=doc.content,
        device_id="system_restore",
    )
    db.add(new_rev)
    db.commit()
    db.refresh(doc)

    return doc
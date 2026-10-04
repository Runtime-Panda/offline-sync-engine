from typing import Any, Dict, Tuple
from sqlalchemy.orm import Session
from app.models import Document, DocumentRevision, IdempotencyKey


def process_sync(
    db: Session,
    idempotency_key: str,
    device_id: str,
    doc_id: str,
    base_version: int,
    changes: Dict[str, Any],
) -> Tuple[int, Dict[str, Any]]:
    existing_key = db.query(IdempotencyKey).filter_by(key=idempotency_key).first()
    if existing_key:
        return existing_key.response_code, existing_key.response_body

    doc = db.query(Document).filter_by(id=doc_id).first()
    if not doc:
        response = (404, {"error": "Document not found"})
        _save_idempotency(db, idempotency_key, response[0], response[1])
        return response

    if base_version == doc.version:
        if "title" in changes:
            doc.title = changes["title"]
        if "content" in changes:
            doc.content = {**doc.content, **changes["content"]}

        doc.version += 1
        _record_revision(db, doc, device_id)
        db.commit()
        db.refresh(doc)

        response_data = {
            "status": "ACCEPTED",
            "document_id": doc.id,
            "version": doc.version,
            "title": doc.title,
            "content": doc.content,
        }
        response = (200, response_data)
        _save_idempotency(db, idempotency_key, response[0], response[1])
        return response

    if base_version < doc.version:
        revisions = (
            db.query(DocumentRevision)
            .filter(
                DocumentRevision.document_id == doc_id,
                DocumentRevision.version > base_version,
            )
            .all()
        )

        server_modified_keys = set()
        for rev in revisions:
            for k in rev.content.keys():
                server_modified_keys.add(k)

        client_modified_content = changes.get("content", {})
        conflicting_keys = set(client_modified_content.keys()).intersection(
            server_modified_keys
        )

        if not conflicting_keys:
            merged_content = {**doc.content, **client_modified_content}
            if "title" in changes:
                doc.title = changes["title"]
            doc.content = merged_content
            doc.version += 1

            _record_revision(db, doc, device_id)
            db.commit()
            db.refresh(doc)

            response_data = {
                "status": "MERGED",
                "document_id": doc.id,
                "version": doc.version,
                "title": doc.title,
                "content": doc.content,
            }
            response = (200, response_data)
            _save_idempotency(db, idempotency_key, response[0], response[1])
            return response

        response_data = {
            "status": "CONFLICT",
            "document_id": doc.id,
            "server_version": doc.version,
            "conflicting_fields": list(conflicting_keys),
            "server_state": {"title": doc.title, "content": doc.content},
            "client_state": changes,
        }
        response = (409, response_data)
        _save_idempotency(db, idempotency_key, response[0], response[1])
        return response

    response = (400, {"error": "Invalid base_version submitted"})
    _save_idempotency(db, idempotency_key, response[0], response[1])
    return response


def _record_revision(db: Session, doc: Document, device_id: str):
    rev = DocumentRevision(
        document_id=doc.id,
        version=doc.version,
        title=doc.title,
        content=doc.content,
        device_id=device_id,
    )
    db.add(rev)


def _save_idempotency(
    db: Session, key: str, status_code: int, response_body: Dict[str, Any]
):
    idem = IdempotencyKey(
        key=key, response_code=status_code, response_body=response_body
    )
    db.add(idem)
    db.commit()
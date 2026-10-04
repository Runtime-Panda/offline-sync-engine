from typing import List
from fastapi import Depends, FastAPI, HTTPException, Response
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.database import Base, engine, get_db
from app.models import Document, DocumentRevision
from app.schemas import DocumentCreate, DocumentResponse, RevisionResponse, SyncRequest
from app.sync_engine import process_sync

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Offline Sync Engine", docs_url=None)

CLEAN_DARK_THEME_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

/* Global Reset & Dark Background */
body {
    background-color: #121212 !important;
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
    color: #E0E0E0 !important;
}

/* Hide Top Bar */
.swagger-ui .topbar { display: none !important; }

/* Header Info Section */
.swagger-ui .info .title {
    color: #8AB4F8 !important;
    font-size: 28px !important;
    font-weight: 700 !important;
}

/* API Operation Blocks */
.swagger-ui .opblock {
    background: #1E1E1E !important;
    border: 1px solid #2D2D2D !important;
    border-radius: 8px !important;
    box-shadow: none !important;
    margin-bottom: 12px !important;
}

.swagger-ui .opblock .opblock-summary {
    border-bottom: 1px solid #2D2D2D !important;
}

.swagger-ui .opblock .opblock-summary-path,
.swagger-ui .opblock .opblock-summary-description,
.swagger-ui .opblock-title,
.swagger-ui .opblock-description-wrapper,
.swagger-ui .parameter__name,
.swagger-ui .parameter__type,
.swagger-ui label,
.swagger-ui table thead tr th,
.swagger-ui table tbody tr td,
.swagger-ui .response-col_status,
.swagger-ui .response-col_links,
.swagger-ui .opblock-tag {
    color: #E0E0E0 !important;
    background: transparent !important;
}

.swagger-ui .opblock-section-header {
    background: #252525 !important;
}

/* HTTP Method Badges */
.swagger-ui .opblock-post .opblock-summary-method {
    background: #1A73E8 !important;
    color: #FFFFFF !important;
    border-radius: 4px !important;
}

.swagger-ui .opblock-get .opblock-summary-method {
    background: #0F9D58 !important;
    color: #FFFFFF !important;
    border-radius: 4px !important;
}

/* Code Inputs & Controls */
.swagger-ui textarea, 
.swagger-ui input[type=text],
.swagger-ui select {
    background-color: #181818 !important;
    color: #00FF66 !important;
    border: 1px solid #333333 !important;
    border-radius: 4px !important;
}

.swagger-ui .btn {
    background: #2A2A2A !important;
    color: #8AB4F8 !important;
    border: 1px solid #333333 !important;
    border-radius: 4px !important;
}

.swagger-ui .btn.execute {
    background-color: #1A73E8 !important;
    color: #FFFFFF !important;
    border: none !important;
}

/* --- COMPLETE SCHEMAS SECTION FIX --- */
.swagger-ui section.models {
    background: #1E1E1E !important;
    border: 1px solid #2D2D2D !important;
    border-radius: 8px !important;
    padding: 16px !important;
}

.swagger-ui section.models h4 {
    color: #8AB4F8 !important;
    font-size: 18px !important;
    border-bottom: 1px solid #2D2D2D !important;
    padding-bottom: 8px !important;
}

.swagger-ui .model-container {
    background: #181818 !important;
    border-radius: 6px !important;
    margin: 8px 0 !important;
    border: 1px solid #2A2A2A !important;
    padding: 10px !important;
}

.swagger-ui .model-box {
    background: transparent !important;
}

.swagger-ui .model-title,
.swagger-ui .model-title span,
.swagger-ui .model,
.swagger-ui .model .property,
.swagger-ui .prop-name,
.swagger-ui .prop-type,
.swagger-ui .inner-object {
    color: #E0E0E0 !important;
    background: transparent !important;
}

.swagger-ui .prop-name {
    color: #8AB4F8 !important;
    font-weight: 600 !important;
}

.swagger-ui .prop-type {
    color: #81C995 !important;
}

.swagger-ui .model-box .model-jump-to-path,
.swagger-ui .model-box .model-jump-to-path button {
    background: #2D2D2D !important;
    color: #8AB4F8 !important;
    border-radius: 4px !important;
    border: none !important;
}

.swagger-ui .model-toggle:after {
    filter: invert(1) !important;
}
"""


@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui_html():
    base_html = get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title=app.title + " - Docs",
    )
    custom_html = base_html.body.decode("utf-8").replace(
        "</head>", f"<style>{CLEAN_DARK_THEME_CSS}</style></head>"
    )
    return HTMLResponse(content=custom_html)


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
import pytest
from fastapi.testclient import TestClient
from app.database import Base, engine
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_offline_sync_workflow():
    res = client.post(
        "/documents",
        json={"title": "Draft 1", "content": {"author": "Alex", "status": "draft"}},
    )
    assert res.status_code == 201
    doc_id = res.json()["id"]

    sync_payload_1 = {
        "idempotency_key": "key_1",
        "device_id": "device_a",
        "document_id": doc_id,
        "base_version": 1,
        "changes": {"content": {"status": "published"}},
    }
    res_1 = client.post("/sync", json=sync_payload_1)
    assert res_1.status_code == 200
    assert res_1.json()["status"] == "ACCEPTED"
    assert res_1.json()["version"] == 2

    res_1_repeat = client.post("/sync", json=sync_payload_1)
    assert res_1_repeat.status_code == 200
    assert res_1_repeat.json() == res_1.json()

    sync_payload_auto_merge = {
        "idempotency_key": "key_2",
        "device_id": "device_b",
        "document_id": doc_id,
        "base_version": 1,
        "changes": {"content": {"category": "tech"}},
    }
    res_2 = client.post("/sync", json=sync_payload_auto_merge)
    assert res_2.status_code == 200
    assert res_2.json()["status"] == "MERGED"
    assert res_2.json()["version"] == 3
    assert res_2.json()["content"] == {
        "author": "Alex",
        "status": "published",
        "category": "tech",
    }

    sync_payload_conflict = {
        "idempotency_key": "key_3",
        "device_id": "device_c",
        "document_id": doc_id,
        "base_version": 1,
        "changes": {"content": {"status": "archived"}},
    }
    res_3 = client.post("/sync", json=sync_payload_conflict)
    assert res_3.status_code == 409
    assert res_3.json()["status"] == "CONFLICT"
    assert "status" in res_3.json()["conflicting_fields"]

    rev_res = client.get(f"/documents/{doc_id}/revisions")
    assert rev_res.status_code == 200
    assert len(rev_res.json()) == 3

    restore_res = client.post(f"/documents/{doc_id}/restore/1")
    assert restore_res.status_code == 200
    assert restore_res.json()["version"] == 4
    assert restore_res.json()["content"] == {"author": "Alex", "status": "draft"}
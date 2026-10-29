import json

import pytest
from fastapi.testclient import TestClient

from linescope.app import create_app
from linescope.extractor import ExtractionError


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(str(tmp_path / "runs.sqlite3"))) as client:
        yield client


def test_persistent_immutable_revision_chain(tmp_path, case, checked):
    path = str(tmp_path / "persistent.sqlite3")
    with TestClient(create_app(path)) as client:
        response = client.post("/api/runs", json=case)
        assert response.status_code == 201
        first = response.json()
        assert first["report"]["verdict"] == "NEEDS_REVIEW"
        revision = client.post(f'/api/runs/{first["id"]}/revisions', json={
            "extraction": case["extraction"], "review": checked.model_dump()}).json()
        assert revision["parent_id"] == first["id"]
        assert revision["report"]["verdict"] == "CHECKS_PASSED"
        assert revision["report"]["document_sha256"] == first["report"]["document_sha256"]
        assert client.get(f'/api/runs/{first["id"]}').json() == first
    with TestClient(create_app(path)) as restarted:
        export = restarted.get(f'/api/runs/{revision["id"]}/export')
        assert export.json() == revision
        assert "attachment" in export.headers["content-disposition"]


def test_revision_cannot_replace_source_document(client, case, checked):
    first = client.post("/api/runs", json=case).json()
    response = client.post(f'/api/runs/{first["id"]}/revisions', json={
        "document": case["document"], "extraction": case["extraction"], "review": checked.model_dump()})
    assert response.status_code == 422


def test_health_does_not_claim_model_ready(client):
    assert client.get("/health").json()["model_reachability"] == "not_checked"


def test_boundaries(client, case):
    assert client.post("/api/runs", content="a"*262145, headers={"content-type": "application/json"}).status_code == 413
    assert client.post("/api/runs", content="{}", headers={"content-type": "text/plain"}).status_code == 415
    assert client.post("/api/runs", json=case, headers={"origin": "https://evil.test"}).status_code == 403
    assert client.get("/health", headers={"host": "evil.test"}).status_code == 400
    assert client.get("/api/runs/not-a-uuid").status_code == 422
    assert client.get("/api/runs/00000000-0000-0000-0000-000000000001").status_code == 404


def test_no_source_content_in_errors_or_request_logs(client, case, caplog):
    case["document"]["pages"][0]["text"] = "PRIVATE_SOURCE_SENTINEL"
    case["extraction"]["total"]["value"] = "PRIVATE_SECRET_SENTINEL"
    with caplog.at_level("INFO", logger="linescope"):
        response = client.post("/api/runs", json=case)
    assert response.status_code == 422
    assert "PRIVATE" not in response.text
    assert "PRIVATE" not in caplog.text
    assert "X-Request-ID" in response.headers


def test_model_error_stays_error(client, case, monkeypatch):
    def unavailable(*_):
        raise ExtractionError("MODEL_UNAVAILABLE")
    monkeypatch.setattr("linescope.app.extract", unavailable)
    response = client.post("/api/extract", json={"document": case["document"]})
    assert response.status_code == 503
    assert response.json()["detail"] == "MODEL_UNAVAILABLE"


def test_model_cannot_confirm_human_review(client, case, parsed, monkeypatch):
    monkeypatch.setattr("linescope.app.extract", lambda *_: parsed[1])
    record = client.post("/api/extract", json={"document": case["document"]}).json()
    assert record["review"]["coverage_confirmed"] is False
    assert record["report"]["verdict"] == "NEEDS_REVIEW"
    assert record["metadata"]["mode"] == "ollama"


def test_bundled_ui_and_demo(client):
    assert "LineScope" in client.get("/").text
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/api/demo").json()["extraction"]["total"]["value"] == "4500.00"


def test_evidence_roundtrip_is_reproducible(client, case):
    from linescope.models import Document, Extraction, Review
    from linescope.verifier import verify
    record = client.post("/api/runs", json=case).json()
    replay = verify(Document.model_validate(record["document"]), Extraction.model_validate(record["extraction"]),
                    Review.model_validate(record["review"]))
    assert replay.model_dump(mode="json") == record["report"]

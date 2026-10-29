"""Single-user local HTTP application. Each check saves an immutable revision."""

import json
import logging
import os
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import __version__
from .extractor import PROMPT_VERSION, ExtractionError, extract, validate_endpoint
from .models import Contract, Document, Extraction, Review
from .store import Store
from .verifier import verify

HERE = Path(__file__).parent
LOGGER = logging.getLogger("linescope")


class ManualRequest(Contract):
    document: Document
    extraction: Extraction
    review: Review = Field(default_factory=Review)


class ExtractRequest(Contract):
    document: Document


class RevisionRequest(Contract):
    extraction: Extraction
    review: Review


def create_app(db_path: str | None = None) -> FastAPI:
    app = FastAPI(title="LineScope Quotes", version=__version__)
    store = Store(db_path or os.getenv("LINESCOPE_DB", "data/linescope.sqlite3"))
    endpoint = validate_endpoint(os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434"))
    model = os.getenv("OLLAMA_MODEL", "")
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "testserver"])

    @app.middleware("http")
    async def limits_and_logging(request: Request, call_next):
        request_id, start = uuid4().hex, time.monotonic()
        request.state.request_id = request_id
        if request.method in {"POST", "PUT", "PATCH"}:
            origin = request.headers.get("origin")
            if origin and origin != f"{request.url.scheme}://{request.headers.get('host')}":
                return JSONResponse({"error": "ORIGIN_REJECTED"}, status_code=403)
            if request.headers.get("content-type", "").split(";", 1)[0] != "application/json":
                return JSONResponse({"error": "JSON_REQUIRED"}, status_code=415)
            chunks, size = [], 0
            async for chunk in request.stream():
                size += len(chunk)
                if size > 262144:
                    return JSONResponse({"error": "BODY_TOO_LARGE"}, status_code=413)
                chunks.append(chunk)
            request._body = b"".join(chunks)
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; frame-ancestors 'none'"
        route = request.scope.get("route")
        LOGGER.info(json.dumps(dict(request_id=request_id, method=request.method,
                                    path=getattr(route, "path", "/unknown"), status=response.status_code,
                                    elapsed_ms=round((time.monotonic() - start) * 1000)), ensure_ascii=False))
        return response

    @app.exception_handler(RequestValidationError)
    async def invalid_input(request, exc):
        # Do not echo source contents or model output in validation errors.
        return JSONResponse({"error": "INVALID_INPUT", "request_id": request.state.request_id,
                             "fields": [".".join(map(str, e["loc"])) for e in exc.errors()]}, status_code=422)

    @app.exception_handler(sqlite3.Error)
    async def database_error(request, exc):
        LOGGER.error(json.dumps(dict(request_id=request.state.request_id, error="DATABASE_UNAVAILABLE")))
        return JSONResponse({"error": "DATABASE_UNAVAILABLE", "request_id": request.state.request_id}, status_code=503)

    def get_run(run_id: UUID):
        record = store.get(str(run_id))
        if record is None:
            raise HTTPException(404, "RUN_NOT_FOUND")
        return record

    def save(document, extraction, review, metadata, parent_id=None):
        report = verify(document, extraction, review)
        record = dict(id=str(uuid4()), parent_id=parent_id,
                      created_at=datetime.now(timezone.utc).isoformat(),
                      document=document.model_dump(mode="json"),
                      extraction=extraction.model_dump(mode="json"),
                      review=review.model_dump(mode="json"), metadata=metadata,
                      report=report.model_dump(mode="json"))
        store.put(record)
        return record

    @app.get("/health")
    def health():
        store.ready()
        return {"status": "ok", "version": __version__, "model_configured": bool(model),
                "model_reachability": "not_checked"}

    @app.get("/api/demo")
    def demo():
        return json.loads((HERE / "demo.json").read_text(encoding="utf-8"))

    @app.post("/api/runs", status_code=201)
    def manual_run(body: ManualRequest):
        return save(body.document, body.extraction, body.review, {"mode": "manual", "model": None,
                                                               "prompt_version": None})

    @app.post("/api/extract", status_code=201)
    def model_run(body: ExtractRequest):
        try:
            candidate = extract(body.document, endpoint, model)
        except ExtractionError as exc:
            status = 504 if exc.code == "MODEL_TIMEOUT" else 503
            raise HTTPException(status, exc.code) from exc
        # A model cannot supply or inherit human confirmations.
        return save(body.document, candidate, Review(), {"mode": "ollama", "model": model,
                                                        "prompt_version": PROMPT_VERSION})

    @app.get("/api/runs/{run_id}")
    def read_run(run_id: UUID):
        return get_run(run_id)

    @app.post("/api/runs/{run_id}/revisions", status_code=201)
    def revise(run_id: UUID, body: RevisionRequest):
        previous = get_run(run_id)
        return save(Document.model_validate(previous["document"]), body.extraction, body.review,
                    {**previous["metadata"], "revision": "human_candidate"}, str(run_id))

    @app.get("/api/runs/{run_id}/export")
    def export(run_id: UUID):
        return JSONResponse(get_run(run_id), headers={
            "Content-Disposition": f'attachment; filename="linescope-{run_id}.json"'})

    app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")

    @app.get("/")
    def index():
        return FileResponse(HERE / "static/index.html")

    return app


app = create_app()

"""Call the configured local Ollama once on the bundled synthetic source.

This smoke test records a real candidate and its checks, without reading the
hand-authored candidate as model input or treating review-needed as a success.
"""

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from linescope.extractor import PROMPT_VERSION, ExtractionError, extract
from linescope.models import Document, Review
from linescope.verifier import verify

ROOT = Path(__file__).resolve().parents[1]


def main():
    source = json.loads((ROOT / "src/linescope/demo.json").read_text(encoding="utf-8"))["document"]
    document = Document.model_validate(source)
    model = os.environ["OLLAMA_MODEL"]
    start = time.monotonic()
    report = dict(timestamp_utc=datetime.now(timezone.utc).isoformat(), model=model,
                  prompt_version=PROMPT_VERSION, source="bundled synthetic source only",
                  review="not confirmed; model cannot approve", status="error")
    try:
        candidate = extract(document, os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434"), model)
        checks = verify(document, candidate, Review())
        report.update(status="candidate_received", document=document.model_dump(mode="json"),
                      extraction=candidate.model_dump(mode="json"), review=Review().model_dump(mode="json"),
                      report=checks.model_dump(mode="json"))
    except ExtractionError as exc:
        report["error"] = exc.code
    report["observed_seconds"] = round(time.monotonic() - start, 3)
    target = ROOT / ".local/live-smoke.json"
    target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key not in {"document", "extraction", "report"}}, ensure_ascii=False, indent=2))
    if "report" in report:
        print(json.dumps(report["report"], ensure_ascii=False, indent=2))
    raise SystemExit(0 if report["status"] == "candidate_received" else 1)


if __name__ == "__main__":
    main()

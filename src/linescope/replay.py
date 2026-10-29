"""Replay a saved report without any model calls: python -m linescope.replay file.json."""

import argparse
import json
from pathlib import Path

from .models import Document, Extraction, Review
from .verifier import verify


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("record", type=Path)
    args = parser.parse_args()
    record = json.loads(args.record.read_text(encoding="utf-8"))
    report = verify(Document.model_validate(record["document"]),
                    Extraction.model_validate(record["extraction"]),
                    Review.model_validate(record["review"]))
    identical = report.model_dump(mode="json") == record["report"]
    print(json.dumps({"identical": identical, "verdict": report.verdict,
                      "document_sha256": report.document_sha256}, ensure_ascii=False, indent=2))
    raise SystemExit(0 if identical else 1)


if __name__ == "__main__":
    main()

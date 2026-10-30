import json
from pathlib import Path

import pytest

from linescope.models import Document, Extraction, Review


@pytest.fixture
def case():
    return json.loads((Path(__file__).parents[1] / "src/linescope/demo.json").read_text(encoding="utf-8"))


@pytest.fixture
def checked():
    return Review(coverage_confirmed=True, simple_pricing_confirmed=True,
                  reviewer="test-reviewer", reason="Synthetic fixture manually checked")


@pytest.fixture
def parsed(case):
    return Document.model_validate(case["document"]), Extraction.model_validate(case["extraction"])

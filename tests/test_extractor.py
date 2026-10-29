import json

import httpx
import pytest

from linescope.extractor import ExtractionError, extract, validate_endpoint


def test_local_adapter_contract(case, parsed):
    def handler(request):
        body = json.loads(request.content)
        assert str(request.url) == "http://127.0.0.1:11434/api/chat"
        assert body["stream"] is False
        assert body["format"]["type"] == "object"
        value_schema = body["format"]["$defs"]["NumberField"]["properties"]["value"]
        assert {part["type"] for part in value_schema["anyOf"]} == {"string", "null"}
        assert "review" not in body["format"]["properties"]
        assert "Synthetic fixture" not in str(body)
        return httpx.Response(200, json={"done": True, "message": {
            "content": json.dumps(case["extraction"])}})
    result = extract(parsed[0], "http://127.0.0.1:11434", "configured-model", httpx.MockTransport(handler))
    assert result.total.value == parsed[1].total.value


@pytest.mark.parametrize("url", ["https://example.com", "http://10.0.0.1:11434", "http://localhost@evil.test",
                                     "http://localhost/x", "http://localhost?x=1", "http://u:p@localhost",
                                     "file:///tmp/data", "http://localhost:bad"])
def test_unapproved_endpoint_rejected(url):
    with pytest.raises(ValueError):
        validate_endpoint(url)


@pytest.mark.parametrize("response,code", [
    (httpx.Response(404), "MODEL_HTTP_ERROR"),
    (httpx.Response(302, headers={"location": "http://example.com"}), "MODEL_HTTP_ERROR"),
    (httpx.Response(200, text="not json"), "MODEL_INVALID_OUTPUT"),
    (httpx.Response(200, json={"done": True, "message": {"content": "{}"}}), "MODEL_INVALID_OUTPUT"),
    (httpx.Response(200, json={"done": False}), "MODEL_INCOMPLETE"),
    (httpx.Response(200, content=b"x" * 262145), "MODEL_RESPONSE_TOO_LARGE"),
])
def test_bad_model_output_does_not_fallback(parsed, response, code):
    with pytest.raises(ExtractionError) as caught:
        extract(parsed[0], "http://localhost:11434", "test", httpx.MockTransport(lambda _: response))
    assert caught.value.code == code


def test_timeout_is_bounded_and_identifiable(parsed):
    def handler(_):
        raise httpx.ReadTimeout("raw model response must not leak")
    with pytest.raises(ExtractionError, match="MODEL_TIMEOUT"):
        extract(parsed[0], "http://localhost:11434", "test", httpx.MockTransport(handler))

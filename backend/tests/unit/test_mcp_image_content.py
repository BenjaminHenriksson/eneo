import base64
from types import SimpleNamespace

import pytest

from intric.mcp_servers.infrastructure import image_content
from intric.mcp_servers.infrastructure.proxy import mcp_proxy_session


def _result(data=b"image", mime="image/jpeg"):
    return {
        "content": [
            {"type": "text", "text": "Camera location and perspective metadata"},
            {
                "type": "image",
                "mime_type": mime,
                "data": base64.b64encode(data).decode("ascii"),
            },
        ],
        "is_error": False,
    }


def test_binary_images_do_not_consume_text_output_limit(monkeypatch):
    monkeypatch.setattr(
        mcp_proxy_session, "_settings", SimpleNamespace(mcp_tool_output_max_chars=200)
    )
    result = _result(b"x" * 10000)
    proxy = object.__new__(mcp_proxy_session.MCPProxySession)
    assert proxy._truncate_tool_result(result) is result
    message = image_content.image_message(result, "call_photo")
    assert message["role"] == "user"
    assert "call_photo" in message["content"][0]["text"]
    image = message["content"][1]["image_url"]
    assert image["detail"] == "high"
    assert image["url"] == "data:image/jpeg;base64," + result["content"][1]["data"]


def test_text_limits_still_apply_and_failure_does_not_attach_images(monkeypatch):
    monkeypatch.setattr(
        mcp_proxy_session, "_settings", SimpleNamespace(mcp_tool_output_max_chars=200)
    )
    result = _result()
    result["content"][0]["text"] = "x" * 1000
    proxy = object.__new__(mcp_proxy_session.MCPProxySession)
    rejected = proxy._truncate_tool_result(result)
    assert rejected["is_error"]
    assert image_content.image_message(rejected, "call_photo") is None


@pytest.mark.parametrize("mime", ["image/svg+xml", "text/html", None])
def test_non_raster_payloads_are_rejected(mime):
    with pytest.raises(ValueError, match="unsupported"):
        image_content.image_blocks(_result(mime=mime))


def test_malformed_or_oversized_image_is_explicit_error(monkeypatch):
    result = _result()
    result["content"][1]["data"] = "not base64!"
    with pytest.raises(ValueError, match="encoding"):
        image_content.image_blocks(result)
    monkeypatch.setattr(image_content, "MAX_IMAGE_BYTES_PER_RESULT", 3)
    with pytest.raises(ValueError, match="size limit"):
        image_content.image_blocks(_result())


def test_text_only_and_error_results_do_not_generate_extra_messages():
    assert image_content.image_message({"content": []}, "call_text") is None
    result = _result()
    result["is_error"] = True
    assert image_content.image_message(result, "call_error") is None


@pytest.mark.parametrize("mime", ["image/jpeg", "image/png", "image/webp", "image/gif"])
def test_supported_mime_alias_and_high_detail(mime):
    result = _result(mime=mime)
    item = result["content"][1]
    item["mimeType"] = item.pop("mime_type")
    assert image_content.image_blocks(result) == [
        {
            "type": "image_url",
            "image_url": {
                "url": f"data:{mime};base64,{item['data']}",
                "detail": "high",
            },
        }
    ]


@pytest.mark.parametrize(
    "field,value",
    [
        ("mime_type", ["image/jpeg"]),
        ("mime_type", "image/svg+xml"),
        ("data", None),
        ("data", ""),
        ("data", "data:image/jpeg;base64,aW1hZ2U="),
        ("data", "not base64!"),
    ],
)
def test_invalid_images_become_safe_tool_errors(field, value, monkeypatch):
    monkeypatch.setattr(
        mcp_proxy_session, "_settings", SimpleNamespace(mcp_tool_output_max_chars=200)
    )
    result = _result()
    result["content"][1][field] = value
    proxy = object.__new__(mcp_proxy_session.MCPProxySession)
    rejected = proxy._truncate_tool_result(result)
    assert rejected["is_error"]
    assert [item["type"] for item in rejected["content"]] == ["text"]
    assert "Tool returned" in rejected["content"][0]["text"]
    assert image_content.image_message(rejected, "call_invalid") is None


def test_binary_budget_counts_all_images_and_accepts_exact_boundary(monkeypatch):
    monkeypatch.setattr(image_content, "MAX_IMAGE_BYTES_PER_RESULT", 6)
    monkeypatch.setattr(
        mcp_proxy_session, "_settings", SimpleNamespace(mcp_tool_output_max_chars=200)
    )
    proxy = object.__new__(mcp_proxy_session.MCPProxySession)
    result = _result(b"abc")
    result["content"].append(_result(b"def")["content"][1])
    assert proxy._truncate_tool_result(result) is result
    result["content"].append(_result(b"g")["content"][1])
    rejected = proxy._truncate_tool_result(result)
    assert rejected["is_error"]
    assert (
        rejected["content"][0]["text"]
        == "Tool image output exceeds the binary size limit"
    )


def test_text_truncation_preview_never_contains_image_data(monkeypatch):
    monkeypatch.setattr(
        mcp_proxy_session, "_settings", SimpleNamespace(mcp_tool_output_max_chars=200)
    )
    result = _result(b"private image bytes")
    # Put the image first so it would enter the preview if mistakenly serialized.
    result["content"].reverse()
    result["content"][1]["text"] = "x" * 1000
    proxy = object.__new__(mcp_proxy_session.MCPProxySession)
    rejected = proxy._truncate_tool_result(result)
    serialized = str(rejected)
    assert result["content"][0]["data"] not in serialized
    assert "partial_data_preview" in serialized
    assert image_content.image_message(rejected, "call_large_text") is None


def test_regular_text_result_is_unchanged(monkeypatch):
    monkeypatch.setattr(
        mcp_proxy_session, "_settings", SimpleNamespace(mcp_tool_output_max_chars=200)
    )
    result = {"content": [{"type": "text", "text": "tool-ok"}], "is_error": False}
    proxy = object.__new__(mcp_proxy_session.MCPProxySession)
    assert proxy._truncate_tool_result(result) is result
    assert image_content.image_message(result, "call_text") is None


@pytest.mark.parametrize(
    "content", [[None], ["not a content block"], {"type": "image"}, 7]
)
def test_malformed_content_becomes_an_explicit_tool_error(content, monkeypatch):
    monkeypatch.setattr(
        mcp_proxy_session, "_settings", SimpleNamespace(mcp_tool_output_max_chars=200)
    )
    proxy = object.__new__(mcp_proxy_session.MCPProxySession)
    rejected = proxy._truncate_tool_result({"content": content, "is_error": False})
    assert rejected == {
        "content": [{"type": "text", "text": "Tool returned malformed content"}],
        "is_error": True,
    }
    assert image_content.image_message(rejected, "call_malformed") is None

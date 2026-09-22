"""Image evidence reaches compatible model requests without entering tool text."""

import copy
import json
from dataclasses import asdict
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import httpx
import pytest

from intric.ai_models.completion_models.completion_model import (
    Context,
    Message,
    ResponseType,
)
from intric.completion_models.infrastructure.adapters.tenant_model_adapter import (
    TenantModelAdapter,
)
from intric.mcp_servers.infrastructure.tool_approval import (
    ToolApprovalDecision,
    ToolApprovalWaitResult,
)
from tests.unit.test_tenant_model_adapter_iterate_stream import (
    _AsyncChunkStream,
    _collect,
    _FakeMCPProxy,
    _make_adapter,
    _make_completion_adapter,
    _text_chunk,
    _tool_call_chunk,
)


@pytest.fixture
def adapter_log():
    with patch(
        "intric.completion_models.infrastructure.adapters.tenant_model_adapter.logger"
    ) as logger:
        yield logger


def _image_result(mime="image/jpeg"):
    return {
        "content": [
            {"type": "text", "text": '{"camera_heading": null}'},
            {"type": "image", "mime_type": mime, "data": "aW1hZ2U="},
        ],
        "is_error": False,
    }


def _tool_call(call_id):
    return {
        "id": call_id,
        "type": "function",
        "function": {"name": "server__tool", "arguments": '{"q":"x"}'},
    }


def _configure_compatible_transport(adapter):
    # Select the existing native compatible-endpoint transport/history path.
    adapter.provider_type = "openrouter"
    adapter.litellm_model = f"{adapter.provider_type}/test-model"
    return {
        "api_key": "unit-test-only-key",
        "api_base": "https://compatible-endpoint.test/v1",
    }


def _assert_evidence_after_tools(messages, expected_ids):
    assistant_index = next(i for i, msg in enumerate(messages) if msg.get("tool_calls"))
    tool_count = len(messages[assistant_index]["tool_calls"])
    replies = messages[assistant_index + 1 : assistant_index + 1 + tool_count]
    assert all(msg["role"] == "tool" for msg in replies)
    assert {msg["tool_call_id"] for msg in replies} == {
        tc["id"] for tc in messages[assistant_index]["tool_calls"]
    }
    evidence = messages[assistant_index + 1 + tool_count :]
    assert len(evidence) == len(expected_ids)
    for message, call_id in zip(evidence, expected_ids):
        assert message["role"] == "user"
        assert call_id in message["content"][0]["text"]
        assert message["content"][1]["type"] == "image_url"
        assert message["content"][1]["image_url"]["detail"] == "high"
    assert "aW1hZ2U=" not in json.dumps(replies)
    return replies, evidence


def _assert_history_replays(adapter, history, expected_messages):
    # Exercise JSON persistence and the next user turn without connecting a DB.
    persisted = json.loads(json.dumps(history))
    context = Context(
        input="Inspect the same images again",
        messages=[
            Message(question="hello", answer="visible", provider_history=persisted)
        ],
    )
    replay = TenantModelAdapter._create_messages_from_context(adapter, context)
    assert replay[1:-1] == expected_messages
    assert replay[-1] == {"role": "user", "content": context.input}


@pytest.mark.asyncio
async def test_non_streaming_image_evidence_reaches_sdk_payload_and_history(
    adapter_log,
):
    adapter = _make_completion_adapter()
    adapter._prepare_kwargs.return_value = _configure_compatible_transport(adapter)
    adapter._merge_mcp_tools.return_value = [
        {
            "type": "function",
            "function": {
                "name": "server__tool",
                "parameters": {
                    "type": "object",
                    "properties": {"q": {"type": "string"}},
                },
            },
        }
    ]
    proxy = _FakeMCPProxy()
    proxy.call_tools_parallel = AsyncMock(
        return_value=[_image_result(), _image_result("image/png")]
    )
    requests = []

    async def send(client, request, **kwargs):
        assert (
            str(request.url) == "https://compatible-endpoint.test/v1/chat/completions"
        )
        body = json.loads(request.content)
        requests.append(body)
        message = (
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [_tool_call("call_photo_1"), _tool_call("call_photo_2")],
            }
            if len(requests) == 1
            else {"role": "assistant", "content": "visible"}
        )
        return httpx.Response(
            200,
            request=request,
            json={
                "id": "completion_test",
                "object": "chat.completion",
                "created": 0,
                "model": "test-model",
                "choices": [
                    {
                        "index": 0,
                        "message": message,
                        "finish_reason": "tool_calls" if len(requests) == 1 else "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 2,
                    "total_tokens": 12,
                },
            },
        )

    # Keep the real SDK request serialization/response parsing; intercept only HTTP.
    with patch.object(httpx.AsyncClient, "send", autospec=True, side_effect=send):
        completion = await adapter.get_response(
            context=SimpleNamespace(), model_kwargs={}, mcp_proxy=proxy
        )

    assert len(requests) == 2
    assert completion.text == "visible"
    replies, evidence = _assert_evidence_after_tools(
        requests[1]["messages"], ["call_photo_1", "call_photo_2"]
    )
    assert [reply["content"] for reply in replies] == ['{"camera_heading": null}'] * 2
    assert [msg["content"][1]["image_url"]["url"] for msg in evidence] == [
        "data:image/jpeg;base64,aW1hZ2U=",
        "data:image/png;base64,aW1hZ2U=",
    ]
    history = completion.provider_history
    assert history["messages"][:-1] == requests[1]["messages"][1:]
    _assert_history_replays(adapter, history, history["messages"])
    assert adapter_log.info.called
    assert "aW1hZ2U=" not in str(adapter_log.mock_calls)


@pytest.mark.asyncio
async def test_streaming_images_follow_approved_and_denied_replies_in_sdk_payload(
    adapter_log,
):
    adapter = _make_adapter()
    transport_kwargs = _configure_compatible_transport(adapter)
    proxy = _FakeMCPProxy()
    proxy.call_tools_parallel = AsyncMock(
        return_value=[_image_result(), _image_result("image/webp")]
    )
    approval_manager = AsyncMock()
    approval_manager.wait_for_approval.return_value = ToolApprovalWaitResult(
        decisions=[
            ToolApprovalDecision(tool_call_id="call_photo_1", approved=True),
            ToolApprovalDecision(
                tool_call_id="call_denied", approved=False, reason="Skip"
            ),
            ToolApprovalDecision(tool_call_id="call_photo_2", approved=True),
        ],
        timed_out=False,
    )
    chunk = _tool_call_chunk(tool_call_id="call_photo_1")
    for index, call_id in enumerate(["call_denied", "call_photo_2"], start=1):
        tc = _tool_call_chunk(tool_call_id=call_id).choices[0].delta.tool_calls[0]
        tc.index = index
        chunk.choices[0].delta.tool_calls.append(tc)
    stream = _AsyncChunkStream(
        [chunk],
        eneo_context={
            "mcp_proxy": proxy,
            "messages": [{"role": "user", "content": "hello"}],
            "kwargs": transport_kwargs,
            "has_tools": True,
        },
    )
    requests = []

    async def send(client, request, **kwargs):
        assert (
            str(request.url) == "https://compatible-endpoint.test/v1/chat/completions"
        )
        requests.append(json.loads(request.content))
        event = {
            "id": "completion_test",
            "object": "chat.completion.chunk",
            "created": 0,
            "model": "test-model",
            "choices": [
                {"index": 0, "delta": {"content": "visible"}, "finish_reason": "stop"}
            ],
        }
        return httpx.Response(
            200,
            request=request,
            headers={"content-type": "text/event-stream"},
            content=f"data: {json.dumps(event)}\n\ndata: [DONE]\n\n".encode(),
        )

    with patch.object(httpx.AsyncClient, "send", autospec=True, side_effect=send):
        output = await _collect(
            adapter,
            stream,
            require_tool_approval=True,
            approval_manager=approval_manager,
            approval_context={
                "tenant_id": uuid4(),
                "user_id": uuid4(),
                "session_id": uuid4(),
                "assistant_id": uuid4(),
            },
            pending_approval_ids=set(),
        )

    assert len(requests) == 1
    assert requests[0]["stream"] is True
    replies, evidence = _assert_evidence_after_tools(
        requests[0]["messages"], ["call_photo_1", "call_photo_2"]
    )
    denied = next(msg for msg in replies if msg["tool_call_id"] == "call_denied")
    assert json.loads(denied["content"]) == {"denied": True, "user_reason": "Skip"}
    assert (
        evidence[1]["content"][1]["image_url"]["url"]
        == "data:image/webp;base64,aW1hZ2U="
    )
    proxy.call_tools_parallel.assert_awaited_once_with(
        [
            ("server__tool", {"q": "x"}),
            ("server__tool", {"q": "x"}),
        ]
    )
    assert "".join(event.text or "" for event in output) == "visible"
    assert not any(event.response_type == ResponseType.ERROR for event in output)
    result_metadata = [
        metadata
        for event in output
        for metadata in event.tool_calls_metadata or []
        if metadata.result is not None
    ]
    assert {metadata.result_status for metadata in result_metadata} == {
        "succeeded",
        "denied",
    }
    assert "aW1hZ2U=" not in json.dumps(
        [asdict(metadata) for metadata in result_metadata]
    )
    assert adapter_log.info.called
    assert "aW1hZ2U=" not in str(adapter_log.mock_calls)
    history = output[-1].provider_history
    assert history["messages"][:-1] == requests[0]["messages"][1:]
    _assert_history_replays(adapter, history, history["messages"])


@pytest.mark.asyncio
async def test_image_evidence_is_retained_across_followup_tool_rounds():
    adapter = _make_adapter()
    proxy = _FakeMCPProxy()
    proxy.call_tools_parallel = AsyncMock(
        side_effect=[
            [_image_result()],
            [
                {
                    "content": [{"type": "text", "text": "source location"}],
                    "is_error": False,
                }
            ],
        ]
    )
    stream = _AsyncChunkStream(
        [_tool_call_chunk()],
        eneo_context={
            "mcp_proxy": proxy,
            "messages": [],
            "kwargs": {},
            "has_tools": True,
        },
    )
    requests = []
    followups = iter(
        [
            _AsyncChunkStream([_tool_call_chunk(tool_call_id="call_2")]),
            _AsyncChunkStream([_text_chunk("visible", "stop")]),
        ]
    )

    async def followup(**kwargs):
        requests.append(copy.deepcopy(kwargs["messages"]))
        return next(followups)

    with patch(
        "intric.completion_models.infrastructure.adapters.tenant_model_adapter._acompletion_call",
        side_effect=followup,
    ):
        output = await _collect(adapter, stream, require_tool_approval=False)
    assert len(requests) == 2
    assert requests[1][: len(requests[0])] == requests[0]
    assert [msg["role"] for msg in requests[1]] == [
        "assistant",
        "tool",
        "user",
        "assistant",
        "tool",
    ]
    assert output[-1].stop
    assert "".join(event.text or "" for event in output) == "visible"

import copy
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

from sqlalchemy.dialects import postgresql

from intric.ai_models.completion_models.completion_model import (
    Context,
    Message,
    ModelKwargs,
)
from intric.completion_models.infrastructure.adapters.openrouter_client import (
    merge_reasoning_details,
)
from intric.completion_models.infrastructure.adapters.tenant_model_adapter import (
    TenantModelAdapter,
)
from intric.questions.questions_repo import QuestionRepository
from tests.unit.test_tenant_model_adapter_iterate_stream import (
    _AsyncChunkStream,
    _FakeMCPProxy,
    _make_adapter,
    _text_chunk,
    _tool_call_chunk,
)


def test_reasoning_fragments_preserve_opaque_fields_and_order():
    details = []
    first = {
        "index": 0,
        "type": "reasoning.text",
        "text": "part ",
        "signature": "signed",
        "id": "r1",
    }
    merge_reasoning_details(details, [first])
    merge_reasoning_details(
        details,
        [
            {"index": 0, "text": "two"},
            {"index": 1, "type": "reasoning.encrypted", "data": "opaque"},
        ],
    )
    assert details == [
        {**first, "text": "part two"},
        {"index": 1, "type": "reasoning.encrypted", "data": "opaque"},
    ]
    assert first["text"] == "part "


def test_routing_and_reasoning_config_reaches_transport():
    config = {
        "endpoint": "https://openrouter.ai/api/v1",
        "extra_body": {
            "provider": {"only": ["together"], "allow_fallbacks": False},
            "reasoning": {"enabled": True},
        },
    }
    resolver = Mock()
    resolver.get_api_key.return_value = "test-key"
    resolver.get_credential_field.side_effect = lambda field: config.get(field)
    adapter = TenantModelAdapter(
        SimpleNamespace(
            provider_id=uuid4(),
            name="thinkingmachines/inkling",
            max_input_tokens=524288,
            max_output_tokens=471859,
        ),
        resolver,
        "openrouter",
    )
    params = adapter._prepare_kwargs(ModelKwargs())
    assert params["extra_body"] == config["extra_body"]
    assert params["max_tokens"] == 471859
    assert params["context_window"] == 524288


async def test_stream_tool_round_reasoning_persists_and_replays_exactly():
    adapter = _make_adapter()
    adapter.provider_type = "openrouter"
    adapter.litellm_model = "openrouter/thinkingmachines/inkling"
    proxy = _FakeMCPProxy()
    tool = _tool_call_chunk()
    tool.choices[0].delta.reasoning_details = [
        {"index": 0, "type": "reasoning.encrypted", "data": "opaque-tool"}
    ]
    final = _text_chunk("Done", "stop")
    final.choices[0].delta.reasoning_details = [
        {
            "index": 0,
            "type": "reasoning.text",
            "text": "final reason",
            "signature": "signature",
        }
    ]
    messages = [{"role": "user", "content": "hello"}]
    initial = _AsyncChunkStream(
        [tool],
        {"messages": messages, "kwargs": {}, "mcp_proxy": proxy, "has_tools": True},
    )
    requests = []

    async def follow_up(**kwargs):
        requests.append(copy.deepcopy(kwargs["messages"]))
        return _AsyncChunkStream([final])

    with patch(
        "intric.completion_models.infrastructure.adapters.tenant_model_adapter._acompletion_call",
        side_effect=follow_up,
    ):
        chunks = [chunk async for chunk in adapter.iterate_stream(initial)]
    history = chunks[-1].provider_history
    assert (
        requests[0][1]["reasoning_details"] == tool.choices[0].delta.reasoning_details
    )
    assert [m["role"] for m in history["messages"]] == [
        "assistant",
        "tool",
        "assistant",
    ]
    assert (
        history["messages"][-1]["reasoning_details"]
        == final.choices[0].delta.reasoning_details
    )
    session = AsyncMock()
    await QuestionRepository(session).update_with_answer(
        question_id=uuid4(), tenant_id=uuid4(), answer="Done", provider_history=history
    )
    persisted = (
        session.execute.await_args.args[0]
        .compile(dialect=postgresql.dialect())
        .params["provider_history"]
    )
    context = Context(
        input="Check again",
        messages=[Message(question="hello", answer="Done", provider_history=persisted)],
    )
    replay = adapter._create_messages_from_context(context)
    assert replay[1:-1] == history["messages"]
    adapter.litellm_model = "openai/other-model"
    assert adapter._create_messages_from_context(context)[1] == {
        "role": "assistant",
        "content": "Done",
    }


async def test_openrouter_transport_forwards_native_fields_and_closes_client():
    from intric.completion_models.infrastructure.adapters.openrouter_client import (
        completion,
    )

    client = AsyncMock()
    client.chat.completions.create.return_value = SimpleNamespace(choices=[])
    messages = [
        {
            "role": "assistant",
            "content": "answer",
            "reasoning_details": [{"type": "reasoning.encrypted", "data": "opaque"}],
        }
    ]
    body = {
        "provider": {"only": ["together"], "allow_fallbacks": False},
        "reasoning": {"enabled": True},
    }
    with patch(
        "intric.completion_models.infrastructure.adapters.openrouter_client.openai.AsyncOpenAI",
        return_value=client,
    ):
        await completion(
            model="openrouter/thinkingmachines/inkling",
            api_key="test-key",
            messages=messages,
            extra_body=body,
            stream=False,
            drop_params=True,
        )
    params = client.chat.completions.create.await_args.kwargs
    assert params["messages"] == messages
    assert params["extra_body"] == body
    assert params["model"] == "thinkingmachines/inkling"
    assert "drop_params" not in params
    client.close.assert_awaited_once()

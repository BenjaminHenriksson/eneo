import json
from uuid import uuid4

import pytest

from intric.ai_models.completion_models.completion_model import (
    Completion,
    ResponseType,
    TokenUsage,
    ToolCallMetadata,
)
from intric.assistants.api.assistant_protocol import to_sse_response


def test_token_usage_sse_exposes_context_separately_from_cumulative_spend():
    event = to_sse_response(
        Completion(
            response_type=ResponseType.TOKEN_USAGE,
            usage=TokenUsage(
                prompt_tokens=93000,
                completion_tokens=800,
                context_prompt_tokens=32000,
                context_completion_tokens=500,
            ),
        ),
        uuid4(),
    )
    payload = json.loads(event.data)
    assert payload["usage"] == {
        "prompt_tokens": 93000,
        "completion_tokens": 800,
        "turn_tokens": 93800,
        "context_prompt_tokens": 32000,
        "context_completion_tokens": 500,
    }


def test_tool_call_sse_preserves_null_tool_call_id():
    event = to_sse_response(
        Completion(
            response_type=ResponseType.TOOL_CALL,
            tool_calls_metadata=[
                ToolCallMetadata(
                    server_name="mcp",
                    tool_name="search",
                    tool_call_id=None,
                )
            ],
        ),
        uuid4(),
    )

    payload = json.loads(event.data)

    assert payload["tools"][0]["tool_call_id"] is None


def test_tool_approval_sse_requires_real_approval_id():
    with pytest.raises(ValueError, match="approval_id"):
        to_sse_response(
            Completion(
                response_type=ResponseType.TOOL_APPROVAL_REQUIRED,
                approval_id=None,
                tool_calls_metadata=[],
            ),
            uuid4(),
        )

"""OpenRouter transport that retains provider-native reasoning_details."""

from typing import Any

import litellm
import openai


class OpenRouterStream:
    def __init__(self, stream, client):
        self.stream = stream
        self.client = client

    async def __aiter__(self):
        try:
            async for chunk in self.stream:
                yield chunk
        finally:
            await self.stream.close()
            await self.client.close()


async def completion(**kwargs: Any):
    # Eneo's pinned LiteLLM version discards OpenRouter reasoning_details.
    # Use the same OpenAI protocol without that lossy conversion.
    kwargs.pop("drop_params", None)
    kwargs["model"] = kwargs["model"].removeprefix("openrouter/")
    if "top_k" in kwargs:
        kwargs["extra_body"] = {
            **kwargs.get("extra_body", {}),
            "top_k": kwargs.pop("top_k"),
        }
    context_window = kwargs.pop("context_window", None)
    if context_window and kwargs.get("max_tokens"):
        prompt_tokens = litellm.token_counter(
            model="gpt-4o", messages=kwargs["messages"], tools=kwargs.get("tools")
        )
        # token_counter does not include OpenRouter's opaque reasoning state.
        for message in kwargs["messages"]:
            for detail in message.get("reasoning_details", []):
                for field in ("text", "summary", "data"):
                    if detail.get(field):
                        prompt_tokens += litellm.token_counter(
                            model="gpt-4o", text=detail[field]
                        )
        kwargs["max_tokens"] = min(
            kwargs["max_tokens"], max(1, context_window - prompt_tokens)
        )
    client = openai.AsyncOpenAI(
        api_key=kwargs.pop("api_key"),
        base_url=kwargs.pop("api_base", "https://openrouter.ai/api/v1"),
    )
    try:
        response = await client.chat.completions.create(**kwargs)
    except BaseException:
        await client.close()
        raise
    if kwargs.get("stream"):
        return OpenRouterStream(response, client)
    await client.close()
    return response


def merge_reasoning_details(accumulated: list[dict], deltas: list[dict]) -> None:
    """Join streamed fragments without dropping IDs, signatures, or opaque data."""
    for delta in deltas:
        index = delta.get("index")
        target = next(
            (
                item
                for item in accumulated
                if index is not None and item.get("index") == index
            ),
            None,
        )
        if target is None:
            accumulated.append(dict(delta))
            continue
        for key, value in delta.items():
            if key in ("text", "summary", "data") and isinstance(value, str):
                target[key] = target.get(key, "") + value
            elif value is not None:
                target[key] = value

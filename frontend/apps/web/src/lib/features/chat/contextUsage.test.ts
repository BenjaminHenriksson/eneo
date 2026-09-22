import { describe, expect, it } from "vitest";
import { getContextSnapshot } from "./contextUsage";

describe("context usage after tool rounds", () => {
  it("uses the latest request for headroom while preserving cumulative usage", () => {
    const message = {
      num_tokens_question: 93000,
      num_tokens_answer: 800,
      context_tokens_question: 32000,
      context_tokens_answer: 500,
      tool_calls: [{ tool_call_id: "call_1" }, { tool_call_id: "call_2" }]
    };
    const snapshot = getContextSnapshot(message)!;
    expect(snapshot).toEqual({ input: 32000, output: 500 });
    expect(snapshot.input + snapshot.output + 100).toBeLessThan(65280);
    expect(message.num_tokens_question + message.num_tokens_answer).toBe(93800);
    // The same persisted fields must survive reload from conversation history.
    expect(getContextSnapshot(JSON.parse(JSON.stringify(message)))).toEqual(snapshot);
  });

  it("preserves zero counts instead of falling back to cumulative totals", () => {
    expect(getContextSnapshot({ num_tokens_question: 90000, context_tokens_question: 0, context_tokens_answer: 0 }))
      .toEqual({ input: 0, output: 0 });
  });

  it("does not use cumulative counts for legacy tool conversations", () => {
    expect(getContextSnapshot({ num_tokens_question: 90000, tool_calls: [{}] })).toBeNull();
    expect(getContextSnapshot({ num_tokens_question: 90000, mcp_tool_calls: [{}] })).toBeNull();
  });

  it("retains legacy non-tool usage and genuine context exhaustion", () => {
    expect(getContextSnapshot({ num_tokens_question: 64000, num_tokens_answer: 1500 }))
      .toEqual({ input: 64000, output: 1500 });
    const snapshot = getContextSnapshot({ context_tokens_question: 64000, context_tokens_answer: 1500 })!;
    expect(snapshot.input + snapshot.output).toBeGreaterThan(65280);
  });
});

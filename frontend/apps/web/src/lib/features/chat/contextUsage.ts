export type ContextTokenUsage = {
  prompt_tokens: number;
  completion_tokens: number;
  context_prompt_tokens?: number | null;
  context_completion_tokens?: number | null;
};

type ContextMessage = {
  num_tokens_question?: number;
  num_tokens_answer?: number;
  context_tokens_question?: number | null;
  context_tokens_answer?: number | null;
  tool_calls?: unknown[] | null;
  mcp_tool_calls?: unknown[] | null;
};

/** Context occupancy is a snapshot, not the sum of repeated model requests. */
export function getContextSnapshot(message: ContextMessage) {
  if (message.context_tokens_question != null && message.context_tokens_answer != null) {
    return { input: message.context_tokens_question, output: message.context_tokens_answer };
  }
  // Old MCP messages have cumulative counts but no recoverable snapshot.
  // Do not misrepresent those counts or prevent the next request based on them.
  if (message.tool_calls?.length || message.mcp_tool_calls?.length) return null;
  return { input: message.num_tokens_question ?? 0, output: message.num_tokens_answer ?? 0 };
}

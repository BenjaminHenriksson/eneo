export type ToolArtifact = {
  kind: "map" | "export" | "citation";
  url: string;
  title?: string;
  format?: string;
  expiresHours?: number;
};

function record(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function safeUrl(value: unknown): value is string {
  if (typeof value !== "string") return false;
  try {
    const url = new URL(value);
    return ["https:", "http:"].includes(url.protocol) && !url.username && !url.password;
  } catch {
    return false;
  }
}

/** Read artifact contracts from completed tools, never from model-generated prose. */
export function getToolArtifacts(toolCalls: unknown): ToolArtifact[] {
  if (!Array.isArray(toolCalls)) return [];
  const artifacts = new Map<string, ToolArtifact>();
  function add(artifact: ToolArtifact) {
    if (safeUrl(artifact.url)) artifacts.set(`${artifact.kind}:${artifact.url}`, artifact);
  }

  for (const call of toolCalls) {
    if (!record(call) || call.approved === false || call.result_status !== "succeeded") continue;
    let result: unknown = call.result;
    if (typeof result === "string") {
      try {
        result = JSON.parse(result);
      } catch {
        continue;
      }
    }
    if (!record(result) || result.error || !safeUrl(result.url)) continue;

    if (call.tool_name === "map" && typeof result.view_id === "string") {
      const title = record(call.arguments) ? call.arguments.title : undefined;
      add({ kind: "map", url: result.url, title: typeof title === "string" ? title : undefined });
    } else if (call.tool_name === "export" && result.status === "done" && result.job_id != null) {
      add({
        kind: "export",
        url: result.url,
        format: typeof result.format === "string" ? result.format.toUpperCase() : undefined,
        expiresHours:
          typeof result.expires_hours === "number" && result.expires_hours > 0
            ? result.expires_hours
            : undefined
      });
      if (safeUrl(result.sidecar_url)) add({ kind: "citation", url: result.sidecar_url });
    }
  }
  return [...artifacts.values()];
}

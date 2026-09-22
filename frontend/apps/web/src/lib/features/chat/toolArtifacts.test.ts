import { describe, expect, it } from "vitest";
import { getToolArtifacts } from "./toolArtifacts";

const map = {
  tool_name: "map",
  approved: true,
  result_status: "succeeded",
  arguments: { title: "Byggnader i strandskydd" },
  result: JSON.stringify({ view_id: "v_123", url: "https://geodata.example/v/v_123" })
};
const exportUrl = "https://geodata.example/export.gpkg?X-Amz-Credential=a%2Fb&X-Amz-Signature=abc";
const exportCall = {
  tool_name: "export",
  approved: true,
  result_status: "succeeded",
  result: JSON.stringify({
    job_id: 10,
    status: "done",
    url: exportUrl,
    format: "gpkg",
    expires_hours: 24,
    sidecar_url: "https://geodata.example/export.citation.md?signature=def"
  })
};

describe("structured tool artifacts", () => {
  it("keeps exact tool URLs independent of malformed model prose, live and after reload", () => {
    const message = {
      answer: "https://geodata.example/v/v_123Den visar byggnader.",
      mcp_tool_calls: [map, exportCall]
    };
    const live = getToolArtifacts(message.mcp_tool_calls);
    const saved = JSON.parse(JSON.stringify({ tool_calls: message.mcp_tool_calls }));
    expect(getToolArtifacts(saved.tool_calls)).toEqual(live);
    expect(live).toEqual([
      { kind: "map", url: "https://geodata.example/v/v_123", title: "Byggnader i strandskydd" },
      { kind: "export", url: exportUrl, format: "GPKG", expiresHours: 24 },
      { kind: "citation", url: "https://geodata.example/export.citation.md?signature=def" }
    ]);
  });

  it("deduplicates repeated artifacts and accepts decoded results", () => {
    expect(getToolArtifacts([map, map, { ...map, result: JSON.parse(map.result) }])).toHaveLength(
      1
    );
  });

  it.each(["failed", "denied", "timeout_denied", "approved", undefined])(
    "does not promote %s tool calls to working artifacts",
    (result_status) => {
      expect(getToolArtifacts([{ ...map, result_status }])).toEqual([]);
    }
  );

  it("ignores missing, malformed, pending, denied, error and unrelated results", () => {
    expect(getToolArtifacts(undefined)).toEqual([]);
    expect(
      getToolArtifacts([
        null,
        {},
        { ...map, approved: false },
        { ...map, result: "not JSON" },
        { ...map, result: "null" },
        { ...map, result: "[]" },
        { ...map, result: { view_id: "v_123", url: "https://example.com", error: "failed" } },
        { ...exportCall, result: { job_id: 10, status: "running", url: exportUrl } },
        { ...map, tool_name: "search" }
      ])
    ).toEqual([]);
  });

  it.each([
    "javascript:alert(1)",
    "data:text/html,test",
    "/relative",
    "//example.com",
    "https://user:password@example.com"
  ])("rejects unsafe or ambiguous URLs: %s", (url) => {
    expect(getToolArtifacts([{ ...map, result: { view_id: "v_123", url } }])).toEqual([]);
    expect(
      getToolArtifacts([
        { ...exportCall, result: { job_id: 10, status: "done", url: exportUrl, sidecar_url: url } }
      ])
    ).toHaveLength(1);
  });
});

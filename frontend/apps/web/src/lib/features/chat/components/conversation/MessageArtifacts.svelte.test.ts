import { page } from "@vitest/browser/context";
import { render } from "vitest-browser-svelte";
import { expect, it } from "vitest";
import { m } from "$lib/paraglide/messages";
import MessageArtifacts from "./MessageArtifacts.svelte";

it("renders usable links from saved results with exact signatures and escaped titles", async () => {
  const exportUrl = "https://example.com/export.gpkg?credential=a%2Fb&signature=123";
  render(MessageArtifacts, {
    toolCalls: [
      {
        tool_name: "map",
        result_status: "succeeded",
        arguments: { title: "<b>Buildings</b>" },
        result: JSON.stringify({ view_id: "v_1", url: "https://example.com/v/v_1" })
      },
      {
        tool_name: "export",
        result_status: "succeeded",
        result: JSON.stringify({
          job_id: 10,
          status: "done",
          url: exportUrl,
          format: "gpkg",
          expires_hours: 24
        })
      }
    ]
  });
  const map = page.getByRole("link", { name: `${m.chat_open_map()}: <b>Buildings</b>` });
  await expect.element(map).toHaveAttribute("href", "https://example.com/v/v_1");
  await expect.element(map).toHaveAttribute("rel", "noopener noreferrer");
  const download = page.getByRole("link", { name: `${m.chat_download_export()} (GPKG)` });
  await expect.element(download).toHaveAttribute("href", exportUrl);
  await expect.element(page.getByText(m.chat_export_expiry({ hours: 24 }))).toBeVisible();
});

it("does not show a results panel for failed tools", async () => {
  render(MessageArtifacts, {
    toolCalls: [{ tool_name: "map", result_status: "failed", result: "{}" }]
  });
  await expect.element(page.getByRole("navigation")).not.toBeInTheDocument();
});

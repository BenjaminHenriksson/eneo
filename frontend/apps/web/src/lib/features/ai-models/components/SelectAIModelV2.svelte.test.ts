import { page } from "@vitest/browser/context";
import { render } from "vitest-browser-svelte";
import { expect, it } from "vitest";
import type { CompletionModel } from "@intric/intric-js";
import SelectAIModelV2 from "./SelectAIModelV2.svelte";

it("shows display names without connection metadata and still selects models", async () => {
  const model = {
    id: "model-a",
    name: "private-route/checkpoint",
    nickname: "Gemma",
    description: "Private endpoint details",
    provider_id: "connection-a",
    provider_name: "Private connection",
    provider_type: "custom",
    input_cost_per_token: "0.000001",
    output_cost_per_token: "0.000002"
  } as unknown as CompletionModel;
  const other = { ...model, id: "model-b", nickname: "Second model" };
  render(SelectAIModelV2, {
    availableModels: [model, other],
    selectedModel: model
  });
  const trigger = page.getByRole("combobox");
  await trigger.click();
  await expect.element(page.getByRole("option", { name: "Gemma", exact: true })).toBeVisible();
  await expect.element(page.getByText("Private connection")).not.toBeInTheDocument();
  await expect.element(page.getByText("Private endpoint details")).not.toBeInTheDocument();
  await expect.element(page.getByText("private-route/checkpoint")).not.toBeInTheDocument();
  await expect
    .element(page.getByRole("listbox").getByRole("img", { name: "custom", exact: true }))
    .not.toBeInTheDocument();
  await expect.element(page.getByRole("listbox").getByRole("button")).not.toBeInTheDocument();
  await page.getByRole("option", { name: "Second model", exact: true }).click();
  await expect.element(trigger).toHaveTextContent("Second model");
});

it("uses the display name when the selected model is unavailable", async () => {
  const selected = {
    id: "retired",
    name: "private-route/retired",
    nickname: "Retired model"
  } as CompletionModel;
  render(SelectAIModelV2, { availableModels: [], selectedModel: selected });
  await expect.element(page.getByRole("combobox")).toHaveTextContent("Retired model");
  await expect
    .element(page.getByText("private-route/retired", { exact: false }))
    .not.toBeInTheDocument();
});

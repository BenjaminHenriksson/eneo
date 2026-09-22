<script lang="ts">
  import { m } from "$lib/paraglide/messages";
  import { getToolArtifacts } from "../../toolArtifacts";

  let { toolCalls }: { toolCalls: unknown } = $props();
  const artifacts = $derived(getToolArtifacts(toolCalls));
</script>

{#if artifacts.length}
  <nav
    aria-label={m.chat_tool_results()}
    class="border-default bg-secondary mb-5 rounded-lg border p-4"
  >
    <p class="mb-3 text-sm font-medium">{m.chat_tool_results()}</p>
    <ul class="flex flex-col gap-3 text-base">
      {#each artifacts as artifact (`${artifact.kind}:${artifact.url}`)}
        <li>
          <!-- eslint-disable svelte/no-navigation-without-resolve -- validated external tool URL -->
          <a
            href={artifact.url}
            target="_blank"
            rel="noopener noreferrer"
            class="text-accent-default font-medium underline underline-offset-4"
          >
            {#if artifact.kind === "map"}
              {m.chat_open_map()}{artifact.title ? `: ${artifact.title}` : ""}
            {:else if artifact.kind === "export"}
              {m.chat_download_export()}{artifact.format ? ` (${artifact.format})` : ""}
            {:else}
              {m.chat_export_citation()}
            {/if}
          </a>
          <!-- eslint-enable svelte/no-navigation-without-resolve -->
          {#if artifact.expiresHours}
            <p class="text-muted mt-1 text-sm">
              {m.chat_export_expiry({ hours: artifact.expiresHours })}
            </p>
          {/if}
        </li>
      {/each}
    </ul>
  </nav>
{/if}

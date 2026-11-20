import type { ChatItem } from "./types";
import { downloadFile } from "./utils";

function stamp(): string {
  return new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19);
}

export function exportJson(sessionId: string, items: ChatItem[]): void {
  const messages = items
    .filter((i) => i.kind !== "error")
    .map((i) =>
      i.kind === "user" ? { role: "user", content: i.content } : { role: "assistant", content: i.content, metadata: i.kind === "assistant" ? i.metadata : undefined },
    );
  const payload = { session_id: sessionId, exported_at: new Date().toISOString(), messages };
  downloadFile(`chat-${sessionId}-${stamp()}.json`, JSON.stringify(payload, null, 2), "application/json");
}

export function exportMarkdown(sessionId: string, items: ChatItem[]): void {
  const lines = [`# Chat ${sessionId}`, "", `_Exported ${new Date().toLocaleString()}_`, ""];
  for (const i of items) {
    if (i.kind === "user") {
      lines.push("## You", "", i.content, "");
    } else if (i.kind === "assistant") {
      const m = i.metadata;
      lines.push(
        "## Assistant",
        "",
        i.content,
        "",
        `> ${m.resolution_source} · ${m.model} · ${m.latency_ms} ms · in ${m.input_tokens} / out ${m.output_tokens} tokens · key ${m.key_id ?? "none"} · fallbacks ${m.fallback_attempts}`,
        "",
      );
    }
  }
  downloadFile(`chat-${sessionId}-${stamp()}.md`, lines.join("\n"), "text/markdown");
}

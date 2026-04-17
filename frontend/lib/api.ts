export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

export type ChatEvent =
  | { type: "token"; text: string }
  | { type: "tool_call_start"; tool: string; args: unknown }
  | { type: "tool_call_end"; tool: string; output: unknown }
  | { type: "return_updated"; return_draft: unknown; finalized: boolean; pending_clarification: string | null }
  | { type: "error"; message: string }
  | { type: "done" };

export async function createSession(): Promise<{ session_id: string; tax_year: number }> {
  const res = await fetch(`${API_BASE}/sessions`, { method: "POST" });
  if (!res.ok) throw new Error(`createSession failed: ${res.status}`);
  return res.json();
}

export async function uploadDocument(
  sessionId: string,
  file: File,
): Promise<{ document_id: string; filename: string }> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API_BASE}/sessions/${sessionId}/documents`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) throw new Error(`uploadDocument failed: ${res.status}`);
  return res.json();
}

export async function listDocuments(
  sessionId: string,
): Promise<{ documents: { document_id: string; filename: string }[] }> {
  const res = await fetch(`${API_BASE}/sessions/${sessionId}/documents`);
  return res.json();
}

export async function getReturn(sessionId: string): Promise<{
  return_draft: Record<string, unknown> | null;
  finalized: boolean;
  pending_clarification: string | null;
}> {
  const res = await fetch(`${API_BASE}/sessions/${sessionId}/return`);
  return res.json();
}

/** Stream chat events from the backend SSE endpoint. */
export async function* streamChat(
  sessionId: string,
  message: string,
  signal?: AbortSignal,
): AsyncGenerator<ChatEvent> {
  const res = await fetch(`${API_BASE}/sessions/${sessionId}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify({ message }),
    signal,
  });
  if (!res.ok || !res.body) throw new Error(`chat failed: ${res.status}`);

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    buffer = buffer.replace(/\r/g, "");

    // SSE messages are separated by blank lines. Each message is one or more
    // "event: X" / "data: Y" lines.
    let idx: number;
    while ((idx = buffer.indexOf("\n\n")) !== -1) {
      const raw = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      const evt = parseSSEMessage(raw);
      if (evt) yield evt;
    }
  }
}

function parseSSEMessage(raw: string): ChatEvent | null {
  let event = "message";
  let data = "";
  for (const line of raw.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) data += line.slice(5).trim();
  }
  if (!data) return null;
  let parsed: Record<string, unknown> = {};
  try {
    parsed = JSON.parse(data);
  } catch {
    return null;
  }
  switch (event) {
    case "token":
      return { type: "token", text: String(parsed.text ?? "") };
    case "tool_call_start":
      return { type: "tool_call_start", tool: String(parsed.tool), args: parsed.args };
    case "tool_call_end":
      return { type: "tool_call_end", tool: String(parsed.tool), output: parsed.output };
    case "return_updated":
      return {
        type: "return_updated",
        return_draft: parsed.return_draft,
        finalized: Boolean(parsed.finalized),
        pending_clarification: (parsed.pending_clarification as string | null) ?? null,
      };
    case "error":
      return { type: "error", message: String(parsed.message ?? "unknown error") };
    case "done":
      return { type: "done" };
    default:
      return null;
  }
}

"use client";

import { useEffect, useRef, useState } from "react";
import { streamChat } from "@/lib/api";
import { ToolCallEvent, ToolCallTimeline } from "./ToolCallTimeline";

type ChatMessage = {
  role: "user" | "assistant";
  text: string;
};

export function ChatPane({
  sessionId,
  onReturnUpdated,
}: {
  sessionId: string;
  onReturnUpdated: (payload: {
    return_draft: unknown;
    finalized: boolean;
    pending_clarification: string | null;
  }) => void;
}) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [tools, setTools] = useState<ToolCallEvent[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [messages, tools]);

  async function send() {
    const text = input.trim();
    if (!text || sending) return;
    setSending(true);
    setError(null);
    setInput("");
    setMessages((m) => [...m, { role: "user", text }, { role: "assistant", text: "" }]);

    try {
      for await (const evt of streamChat(sessionId, text)) {
        if (evt.type === "token") {
          setMessages((m) => {
            const next = [...m];
            const last = next[next.length - 1];
            if (last?.role === "assistant") {
              next[next.length - 1] = { ...last, text: last.text + evt.text };
            }
            return next;
          });
        } else if (evt.type === "tool_call_start") {
          const id = `${evt.tool}-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`;
          setTools((t) => [
            ...t,
            { id, tool: evt.tool, args: evt.args, status: "running" },
          ]);
        } else if (evt.type === "tool_call_end") {
          setTools((t) => {
            const next = [...t];
            for (let i = next.length - 1; i >= 0; i--) {
              if (next[i].tool === evt.tool && next[i].status === "running") {
                next[i] = {
                  ...next[i],
                  output: evt.output,
                  status:
                    evt.output &&
                    typeof evt.output === "object" &&
                    (evt.output as { ok?: boolean }).ok === false
                      ? "error"
                      : "done",
                };
                break;
              }
            }
            return next;
          });
        } else if (evt.type === "return_updated") {
          onReturnUpdated({
            return_draft: evt.return_draft,
            finalized: evt.finalized,
            pending_clarification: evt.pending_clarification,
          });
          // If the agent asked a clarifying question and produced no text tokens,
          // surface the question as the assistant's chat message.
          if (evt.pending_clarification) {
            setMessages((m) => {
              const next = [...m];
              const last = next[next.length - 1];
              if (last?.role === "assistant" && !last.text) {
                next[next.length - 1] = { ...last, text: evt.pending_clarification! };
              }
              return next;
            });
          }
        } else if (evt.type === "error") {
          setError(evt.message);
        } else if (evt.type === "done") {
          break;
        }
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Stream failed");
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="flex flex-col h-full">
      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto p-4 space-y-4"
      >
        {messages.length === 0 && (
          <div className="text-sm text-[color:var(--muted)]">
            Upload a W-2 above, then tell the agent your filing status. Try: <em>&ldquo;I&apos;m single, no dependents, take the standard deduction.&rdquo;</em>
          </div>
        )}
        {messages.map((m, i) => (
          <div
            key={i}
            className={`text-sm whitespace-pre-wrap ${
              m.role === "user" ? "text-[color:var(--text)]" : "text-[color:var(--muted)]"
            }`}
          >
            <div className="text-xs uppercase mb-1 text-[color:var(--muted)]">
              {m.role}
            </div>
            {m.text || (m.role === "assistant" && sending ? "…" : "")}
          </div>
        ))}
        {tools.length > 0 && (
          <div className="pt-2 border-t border-[color:var(--border)]">
            <div className="text-xs uppercase text-[color:var(--muted)] px-2 pt-2">
              Tool calls
            </div>
            <ToolCallTimeline events={tools} />
          </div>
        )}
        {error && (
          <div className="text-sm text-[color:var(--error)]">Error: {error}</div>
        )}
      </div>
      <div className="border-t border-[color:var(--border)] p-3 flex gap-2">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              void send();
            }
          }}
          disabled={sending}
          placeholder="Ask the agent…"
          className="flex-1 bg-[color:var(--panel)] border border-[color:var(--border)] rounded-md px-3 py-2 text-sm focus:outline-none focus:border-[color:var(--accent)]"
        />
        <button
          onClick={send}
          disabled={sending || !input.trim()}
          className="px-4 py-2 rounded-md bg-[color:var(--accent)] hover:opacity-90 disabled:opacity-50 text-sm"
        >
          {sending ? "…" : "Send"}
        </button>
      </div>
    </div>
  );
}

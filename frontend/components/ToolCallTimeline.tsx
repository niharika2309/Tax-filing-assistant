"use client";

import { useState } from "react";

export type ToolCallEvent = {
  id: string;
  tool: string;
  args?: unknown;
  output?: unknown;
  status: "running" | "done" | "error";
};

export function ToolCallTimeline({ events }: { events: ToolCallEvent[] }) {
  if (events.length === 0) {
    return (
      <div className="text-xs text-[color:var(--muted)] p-4">
        Tool calls will appear here as the agent works.
      </div>
    );
  }
  return (
    <ol className="space-y-2 p-2">
      {events.map((e) => (
        <ToolCallRow key={e.id} e={e} />
      ))}
    </ol>
  );
}

function ToolCallRow({ e }: { e: ToolCallEvent }) {
  const [open, setOpen] = useState(false);
  const statusColor =
    e.status === "done"
      ? "var(--success)"
      : e.status === "error"
        ? "var(--error)"
        : "var(--warning)";
  const errored =
    e.status === "error" ||
    (e.output &&
      typeof e.output === "object" &&
      (e.output as { ok?: boolean }).ok === false);

  return (
    <li className="border border-[color:var(--border)] rounded-md bg-[color:var(--panel)]">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-3 px-3 py-2 text-left text-sm"
      >
        <span
          className="w-2 h-2 rounded-full shrink-0"
          style={{ background: errored ? "var(--error)" : statusColor }}
        />
        <span className="font-mono">{e.tool}</span>
        <span className="ml-auto text-xs text-[color:var(--muted)]">
          {e.status === "running" ? "running…" : open ? "▾" : "▸"}
        </span>
      </button>
      {open && (
        <div className="border-t border-[color:var(--border)] text-xs p-3 space-y-2 font-mono">
          <div>
            <div className="text-[color:var(--muted)] mb-1">args</div>
            <pre className="whitespace-pre-wrap break-all">
              {JSON.stringify(e.args ?? {}, null, 2)}
            </pre>
          </div>
          {e.output !== undefined && (
            <div>
              <div className="text-[color:var(--muted)] mb-1">output</div>
              <pre className="whitespace-pre-wrap break-all">
                {JSON.stringify(e.output, null, 2)}
              </pre>
            </div>
          )}
        </div>
      )}
    </li>
  );
}

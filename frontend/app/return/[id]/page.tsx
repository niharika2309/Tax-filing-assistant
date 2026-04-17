"use client";

import { useEffect, useState } from "react";
import { ChatPane } from "@/components/ChatPane";
import { Form1040Preview } from "@/components/Form1040Preview";
import { UploadDropzone } from "@/components/UploadDropzone";
import { getReturn, listDocuments } from "@/lib/api";

export default function ReturnPage({ params }: { params: { id: string } }) {
  const { id: sessionId } = params;
  const [draft, setDraft] = useState<Record<string, unknown> | null>(null);
  const [finalized, setFinalized] = useState(false);
  const [clarification, setClarification] = useState<string | null>(null);
  const [docs, setDocs] = useState<{ document_id: string; filename: string }[]>([]);

  useEffect(() => {
    void getReturn(sessionId).then((r) => {
      setDraft(r.return_draft);
      setFinalized(r.finalized);
      setClarification(r.pending_clarification);
    });
    void listDocuments(sessionId).then((r) => setDocs(r.documents));
  }, [sessionId]);

  return (
    <main className="h-screen grid grid-cols-[1fr_1fr] divide-x divide-[color:var(--border)]">
      <section className="flex flex-col min-h-0">
        <header className="border-b border-[color:var(--border)] p-3 space-y-3">
          <div className="flex items-center justify-between">
            <h1 className="text-sm">
              Session <span className="font-mono text-xs">{sessionId.slice(0, 8)}</span>
            </h1>
            {clarification && (
              <span className="text-xs text-[color:var(--warning)]">
                Needs clarification
              </span>
            )}
          </div>
          <UploadDropzone
            sessionId={sessionId}
            onUploaded={(doc) => setDocs((d) => [...d, doc])}
          />
          {docs.length > 0 && (
            <div className="text-xs text-[color:var(--muted)] flex flex-wrap gap-2">
              {docs.map((d) => (
                <span
                  key={d.document_id}
                  className="px-2 py-1 rounded bg-[color:var(--panel)] border border-[color:var(--border)]"
                  title={d.document_id}
                >
                  {d.filename}
                </span>
              ))}
            </div>
          )}
          {clarification && (
            <div className="text-xs p-2 rounded bg-[color:var(--panel)] border border-[color:var(--warning)]">
              {clarification}
            </div>
          )}
        </header>
        <div className="flex-1 min-h-0">
          <ChatPane
            sessionId={sessionId}
            onReturnUpdated={(p) => {
              setDraft(p.return_draft as Record<string, unknown>);
              setFinalized(p.finalized);
              setClarification(p.pending_clarification);
            }}
          />
        </div>
      </section>
      <section className="overflow-y-auto">
        <Form1040Preview draft={draft} finalized={finalized} />
      </section>
    </main>
  );
}

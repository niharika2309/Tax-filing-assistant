"use client";

import { useRef, useState } from "react";
import { uploadDocument } from "@/lib/api";

export function UploadDropzone({
  sessionId,
  onUploaded,
}: {
  sessionId: string;
  onUploaded: (doc: { document_id: string; filename: string }) => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleFile(file: File) {
    setError(null);
    if (!file.name.toLowerCase().endsWith(".pdf")) {
      setError("Please upload a PDF.");
      return;
    }
    setUploading(true);
    try {
      const doc = await uploadDocument(sessionId, file);
      onUploaded(doc);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  }

  return (
    <div
      onDragOver={(e) => e.preventDefault()}
      onDrop={(e) => {
        e.preventDefault();
        const f = e.dataTransfer.files?.[0];
        if (f) void handleFile(f);
      }}
      onClick={() => inputRef.current?.click()}
      className="border border-dashed border-[color:var(--border)] rounded-md p-4 text-center cursor-pointer hover:border-[color:var(--accent)] transition"
    >
      <input
        ref={inputRef}
        type="file"
        accept="application/pdf"
        hidden
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) void handleFile(f);
        }}
      />
      <div className="text-sm">
        {uploading ? "Uploading…" : "Drop W-2 PDF here, or click to select"}
      </div>
      {error && <div className="text-xs text-[color:var(--error)] mt-2">{error}</div>}
    </div>
  );
}

"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { createSession } from "@/lib/api";

export default function Landing() {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function start() {
    setLoading(true);
    setError(null);
    try {
      const { session_id } = await createSession();
      router.push(`/return/${session_id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to start session");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="min-h-screen flex items-center justify-center p-8">
      <div className="max-w-xl w-full space-y-6 text-center">
        <h1 className="text-3xl font-semibold">Tax Filing Assistant</h1>
        <p className="text-[color:var(--muted)]">
          Upload your W-2 and chat — the agent parses forms, looks up IRS rules,
          calculates deductions, and fills Form 1040. Runs fully locally against LM Studio.
        </p>
        <button
          onClick={start}
          disabled={loading}
          className="px-6 py-3 rounded-md bg-[color:var(--accent)] hover:opacity-90 disabled:opacity-50 transition"
        >
          {loading ? "Starting…" : "Start a new return"}
        </button>
        {error && <p className="text-[color:var(--error)]">{error}</p>}
        <p className="text-xs text-[color:var(--muted)] pt-8">
          Scope: W-2 individual filers, tax year 2025.
        </p>
      </div>
    </main>
  );
}

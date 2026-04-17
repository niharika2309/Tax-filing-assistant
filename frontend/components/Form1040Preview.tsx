"use client";

type Draft = Record<string, unknown> | null;

function fmt(v: unknown): string {
  if (v === null || v === undefined || v === "") return "—";
  if (typeof v === "string" || typeof v === "number") {
    const n = Number(v);
    if (!Number.isNaN(n) && typeof v === "string" && /^-?\d+(\.\d+)?$/.test(v)) {
      return `$${n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
    }
    return String(v);
  }
  return JSON.stringify(v);
}

export function Form1040Preview({
  draft,
  finalized,
}: {
  draft: Draft;
  finalized: boolean;
}) {
  if (!draft) {
    return (
      <div className="p-6 text-sm text-[color:var(--muted)]">
        Form 1040 preview will fill in as the agent runs tools.
      </div>
    );
  }
  const tp = (draft["taxpayer"] as Record<string, unknown> | undefined) ?? {};
  const rows: [string, unknown][] = [
    ["Filing status", tp["filing_status"]],
    ["Dependents", tp["dependents"]],
    ["W-2 forms", (draft["w2_forms"] as unknown[] | undefined)?.length ?? 0],
    ["Line 1a — Wages", draft["total_wages"]],
    ["Line 11 — AGI", draft["adjusted_gross_income"]],
    ["Deduction type", draft["deduction_type"]],
    ["Line 12 — Standard deduction", draft["standard_deduction"]],
    ["Line 12 — Itemized deduction", draft["itemized_deduction"]],
    ["Line 15 — Taxable income", draft["taxable_income"]],
    ["Line 16 — Tax before credits", draft["tax_before_credits"]],
    ["Line 21 — Total credits", draft["total_credits"]],
    ["Line 24 — Tax after credits", draft["tax_after_credits"]],
    ["Line 25a — Federal withholding", draft["total_federal_withholding"]],
    ["Refund / Owed", draft["refund_or_owed"]],
  ];
  const schedA = draft["schedule_a"] as Record<string, unknown> | undefined;

  return (
    <div className="p-4 space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">Form 1040 — Tax Year {String(draft["tax_year"] ?? "")}</h2>
        {finalized && (
          <span className="text-xs px-2 py-1 rounded-full bg-[color:var(--success)] bg-opacity-20 text-black">
            READY
          </span>
        )}
      </div>
      <table className="w-full text-sm">
        <tbody>
          {rows.map(([label, value]) => (
            <tr key={label} className="border-b border-[color:var(--border)]">
              <td className="py-2 text-[color:var(--muted)]">{label}</td>
              <td className="py-2 text-right font-mono">{fmt(value)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {schedA && (
        <div>
          <h3 className="text-sm font-semibold mb-2">Schedule A — Itemized Deductions</h3>
          <table className="w-full text-sm">
            <tbody>
              {(
                [
                  ["Medical & dental", schedA["medical_dental"]],
                  ["State & local tax", schedA["state_local_tax"]],
                  ["Real estate tax", schedA["real_estate_tax"]],
                  ["Mortgage interest", schedA["mortgage_interest"]],
                  ["Charitable (cash)", schedA["charitable_cash"]],
                  ["Charitable (non-cash)", schedA["charitable_noncash"]],
                  ["Casualty loss", schedA["casualty_loss"]],
                  ["Other", schedA["other"]],
                  ["Total", schedA["total"]],
                ] as [string, unknown][]
              ).map(([label, value]) => (
                <tr key={label} className="border-b border-[color:var(--border)]">
                  <td className="py-1.5 text-[color:var(--muted)]">{label}</td>
                  <td className="py-1.5 text-right font-mono">{fmt(value)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

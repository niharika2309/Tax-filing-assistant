"""Streamlit frontend for the Tax Filing Assistant backend."""

import json
import requests
import streamlit as st

API = "http://localhost:8000"

st.set_page_config(page_title="Tax Filing Assistant", layout="wide")
st.title("Tax Filing Assistant")

# ── Session ──────────────────────────────────────────────────────────────────

if "session_id" not in st.session_state:
    st.session_state.session_id = None
if "messages" not in st.session_state:
    st.session_state.messages = []
if "return_draft" not in st.session_state:
    st.session_state.return_draft = None
if "docs" not in st.session_state:
    st.session_state.docs = []

if st.session_state.session_id is None:
    if st.button("Start a new return"):
        r = requests.post(f"{API}/sessions")
        r.raise_for_status()
        st.session_state.session_id = r.json()["session_id"]
        st.rerun()
    st.stop()

sid = st.session_state.session_id
st.caption(f"Session `{sid[:8]}…`")

left, right = st.columns(2)

# ── Left: upload + chat ───────────────────────────────────────────────────────

with left:
    uploaded = st.file_uploader("Upload W-2 PDF", type=["pdf"])
    if uploaded:
        already = [d["filename"] for d in st.session_state.docs]
        if uploaded.name not in already:
            r = requests.post(
                f"{API}/sessions/{sid}/documents",
                files={"file": (uploaded.name, uploaded.read(), "application/pdf")},
                data={"kind": "w2"},
            )
            r.raise_for_status()
            doc = r.json()
            st.session_state.docs.append({"filename": doc["filename"], "id": doc["document_id"]})

    if st.session_state.docs:
        st.write("**Uploaded:**", ", ".join(d["filename"] for d in st.session_state.docs))

    st.divider()

    # Render chat history
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # Chat input
    user_input = st.chat_input("I'm single, no dependents, take the standard deduction…")
    if user_input:
        st.session_state.messages.append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.markdown(user_input)

        # Stream from backend
        with st.chat_message("assistant"):
            text_placeholder = st.empty()
            tool_placeholder = st.empty()
            assistant_text = ""
            tool_lines = []

            with requests.post(
                f"{API}/sessions/{sid}/chat",
                json={"message": user_input},
                stream=True,
                headers={"Accept": "text/event-stream"},
                timeout=120,
            ) as resp:
                resp.raise_for_status()
                event_type = "message"
                for raw_line in resp.iter_lines(decode_unicode=True):
                    if not raw_line:
                        event_type = "message"
                        continue
                    if raw_line.startswith("event:"):
                        event_type = raw_line[6:].strip()
                        continue
                    if not raw_line.startswith("data:"):
                        continue
                    data_str = raw_line[5:].strip()
                    try:
                        payload = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue

                    if event_type == "token":
                        assistant_text += payload.get("text", "")
                        text_placeholder.markdown(assistant_text + "▌")

                    elif event_type == "tool_call_start":
                        tool_lines.append(f"⚙️ `{payload['tool']}` …")
                        tool_placeholder.markdown("\n".join(tool_lines))

                    elif event_type == "tool_call_end":
                        ok = isinstance(payload.get("output"), dict) and payload["output"].get("ok", True)
                        icon = "✅" if ok else "❌"
                        if tool_lines:
                            tool_lines[-1] = f"{icon} `{payload['tool']}`"
                        tool_placeholder.markdown("\n".join(tool_lines))

                    elif event_type == "return_updated":
                        st.session_state.return_draft = payload.get("return_draft")

                    elif event_type == "error":
                        st.error(payload.get("message", "Unknown error"))

                    elif event_type == "done":
                        break

            text_placeholder.markdown(assistant_text or "*(no text response)*")

        st.session_state.messages.append(
            {"role": "assistant", "content": assistant_text or "*(agent ran tools — see Form 1040 preview)*"}
        )
        st.rerun()

# ── Right: Form 1040 preview ──────────────────────────────────────────────────

with right:
    st.subheader("Form 1040 Preview")
    draft = st.session_state.return_draft

    if draft is None:
        # Fetch from backend
        r = requests.get(f"{API}/sessions/{sid}/return")
        if r.ok:
            data = r.json()
            draft = data.get("return_draft")
            st.session_state.return_draft = draft

    if draft:
        tp = draft.get("taxpayer") or {}

        def fmt(v):
            if v is None or v == "":
                return "—"
            try:
                n = float(v)
                return f"${n:,.2f}"
            except (TypeError, ValueError):
                return str(v)

        rows = [
            ("Filing status", tp.get("filing_status")),
            ("Dependents", tp.get("dependents")),
            ("W-2 forms", len(draft.get("w2_forms") or [])),
            ("Line 1a — Wages", draft.get("total_wages")),
            ("Line 11 — AGI", draft.get("adjusted_gross_income")),
            ("Deduction type", draft.get("deduction_type")),
            ("Line 12 — Standard deduction", draft.get("standard_deduction")),
            ("Line 12 — Itemized deduction", draft.get("itemized_deduction")),
            ("Line 15 — Taxable income", draft.get("taxable_income")),
            ("Line 16 — Tax before credits", draft.get("tax_before_credits")),
            ("Line 21 — Total credits", draft.get("total_credits")),
            ("Line 24 — Tax after credits", draft.get("tax_after_credits")),
            ("Line 25a — Federal withholding", draft.get("total_federal_withholding")),
            ("Refund / Owed", draft.get("refund_or_owed")),
        ]

        table_md = "| Line | Value |\n|---|---|\n"
        for label, val in rows:
            table_md += f"| {label} | {fmt(val)} |\n"
        st.markdown(table_md)

        sched_a = draft.get("schedule_a")
        if sched_a:
            st.subheader("Schedule A — Itemized Deductions")
            sa_rows = [
                ("Medical & dental", sched_a.get("medical_dental")),
                ("State & local tax", sched_a.get("state_local_tax")),
                ("Real estate tax", sched_a.get("real_estate_tax")),
                ("Mortgage interest", sched_a.get("mortgage_interest")),
                ("Charitable (cash)", sched_a.get("charitable_cash")),
                ("Total", sched_a.get("total")),
            ]
            sa_md = "| Line | Value |\n|---|---|\n"
            for label, val in sa_rows:
                sa_md += f"| {label} | {fmt(val)} |\n"
            st.markdown(sa_md)
    else:
        st.info("Form 1040 preview will appear here as the agent runs tools.")

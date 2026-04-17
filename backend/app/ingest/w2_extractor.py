"""Regex-driven W-2 field extraction.

W-2 PDFs vary across issuers (ADP, Gusto, QuickBooks, hand-typed), but IRS
layout mandates the same numbered boxes. The extractor operates on raw text
(from pdfplumber OR OCR output) and is tolerant of:
- box labels on their own line vs inline with values
- dollar signs, commas, parentheses for negatives
- extra whitespace and newlines between label and value
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.schemas.documents import IngestError, W2Form
from app.schemas.money import Money

# Stricter: requires either a decimal point, a thousands-separator, or 4+ digits.
# This prevents matching bare box numbers like "1" or "17" as money values.
_MONEY_RE = r"\$?\s*\(?-?\s*(?:\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?|\d+\.\d{1,2}|\d{4,})\)?"

# Labels for each W-2 box we care about. Ordered by specificity so
# "Box 1" matches before a bare "1".
_BOX_LABELS: dict[str, list[str]] = {
    "wages": [
        r"1\s+wages,?\s+tips,?\s+other\s*comp(?:ensation)?",
        r"box\s*1\s*[:.-]?\s*wages",
        r"wages,?\s+tips,?\s+other\s*comp(?:ensation)?",
        r"1\s+wages,?\s+tips,?\s+other",
        r"wages,?\s+tips,?\s+other",
    ],
    "federal_income_tax_withheld": [
        r"2\s+federal\s+income\s+tax\s+withheld",
        r"box\s*2\s*[:.-]?\s*federal",
        r"federal\s+income\s+tax\s+withheld",
    ],
    "social_security_wages": [
        r"3\s+social\s+security\s+wages",
        r"social\s+security\s+wages",
    ],
    "social_security_tax_withheld": [
        r"4\s+social\s+security\s+tax\s+withheld",
        r"social\s+security\s+tax\s+withheld",
    ],
    "medicare_wages": [
        r"5\s+medicare\s+wages(?:\s+and\s+tips)?",
        r"medicare\s+wages(?:\s+and\s+tips)?",
    ],
    "medicare_tax_withheld": [
        r"6\s+medicare\s+tax\s+withheld",
        r"medicare\s+tax\s+withheld",
    ],
    "state_income_tax_withheld": [
        r"17\s+state\s+income\s+tax",
        r"state\s+income\s+tax(?:\s+withheld)?",
    ],
}

_EMPLOYER_NAME_RE = re.compile(
    r"(?:c\s+employer[''`]?s\s+name[^\n]*\n)(.+?)(?:\n\s*(?:d\s+|e\s+|\d+\s+))",
    re.IGNORECASE | re.DOTALL,
)
_EIN_RE = re.compile(r"\b(\d{2}-\d{7})\b")
_TAX_YEAR_RE = re.compile(r"\b(20\d{2})\b")


@dataclass
class ExtractionResult:
    w2: W2Form | None
    confidence: float
    missing_fields: list[str]
    raw_matches: dict[str, str]


_BOX_LABEL_ON_LINE = re.compile(
    r"\b(1|2|3|4|5|6|15|16|17)\s+[a-zA-Z]", re.IGNORECASE
)
# Boxes whose values are text (state abbr, control number), not money.
# When a line has these alongside money boxes and value count is short by the
# number of text-valued boxes present, we drop them and retry alignment.
_TEXT_VALUED_BOXES = {"15"}


def preprocess_column_layout(text: str) -> str:
    """Split multi-column W-2 layouts into label→value pairs.

    When a line holds N box labels and the following line holds exactly N money
    values, emit N synthetic `label<tab>value` lines so downstream regex treats
    each box as a standalone record. No-op otherwise — preserves original text.
    """
    money_re = re.compile(_MONEY_RE)
    lines = text.split("\n")
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        labels = list(_BOX_LABEL_ON_LINE.finditer(line))
        if len(labels) >= 2 and i + 1 < len(lines):
            next_line = lines[i + 1]
            moneys = list(money_re.finditer(next_line))
            # Drop text-valued labels if doing so reconciles the count.
            money_labels = [lb for lb in labels if lb.group(1) not in _TEXT_VALUED_BOXES]
            if len(moneys) == len(money_labels) and money_labels:
                boundaries = [m.start() for m in money_labels] + [len(line)]
                for idx, m in enumerate(moneys):
                    label_text = line[boundaries[idx] : boundaries[idx + 1]].strip()
                    out.append(f"{label_text}\t{m.group(0).strip()}")
                i += 2
                continue
        out.append(line)
        i += 1
    return "\n".join(out)


def _normalize_money(raw: str) -> Money:
    """Convert messy string to Money. Handles $, commas, parens-as-negative."""
    s = raw.strip()
    negative = s.startswith("(") and s.endswith(")")
    s = s.replace("$", "").replace(",", "").replace("(", "").replace(")", "").strip()
    if not s or s == "-":
        return Money.zero()
    val = Money(s)
    if negative:
        val = Money.zero() - val
    return val


def _find_value_near_label(text: str, label_pattern: str, search_window: int = 200) -> str | None:
    """Find a label match, then look for the nearest money value within `search_window` chars."""
    label_re = re.compile(label_pattern, re.IGNORECASE)
    match = label_re.search(text)
    if not match:
        return None
    window = text[match.end() : match.end() + search_window]
    money_match = re.search(_MONEY_RE, window)
    return money_match.group(0) if money_match else None


def extract_w2_fields(
    text: str,
    document_id: str,
    default_tax_year: int,
) -> ExtractionResult:
    text = preprocess_column_layout(text)
    raw_matches: dict[str, str] = {}
    missing: list[str] = []

    for field, patterns in _BOX_LABELS.items():
        found: str | None = None
        for p in patterns:
            found = _find_value_near_label(text, p)
            if found:
                break
        if found:
            raw_matches[field] = found
        else:
            missing.append(field)

    # Critical fields — without these we cannot produce a W2Form at all.
    critical = {"wages", "federal_income_tax_withheld"}
    critical_missing = [f for f in critical if f in missing]

    if critical_missing:
        return ExtractionResult(
            w2=None,
            confidence=0.0,
            missing_fields=critical_missing,
            raw_matches=raw_matches,
        )

    ein_match = _EIN_RE.search(text)
    year_match = _TAX_YEAR_RE.search(text)
    tax_year = int(year_match.group(1)) if year_match else default_tax_year

    # Employer name — best effort; fail soft
    employer_name: str | None = None
    emp_match = _EMPLOYER_NAME_RE.search(text)
    if emp_match:
        employer_name = emp_match.group(1).strip().split("\n")[0][:120]

    w2 = W2Form(
        document_id=document_id,
        employer_ein=ein_match.group(1) if ein_match else None,
        employer_name=employer_name,
        wages=_normalize_money(raw_matches["wages"]),
        federal_income_tax_withheld=_normalize_money(raw_matches["federal_income_tax_withheld"]),
        social_security_wages=_normalize_money(raw_matches.get("social_security_wages", "0")),
        social_security_tax_withheld=_normalize_money(
            raw_matches.get("social_security_tax_withheld", "0")
        ),
        medicare_wages=_normalize_money(raw_matches.get("medicare_wages", "0")),
        medicare_tax_withheld=_normalize_money(raw_matches.get("medicare_tax_withheld", "0")),
        state_income_tax_withheld=_normalize_money(
            raw_matches.get("state_income_tax_withheld", "0")
        ),
        tax_year=tax_year,
    )

    total_fields = len(_BOX_LABELS) + 2  # +2 for EIN, employer name
    found_count = (
        len(_BOX_LABELS) - len(missing) + (1 if ein_match else 0) + (1 if employer_name else 0)
    )
    confidence = found_count / total_fields

    return ExtractionResult(
        w2=w2,
        confidence=confidence,
        missing_fields=missing,
        raw_matches=raw_matches,
    )


def require_w2(result: ExtractionResult) -> W2Form:
    if result.w2 is None:
        raise IngestError(
            f"W-2 extraction failed; missing critical fields: {result.missing_fields}",
            missing_fields=result.missing_fields,
        )
    return result.w2

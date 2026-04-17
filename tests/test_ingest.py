"""Extractor tests on synthetic W-2 text (no real PDFs needed — that's the point
of keeping the text-extraction layer separate from the PDF/OCR layer)."""

import pytest

from app.ingest.pipeline import ingest_w2_from_text
from app.ingest.w2_extractor import extract_w2_fields
from app.schemas.documents import IngestError
from app.schemas.money import Money

# Realistic W-2 text as produced by pdfplumber on a digital PDF
DIGITAL_W2_TEXT = """
Form W-2 Wage and Tax Statement 2025
a Employee's social security number                OMB No. 1545-0008
XXX-XX-4321

b Employer identification number (EIN)
12-3456789

c Employer's name, address, and ZIP code
Acme Robotics Inc
1 Innovation Way
Palo Alto, CA 94301

d Control number                                    e Employee's first name and initial
000123                                              Jane

1 Wages, tips, other compensation    2 Federal income tax withheld
52345.67                             6789.12

3 Social security wages              4 Social security tax withheld
52345.67                             3245.43

5 Medicare wages and tips            6 Medicare tax withheld
52345.67                             759.01

15 State  Employer's state ID         16 State wages, tips, etc.    17 State income tax
CA      XXX-XXXXXXX                   52345.67                      2112.45
"""

# OCR-style text: more garbled whitespace, inconsistent casing, no box numbers on some lines
OCR_W2_TEXT = """
Form W-2  Wage and Tax Statement  2025
b Employer identification number (EIN)  98-7654321
c Employer's name, address, and ZIP code
Widget Corp
1 Wages, tips, other compensation     $45,000.00
2 Federal income tax withheld          $3,200.50
3 Social security wages                $45,000.00
4 Social security tax withheld         $2,790.00
5 Medicare wages and tips              $45,000.00
6 Medicare tax withheld                $652.50
17 State income tax                    $1,890.00
"""


def test_extract_digital_w2():
    result = extract_w2_fields(DIGITAL_W2_TEXT, document_id="doc-1", default_tax_year=2025)
    assert result.w2 is not None
    w2 = result.w2
    assert w2.wages == Money("52345.67")
    assert w2.federal_income_tax_withheld == Money("6789.12")
    assert w2.social_security_wages == Money("52345.67")
    assert w2.medicare_tax_withheld == Money("759.01")
    assert w2.state_income_tax_withheld == Money("2112.45")
    assert w2.employer_ein == "12-3456789"
    assert w2.tax_year == 2025
    assert result.confidence > 0.7


def test_extract_ocr_w2_with_dollar_signs_and_commas():
    result = extract_w2_fields(OCR_W2_TEXT, document_id="doc-2", default_tax_year=2025)
    assert result.w2 is not None
    w2 = result.w2
    assert w2.wages == Money("45000.00")
    assert w2.federal_income_tax_withheld == Money("3200.50")
    assert w2.medicare_tax_withheld == Money("652.50")
    assert w2.employer_ein == "98-7654321"


def test_extract_missing_critical_field_returns_no_w2():
    broken = """
Form W-2 2025
3 Social security wages  50000.00
4 Social security tax withheld 3100.00
"""
    result = extract_w2_fields(broken, document_id="doc-x", default_tax_year=2025)
    assert result.w2 is None
    assert "wages" in result.missing_fields
    assert "federal_income_tax_withheld" in result.missing_fields
    assert result.confidence == 0.0


def test_ingest_from_text_roundtrips_to_parsed_document():
    parsed = ingest_w2_from_text(
        DIGITAL_W2_TEXT,
        document_id="doc-3",
        source_path="/tmp/fake.pdf",
        default_tax_year=2025,
    )
    assert parsed.kind == "w2"
    assert parsed.ocr_used is False
    assert parsed.w2 is not None
    assert parsed.w2.wages == Money("52345.67")


def test_ingest_from_text_raises_on_missing_critical():
    with pytest.raises(IngestError) as exc:
        ingest_w2_from_text(
            "no box numbers here",
            document_id="doc-fail",
            source_path="/tmp/x.pdf",
            default_tax_year=2025,
        )
    assert "wages" in exc.value.missing_fields


def test_extract_handles_negative_parenthesized_value():
    # Rare but happens on some corrected W-2c forms
    text = """
1 Wages, tips, other compensation   (500.00)
2 Federal income tax withheld       100.00
"""
    result = extract_w2_fields(text, document_id="doc-c", default_tax_year=2025)
    assert result.w2 is not None
    assert result.w2.wages == Money("-500")

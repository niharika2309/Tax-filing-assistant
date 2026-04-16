from app.schemas.rules import IRSRule
from app.tools._data_loader import load_rules


class RuleNotFoundError(KeyError):
    pass


def lookup_irs_rule(topic: str, tax_year: int) -> IRSRule:
    data = load_rules(tax_year)
    topic = topic.strip().lower()
    for rule in data["rules"]:
        if rule["topic"] == topic:
            return IRSRule(
                topic=rule["topic"],
                tax_year=tax_year,
                title=rule["title"],
                summary=rule["summary"],
                citation=rule["citation"],
                values=rule.get("values", {}),
            )
    available = ", ".join(r["topic"] for r in data["rules"])
    raise RuleNotFoundError(
        f"Unknown IRS rule topic '{topic}' for tax year {tax_year}. Available: {available}"
    )

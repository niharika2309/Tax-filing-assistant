import json
from functools import lru_cache
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


@lru_cache(maxsize=4)
def load_brackets(tax_year: int) -> dict[str, Any]:
    path = DATA_DIR / f"brackets_{tax_year}.json"
    if not path.exists():
        raise FileNotFoundError(f"No bracket data for tax year {tax_year}")
    return json.loads(path.read_text())


@lru_cache(maxsize=4)
def load_rules(tax_year: int) -> dict[str, Any]:
    path = DATA_DIR / f"irs_rules_{tax_year}.json"
    if not path.exists():
        raise FileNotFoundError(f"No IRS rules for tax year {tax_year}")
    return json.loads(path.read_text())

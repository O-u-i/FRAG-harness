"""Small deterministic scorers; exceptions propagate to an ERROR report."""
from __future__ import annotations

import re
import unicodedata

from frag_api.schemas.evaluation import EvalCheck, EvalStatus, GoldFact


def aggregate(statuses: list[EvalStatus]) -> EvalStatus:
    if "ERROR" in statuses:
        return "ERROR"
    if "FAIL" in statuses:
        return "FAIL"
    if "PASS" in statuses:
        return "PASS"
    if "UNDETERMINED" in statuses:
        return "UNDETERMINED"
    return "NOT_RUN"


def contains_literal(text: str, phrase: str) -> bool:
    def normalize(value):
        return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", value).casefold()).strip()
    normalized, required = normalize(text), normalize(phrase)
    return re.search(r"(?<!\w)" + re.escape(required) + r"(?!\w)", normalized) is not None


def score_facts(text: str, facts: list[GoldFact], stage: str, category="model_quality") -> list[EvalCheck]:
    checks = []
    for fact in facts:
        matched = [phrase for phrase in fact.alternatives if contains_literal(text, phrase)]
        forbidden = [phrase for phrase in fact.forbidden if contains_literal(text, phrase)]
        checks.append(EvalCheck(
            id=f"{stage}.fact.{fact.id}", stage=stage, category=category,
            status="PASS" if matched and not forbidden else "FAIL",
            detail=f"Declared {fact.kind} literal alternatives and forbidden phrases; semantic review remains required.",
            observed={"matchedAlternatives": matched, "forbiddenFound": forbidden},
        ))
    return checks


def coverage(expected: list[str], actual: list[str], stage: str, category="retrieval") -> EvalCheck:
    missing = sorted(set(expected) - set(actual))
    first_rank = next((rank for rank, item in enumerate(actual, 1) if item in expected), None)
    return EvalCheck(
        id=f"{stage}.coverage", stage=stage, category=category,
        status="FAIL" if missing else "PASS", detail="All declared Gold identifiers must be present.",
        observed={"expectedIds": expected, "actualIds": actual, "missingIds": missing,
                  "recallAtK": (len(expected) - len(missing)) / len(expected),
                  "reciprocalRank": 1 / first_rank if first_rank else 0},
    )

"""Local language hints and a conservative mismatch guard, not semantic scoring."""

import re
from functools import lru_cache

from lingua import LanguageDetectorBuilder

# Engineering heuristics, not calibrated probabilities. Short names/acronyms can
# receive high detector scores (e.g. CCS -> Hungarian), so they stay inconclusive.
MIN_LETTERS = 20
MIN_MARGIN = 0.20
POLICY_VERSION = "lingua-2.2.0-min20-margin0.20-v2"

# Quoted spans are titles or source wording whose language belongs to the
# source. Only the model's own prose is checked: under v1 an English claim was
# rejected as Latin because of a quoted English article title.
_QUOTED = re.compile(r'“[^”]*”|"[^"]*"|«[^»]*»|「[^」]*」|『[^』]*』|‘[^’]*’')


def _prose(text):
    # A claim that is almost entirely quoted is still checked as written.
    stripped = _QUOTED.sub(" ", text)
    return stripped if sum(c.isalpha() for c in stripped) >= MIN_LETTERS else text


@lru_cache(maxsize=1)
def detector():
    return LanguageDetectorBuilder.from_all_languages().build()


def language_hint(text):
    letters = sum(c.isalpha() for c in text)
    result = {"code": None, "name": None, "letters": letters, "margin": None}
    if letters < MIN_LETTERS:
        return result
    scores = detector().compute_language_confidence_values(text)
    if len(scores) < 2:
        return result
    margin = scores[0].value - scores[1].value
    result["margin"] = round(margin, 6)
    if margin >= MIN_MARGIN:
        result.update(
            code=scores[0].language.iso_code_639_1.name.lower(),
            name=scores[0].language.name.replace("_", " ").title(),
        )
    return result


def check_claim_languages(texts, target):
    """Only pass generated prose here. Source quotes must retain their language."""
    audit = {
        "policy": POLICY_VERSION,
        "target": target,
        "status": "inconclusive",
        "claims": [],
        "combined": None,
    }
    if not target or not target["code"]:
        return audit
    prose = [_prose(text) for text in texts]
    audit["claims"] = [language_hint(text) for text in prose]
    audit["combined"] = language_hint("\n".join(prose))
    hints = [*audit["claims"], audit["combined"]]
    if any(h["code"] and h["code"] != target["code"] for h in hints):
        audit["status"] = "mismatch"
    elif texts and all(h["code"] == target["code"] for h in hints):
        audit["status"] = "match"
    return audit

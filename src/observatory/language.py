"""Local language hints and a conservative mismatch guard, not semantic scoring."""

import html
import re
import unicodedata
from functools import lru_cache

from lingua import LanguageDetectorBuilder

# Engineering heuristics, not calibrated probabilities. Short names/acronyms can
# receive high detector scores (e.g. CCS -> Hungarian), so they stay inconclusive.
MIN_LETTERS = 20
MIN_MARGIN = 0.20
POLICY_VERSION = "lingua-2.2.0-min20-margin0.20-v6"

# Only exact titles from the selected evidence can be omitted from detection.
# Quotation marks alone do not establish that text came from a source.
_QUOTED = re.compile(r'“[^”]*”|"[^"]*"|«[^»]*»|「[^」]*」|『[^』]*』|‘[^’]*’')


def _words(text):
    """Letter-only words: punctuation, case, footnote digits and HTML entities do not decide a match."""
    return " ".join(re.findall(r"[^\W\d_]+", html.unescape(str(text)).casefold()))


def _from_sources(content, sources):
    """Every sentence, ellipsis- or [edit]-separated part of a quotation occurs in the evidence.

    Word spacing is not compared: stored text can lose a space ("thesoutheast"),
    which rejected a verbatim English quote in a Chinese answer (B1K-0229).
    """
    parts = [_words(part) for part in re.split(r"\.\.\.|…|\[[^\]]*\]|(?<=[.!?。])\s+", content)]
    parts = [part for part in parts if len(part.split()) >= 3]
    joined = [source.replace(" ", "") for source in sources]
    return bool(parts) and all(any(part.replace(" ", "") in source for source in joined) for part in parts)


def _prose(text, source_titles, source_texts=()):
    unchecked_quotes = []
    ignored = 0

    def replace(match):
        nonlocal ignored
        content = match.group()[1:-1]
        # An exact title, or a quotation found word for word in the selected
        # evidence, is source text in its own language, not generated prose.
        if content in source_titles or (source_texts and _from_sources(content, source_texts)):
            ignored += 1
            return " "
        unchecked_quotes.append(content)
        return match.group()

    stripped = _QUOTED.sub(replace, text)
    # A title alone cannot establish the language of an answer's prose.
    prose = stripped if sum(c.isalpha() for c in stripped) >= MIN_LETTERS else text
    return prose, unchecked_quotes, ignored


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


def answer_language(question):
    """The required answer language: the question's, else the English interface default.

    A short Latin-script question is often inconclusive (a short list question
    about a low-carbon fuel scored a 0.17 margin); without a target the
    generator chose Spanish and nothing was checked. Questions in other scripts
    stay inconclusive rather than being forced into English.
    """
    hint = language_hint(question)
    letters = [c for c in question if c.isalpha()]
    if hint["code"] is None and letters and all("LATIN" in unicodedata.name(c, "") for c in letters):
        hint = {**hint, "code": "en", "name": "English", "basis": "interface_default"}
    return hint


_NAME = re.compile(r"(?<![.!?:]\s)(?<!^)\b[A-ZÀ-Þ][\w'’.-]*", re.M)


def _without_names(text):
    """Drop capitalised words that do not start a sentence."""
    return re.sub(r"\s{2,}", " ", _NAME.sub(" ", text)).strip()


def check_claim_languages(texts, target, *, source_titles=(), source_texts=()):
    """Only pass generated prose here. Source quotes must retain their language."""
    audit = {
        "policy": POLICY_VERSION,
        "target": target,
        "status": "inconclusive",
        "claims": [],
        "combined": None,
        "quoted_prose": [],
        "title_spans_ignored": 0,
    }
    if not target or not target["code"]:
        return audit
    titles = {title for title in source_titles if isinstance(title, str) and title}
    sources = [_words(text) for text in source_texts if isinstance(text, str) and text]
    parsed = [_prose(text, titles, sources) for text in texts]
    prose = [item[0] for item in parsed]
    audit["quoted_prose"] = [language_hint(quote) for item in parsed for quote in item[1]]
    audit["title_spans_ignored"] = sum(item[2] for item in parsed)
    # Proper names ("Søren Skou of Maersk") are no evidence of the prose
    # language; a names-heavy summary would otherwise read as another language.
    prose = [_without_names(text) for text in prose]
    audit["claims"] = [language_hint(text) for text in prose]
    audit["combined"] = language_hint("\n".join(prose))
    # Each claim is judged on its own; the joined text only decides when no
    # claim is conclusive. Under v3 six English claims of the form "The
    # advertisement mentions carbon capture..." were joined into text that
    # lingua read as Latin (margin 0.9997), rejecting a correct answer.
    own = [*audit["claims"], *audit["quoted_prose"]]
    combined = audit["combined"]
    if any(h["code"] and h["code"] != target["code"] for h in own):
        audit["status"] = "mismatch"
    elif texts and all(h["code"] == target["code"] for h in own):
        audit["status"] = "match"
    elif not any(h["code"] for h in own) and combined["code"]:
        audit["status"] = "match" if combined["code"] == target["code"] else "mismatch"
    return audit

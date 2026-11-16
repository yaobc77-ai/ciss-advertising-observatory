"""Link cited quotes to their exact place in a record's stored text (client item C17).

Evidence offsets are Unicode character positions in the cited version's stored body,
or in one saved source observation for social posts with differing captures. A link
carries the version, so a record that changed since the answer is never mis-highlighted.
"""

from urllib.parse import quote, urlencode

MAX_HIGHLIGHTS = 20


def quote_range(evidence, text):
    """Absolute [start, end) of an exact quote inside one evidence passage, or None."""
    passage, start = evidence.get("text"), evidence.get("start")
    if not isinstance(passage, str) or type(start) is not int or not isinstance(text, str) or not text.strip():
        return None
    index = passage.find(text)
    return None if index < 0 else (start + index, start + index + len(text))


def record_quote_href(evidence, quotes):
    """Record page URL that highlights the given quotes from one evidence passage."""
    record_id = str(evidence.get("record_id") or "")
    if not record_id:
        return ""
    ranges = [r for r in (quote_range(evidence, text) for text in quotes) if r]
    href = "/records/" + quote(record_id, safe="")
    if not ranges or not evidence.get("version_id"):
        return href
    params = [("v", evidence["version_id"])]
    if evidence.get("source_observation_id"):
        params.append(("obs", evidence["source_observation_id"]))
    params += [("hl", f"{start}-{end}") for start, end in ranges[:MAX_HIGHLIGHTS]]
    return f"{href}?{urlencode(params)}#quote-1"


def parse_highlights(values):
    """Parse repeated hl=start-end values; malformed parts are ignored."""
    ranges = []
    for value in values[:MAX_HIGHLIGHTS]:
        start, _, end = str(value).partition("-")
        if start.isdigit() and end.isdigit() and int(start) < int(end):
            ranges.append((int(start), int(end)))
    return ranges


def mark_segments(text, ranges):
    """Split text into plain and highlighted pieces; overlapping ranges merge.

    Returns None when a range falls outside the text, so the caller can say the
    position no longer matches instead of highlighting the wrong characters.
    """
    if not isinstance(text, str) or not ranges:
        return None
    if any(end > len(text) for _, end in ranges):
        return None
    merged = []
    for start, end in sorted(ranges):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    segments, cursor = [], 0
    for number, (start, end) in enumerate(merged, start=1):
        if cursor < start:
            segments.append({"text": text[cursor:start], "mark": None})
        segments.append({"text": text[start:end], "mark": number})
        cursor = end
    if cursor < len(text):
        segments.append({"text": text[cursor:], "mark": None})
    return segments


def citation_locations(citations, evidence):
    """For API clients: where each article-text citation sits in its record."""
    by_id = {item.get("evidence_id"): item for item in evidence if isinstance(item, dict)}
    located = []
    for citation in citations:
        item = by_id.get(citation.get("evidence_id")) if isinstance(citation, dict) else None
        span = quote_range(item, citation.get("quote")) if item and citation.get("evidence_type", "article_text") == "article_text" else None
        if span is None:
            located.append(dict(citation, location=None))
            continue
        located.append(dict(citation, location={
            "record_id": item.get("record_id"), "version_id": item.get("version_id"),
            "source_observation_id": item.get("source_observation_id"),
            "start": span[0], "end": span[1],
            "record_url": record_quote_href(item, [citation["quote"]]),
        }))
    return located

"""Conservative task cues, not a general natural-language intent classifier.

These rules prevent an observed failure: a model dropping an explicit content
predicate and returning an unrelated metadata total. They do not establish
article matches, semantic support, complete recall, or scientific consensus.
"""

from __future__ import annotations

import calendar
import re
from datetime import date, timedelta

from .structured_queries import (
    _YEAR_OR_DAY,
    _date_endpoint,
    _entity_keys,
    canonical_source_values,
)

POLICY_VERSION = "question-task-v8"

# There is no trusted calendar reference in the tool contract. A relative
# interval therefore needs clarification, even if a model guessed endpoints.
_RELATIVE_CALENDAR = re.compile(
    r"\b(?:last|this|current|previous|next|past)\s+(?:calendar\s+)?"
    r"(?:(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)\s+)?"
    r"(?:years?|months?|quarters?|weeks?|days?)\b"
    r"|\b(?:today|yesterday|tomorrow|year\s+to\s+date|month\s+to\s+date|YTD|MTD)\b"
    r"|去年|今年|明年|上一年|下一年|上个月|本月|这个月|下个月|上季度|本季度|下季度"
    r"|上周|本周|这周|下周|昨天|今天|明天"
    r"|(?:过去|最近|近)\s*(?:\d+|[一二两三四五六七八九十几]+)\s*(?:年|个月|月|周|天)", re.I,
)

_ORIGINAL_SOURCE = re.compile(
    r"\b(?:excel|spreadsheet|stored|source data|original metadata|original field)\b"
    r"|原(?:Excel|表格|件|字段|始资料)|保存的|已存储的", re.IGNORECASE,
)
_METADATA_FIELD = re.compile(
    r"\b(?:title|date|url|link|publisher|sponsor|search term|keyword|disclosure|label|wording|location)\b"
    r"|标题|日期|网址|链接|媒体|赞助|搜索词|收集词|披露|位置|原文用语", re.IGNORECASE,
)
# A request to cite or quote the source is part of a content read, not a task.
_CITATION_CLAUSE = re.compile(
    r"[,;:.!?]?\s*(?:please\s+)?(?:cite|quote|citing|quoting)\s+(?:the|its|their|those|these|that|each|all)?\s*"
    r"(?:social\s+)?(?:ads?|advertisements?|posts?|articles?|announcements?|sources?|explanations?|passages?|text|wording)?"
    r"\s*[.!?]?\s*(?=$|[A-Z])"
    r"|[，。；,;]?\s*(?:请|并|并且)?(?:引用|给出|注明|附上)(?:原文|来源|出处|帖子|广告|这些广告|这些帖子|原帖)[。！]?\s*$",
    re.IGNORECASE,
)
# Verbs showing that a question asks what a source says, not for a count or a stored field.
_CONTENT_VERB = re.compile(
    r"\b(?:says?|said|saying|describ(?:e|es|ed|ing)|claim(?:s|ed|ing)?|announc(?:e|es|ed|ing)|"
    r"explain(?:s|ed|ing)?|mention(?:s|ed|ing)?|present(?:s|ed|ing)?|stat(?:e|es|ed|ing)|"
    r"report(?:s|ed|ing)?|according\s+to|cite|quote|summari[sz]e|assign(?:s|ed)?|"
    r"why\s+(?:does|do|did|is|are)\b|how\s+(?:does|do|did)\b)"
    r"|说|称|描述|介绍|引用|原文|宣布|提到|谈到|怎样|如何|说明|解释|表示|叫什么|什么办法|建设了什么",
    re.IGNORECASE,
)
# A bare question word is a content cue only when no stored field is named.
_CONTENT_WH = re.compile(
    r"\b(?:what|which|where|who)\s+(?!(?:ads?|advertisements?|articles?|posts?|records?)\b)"
    r"|是什么|有什么|哪个|哪里|谁",
    re.IGNORECASE,
)
# Counting language that refers to records rather than to figures inside a source.
# "How many homes can the plant power" asks for a figure an ad states; only a
# count, share or number of collection units (ads, posts, records) is a count.
_RECORD_UNIT = (r"(?:(?:unique|distinct|countable|native|social|sponsored|paid|company|[\w-]+-sponsored)\s+)*"
                r"(?:ads?|advertisements?|articles?|posts?|records?|tweets?|stories)\b")
_COUNT_REQUEST = re.compile(
    rf"\bhow\s+many\s+(?:[\w&'-]+\s+){{0,3}}?{_RECORD_UNIT}"
    rf"|\b(?:the\s+)?(?:number|count|counts|totals?|percentage|percent|proportion|share)\s+of\s+"
    rf"(?:(?:the|all|their|its|these|those)\s+)?(?:[\w&'-]+\s+){{0,3}}?{_RECORD_UNIT}"
    rf"|\bcount(?:s|ing)?\s+(?:(?:the|all|their|its|these|those)\s+)?(?:[\w&'-]+\s+){{0,3}}?{_RECORD_UNIT}"
    r"|(?:广告|帖子|记录|文章)(?:的)?(?:数量|总数|计数|占比|百分比)"
    r"|(?:广告|帖子|记录|文章)(?:有|共有|一共有|总共有)?多少(?:条|篇|个|则)?(?![一-鿿])"
    r"|(?:多少|几)(?:条|篇|个|则)?(?:唯一)?(?:原生)?(?:社交)?(?:广告|帖子|记录|文章)",
    re.IGNORECASE,
)
# A question asked of one named source ("in X's ad", "according to the post")
# reads that source's text, whatever figure or fact it asks for.
_SOURCE_ANCHOR = re.compile(
    r"\b(?:in|from|according\s+to)\s+(?:the\s+|a\s+|an\s+|this\s+|that\s+|(?:[\w&.-]+\s+){0,3}[\w&.'-]+'s\s+)"
    r"(?:[\w&.'-]+\s+){0,5}?(?:ads?|advertisements?|articles?|posts?|tweets?|pieces?|announcements?|reply"
    r"|episodes?|videos?|podcasts?|pages?|stories|story)\b"
    # A source named by its owner and form, even without a preposition:
    # "TotalEnergies' CNBC episode on ...: how many ...".
    r"|\b[\w&.-]+(?:'s|')\s+(?:[\w&.'-]+\s+){0,3}?(?:ads?|advertisements?|articles?|posts?|tweets?|pieces?"
    r"|episodes?|videos?|podcasts?|stories|story)\s+(?:on|about|titled|that|which)\b"
    r"|(?:广告|帖子|文章|推文)(?:里|中|上|内)", re.I)
_SAYS = re.compile(
    r"\b(?:say|says|said|saying|describe[sd]?|describing|explain(?:s|ed)?)\b|说了?什么|怎么说|描述|介绍", re.I)
_ASKS = re.compile(r"\b(?:what|which|who|where|when|how)\b|什么|哪|谁|多少|几", re.I)
_GROUPING_REQUEST = re.compile(
    r"\bwhich\s+(?:publishers?|outlets?|sponsors?|companies|accounts?|years?|platforms?)\b"
    r"|哪些(?:媒体|公司|赞助|账号|年份|平台)", re.IGNORECASE,
)
_QUOTED_TITLE = re.compile(r'"[^"]{3,}"|《[^》]{2,}》|“[^”]{3,}”')


def strip_citation_clauses(text: str) -> str:
    return _CITATION_CLAUSE.sub(" ", text)


def content_search_question(question: str) -> bool:
    """A question about what a source says is answered by one text search.

    Counts, shares, groupings, complete lists and stored-field requests keep
    their own tools; a citation request does not turn a content question into
    a separate task.
    """
    text = strip_citation_clauses(question)
    # "Which ads mention X, and what does each say" asks for the sources' text,
    # which only a text search reads; a bare "which ads mention X" is a list.
    listing = _SELECTION.search(text) and not _SAYS.search(text)
    if (_COUNT_REQUEST.search(text) or _GROUPING_REQUEST.search(text) or listing
            or original_metadata_question(text) or _DISCLOSURE.search(text) or _ORIGINAL_SOURCE.search(text)):
        return False  # stored or original fields are read by their own tool
    if _CONTENT_VERB.search(text):
        return True
    if (_SOURCE_ANCHOR.search(text) and _ASKS.search(text)
            and not _METADATA_FIELD.search(_QUOTED_TITLE.sub(" ", text))):
        return True
    return bool(_CONTENT_WH.search(text) and not _METADATA_FIELD.search(_QUOTED_TITLE.sub(" ", text)))


_SOURCES_SAY = re.compile(
    r"\bwhat\s+(?:do|does|did)\b[^?。？]{0,160}?\b(?:say|state|claim|tell|write)\b"
    r"|\bhow\s+(?:do|does|did)\b[^?。？]{0,160}?\b(?:describe|explain|discuss|portray|present)\b"
    r"|\bwhat\s+(?:specific\s+|main\s+)?points?\b"
    r"|说了什么|怎么说|讲了什么|写了什么|(?:如何|怎样)(?:描述|介绍|谈)", re.I,
)


def sources_content_request(question: str) -> bool:
    """The user asks what the sources say, not only which sources qualify.

    "What do Tidal Co's ads say about kites? Cite each ad" needs every matching
    ad read for its points; a list of one quote per ad drops them (B1K-Q052).
    "Which ads describe kites as cheap" selects ads and stays a list.
    """
    return bool(_SOURCES_SAY.search(strip_citation_clauses(question)))


_MULTI_READ = re.compile(
    r"(?:\b(?:and|also|plus|then)\s+|[;；.!?。！？]\s*)(?:also\s+)?(?:count|list|read|show|find|compare|how\s+many|which|what)\b"
    r"|(?:并且|同时|以及|再|还要).{0,8}?(?:统计|列出|读取|展示|查看|比较|多少|哪些)", re.I,
)
_READ_REQUEST = re.compile(
    r"\b(?:count|list|read|show|find|compare|search|retrieve|locate|summari[sz]e|"
    r"describe|explain|identify|translate|interpret|give|provide|tell|how\s+many|which|what)\b"
    r"|统计|列出|读取|展示|查看|比较|多少|哪些|什么|查找|找出|寻找|检索|总结|描述|解释|提供", re.I,
)
_RETRIEVAL_REQUEST = re.compile(
    r"^\s*(?:(?:please|can you|could you|would you)\s+)?"
    r"(?:find|search(?:\s+for)?|retrieve|locate)\b|^\s*(?:请)?(?:查找|找出|寻找|检索)", re.I,
)
_SAME_READ_DISPLAY = re.compile(
    r"(?:\b(?:and|also|plus|then)\s+|[;；.!?。！？]\s*)(?:also\s+)?"
    r"(?:show|read)\s+(?:its|their)\s+(?:(?:original|saved|stored)\s+)?"
    r"(?:wording|text|passages|quotes|quotations|excerpts|content|contents)\s*[.!?。！？]?"
    r"|(?:并且|同时|以及|再|还要)\s*(?:展示|查看|列出)\s*(?:它|它们|其)(?:的)?"
    r"(?:原文|正文|文字|措辞|内容)\s*[。！？]?", re.I,
)
# A follow-up that only changes the period of the same count adds no read task;
# record_statistics compares periods in one call.
_PERIOD_ONLY_COUNT = re.compile(
    r"\s*(?:,\s*)?(?:and|also|plus|then)?\s*how\s+many\s+"
    r"(?:(?:were|was|are|did|they|it|in|during|for|from|to|through|between|and|published|posted|ran|"
    r"appeared|of\s+them|the\s+same)\s+|\d{4}(?:-\d{2}(?:-\d{2})?)?\s*,?\s*)+"
    r"(?=[?.!;。？！；]|$)", re.I,
)
_DATASETS = {
    "native": re.compile(r"\bnative\s+(?:advertising|ads?|advertisements?|records?|articles?)\b|原生(?:广告|数据|记录)", re.I),
    "social": re.compile(r"\bsocial\s+(?:media|posts?|records?|advertising|ads?)\b|社交(?:媒体|帖子|记录|广告|数据)", re.I),
}
_BOTH_DATASETS = re.compile(
    r"\b(?:both|two|the\s+two)\s+(?:collections|datasets|data\s*sets)\b|\bboth\s+native\s+(?:ads?|advertisements?)\s+and\s+social"
    r"|(?:两个|两类|两种)(?:数据集|集合|数据)", re.I)


def original_metadata_question(question: str) -> bool:
    """Conservative source-field boundary, independent of customer test wording."""
    return bool(_ORIGINAL_SOURCE.search(question) and _METADATA_FIELD.search(question))


def _compound_read_request(text: str) -> bool:
    """Require a prior request; displaying retrieved text is the same read.

    This remains a conservative surface check. An anaphoric display clause is
    exempt only when it asks for the text of the retrieval and ends the request;
    new objects, source fields, collections or further operations still require
    a plan. Literal scope and metadata contracts are checked independently.
    """
    if _same_record_metadata_read(text) or _located_record_fields_read(text):
        return False
    for match in _MULTI_READ.finditer(text):
        prior = text[:match.start()]
        if not _READ_REQUEST.search(prior):
            continue
        # A relative clause restricts the records of one read. Its predicate
        # must still survive the independent content/scope guards.
        if (re.match(r"\band\s+which\s+(?:are|were|have|had)\b", text[match.start():], re.I)
                and re.search(r"\b(?:that|which)\s+(?:are|were|have|had|ran|published)\b", prior, re.I)
                and not re.search(r"[;.!?。！？]", prior)):
            continue
        if (_QUANTITY.search(prior) and re.fullmatch(
                r"\band\s+show\s+(?:(?:the|its|their)\s+)?(?:breakdown|counts|totals)\s+by\s+"
                r"(?:publisher|sponsor|platform|account|year)\s*[.!?]?", text[match.start():], re.I)):
            continue  # The statistics tool returns a total and this grouping.
        if _QUANTITY.search(prior) and _PERIOD_ONLY_COUNT.match(text, match.start()):
            continue  # "...in 2018, and how many in 2019": one count read with periods.
        if (_RETRIEVAL_REQUEST.search(prior)
                and _SAME_READ_DISPLAY.fullmatch(text[match.start():])):
            continue
        return True
    return False


_TITLE_LOCATOR = re.compile(
    r"\b(?:titled|entitled|whose\s+title|with\s+(?:the\s+)?title|title\s+(?:is|was|reads))\b"
    r"|标题(?:为|是|叫|里有|中有|包含)", re.I)
_RECORD_FIELD = re.compile(
    r"\b(?:outlet|publisher|published|publication|sponsor(?:ed|s)?|date|when|year|url|link|author|byline)\b"
    r"|媒体|赞助|日期|发布|网址|链接|作者", re.I)
_OTHER_OPERATION = re.compile(
    r"\b(?:count|list|compare|summari[sz]e|explain|describe|translate|interpret|say|says|said|mention\w*)\b"
    r"|统计|列出|比较|总结|解释|描述|翻译|说了|提到", re.I)


def _located_record_fields_read(text: str) -> bool:
    """Fields of one record located by its title are one lookup, however phrased.

    "Which outlet published the ad titled X, who sponsored it, and when?" names
    one record and asks only for stored fields. The words describing the title
    are the locator, not a task; any other operation keeps the plan obligation.
    """
    text = strip_citation_clauses(_QUOTED_LITERAL.sub(' "" ', text))
    locators = list(_TITLE_LOCATOR.finditer(text))
    if len(locators) != 1:
        return False
    locator = locators[0]
    after = text[locator.end():]
    quoted = re.match(r'\s*""', after)
    if quoted:
        # A quoted title is the whole locator.
        tail = after[quoted.end():]
    else:
        # An unquoted description ("whose title talks about ...") runs to the clause end.
        stop = re.search(r"[.?!;。？！；,，]|\band\s+(?=(?:what|which|who|how|when|where|show|read|list|count)\b)",
                         after, re.I)
        tail = after[stop.end():] if stop else ""
    rest = text[:locator.start()] + " " + tail
    # A second record or the record's text is another read.
    if len(re.findall(r"\b(?:ads?|advertisements?|articles?|posts?|records?)\b|广告|文章|帖子|记录", text, re.I)) > 1:
        return False
    if re.search(r"\b(?:body|text|passages?|contents?|second|another|other)\b|正文|内容|另一", rest, re.I):
        return False
    return bool(_RECORD_FIELD.search(rest) and not _OTHER_OPERATION.search(rest)
                and not _COUNT_REQUEST.search(rest))


def _same_record_metadata_read(text: str) -> bool:
    """Several stored fields of one explicitly located record use one read.

    This exemption needs a single literal locator and field-only clauses. A
    second record, a count or a content operation retains the plan obligation.
    """
    if not original_metadata_question(text):
        return False
    locators = re.findall(
        r"\b(?:article|record|post)\s+(?:titled|called|named|with\s+(?:the\s+)?title)\b"
        r"|\brecord\s+(?:id\s*[:=]?\s*)?(?:native|social):[\w-]+"
        r"|(?:文章|记录|帖子).{0,6}?(?:标题为|名为)", text, re.I)
    if len(locators) != 1:
        return False
    # Quoted locator titles are data, including any operation-looking words.
    field_text = _QUOTED_LITERAL.sub(" ", text)
    if len(re.findall(r"\b(?:article|record|post)\b|文章|记录|帖子", field_text, re.I)) != 1:
        return False
    if re.search(r"\b(?:count|list|compare|summari[sz]e|explain|translate|how\s+many)\b"
                 r"|统计|列出|比较|总结|解释|翻译|多少", field_text, re.I):
        return False
    if _MENTION.search(field_text) or _FRAMING.search(field_text) or _TOPIC.search(field_text):
        return False
    if re.search(r"\b(?:body|paragraphs?|passages?|contents?|main\s+text|article\s+text)\b"
                 r"|正文|段落|内容", field_text, re.I):
        return False
    clauses = re.split(r"\band\s+(?=(?:what|show|read)\b)|并且|以及|同时", field_text, flags=re.I)
    return len(clauses) > 1 and all(_METADATA_FIELD.search(clause) for clause in clauses)


def effective_dataset_scope(requested: str | None, trusted: str) -> str | None:
    """Intersect a collection request with the active UI collection."""
    if trusted not in {"native", "social", "all"} or requested not in {None, "native", "social", "all"}:
        return None
    if requested in {None, "all"}:
        return trusted
    return requested if trusted in {"all", requested} else None


def _literal_date_scope(text: str) -> tuple[str | None, str | None] | None:
    """Parse bounded year/ISO scope using the executor's calendar endpoints.

    None means there is no supported explicit scope. Multiple or invalid
    ranges fail rather than being narrowed to a convenient subset.
    """
    if _unsupported_subyear_dates(text):
        raise ValueError("Unsupported sub-year date expression")
    token = rf"(?<![A-Za-z0-9_-])({_YEAR_OR_DAY})(?![A-Za-z0-9_-])"
    ranges = list(re.finditer(
        rf"{token}\s*(?:年\s*)?(?:to|through|and|[–—]|至|到)\s*{token}(?:年)?"
        rf"|\b(?:in|during|from)\s+({_YEAR_OR_DAY})\s*-\s*({_YEAR_OR_DAY})(?![A-Za-z0-9_-])", text, re.I))
    if ranges:
        if len(ranges) != 1:
            raise ValueError("Multiple date ranges require period comparison")
        match = ranges[0]
        # 'and' connects endpoints only when introduced by 'between'.
        if re.search(r"\band\b", match.group(), re.I) and not re.search(
                r"\bbetween\s*$", text[:match.start()], re.I):
            raise ValueError("Unspecified relation between date endpoints")
        remainder = text[:match.start()] + text[match.end():]
        if re.search(rf"\b{_YEAR_OR_DAY}\b", remainder):
            raise ValueError("Additional dates were not covered by the range")
        values = [value for value in match.groups() if value is not None]
        lower, upper = _date_endpoint(values[0], False), _date_endpoint(values[1], True)
        if lower > upper:
            raise ValueError("Invalid date order")
        return lower.isoformat(), upper.isoformat()
    tokens = list(re.finditer(token, text))
    if len(tokens) > 1:
        raise ValueError("Multiple dates need an explicit range or comparison")
    if not tokens:
        return None
    match = tokens[0]
    value = match.group(1)
    prefix = text[:match.start()]
    suffix = text[match.end():]
    after = bool(re.search(r"\bafter\s*$", prefix, re.I) or re.match(r"\s*(?:年)?之后", suffix))
    before = bool(re.search(r"\bbefore\s*$", prefix, re.I) or re.match(r"\s*(?:年)?之前", suffix))
    lower_only = after or bool(re.search(r"\b(?:since|from)\s*$|自\s*$", prefix, re.I))
    upper_only = before or bool(re.search(r"\b(?:until|through|to)\s*$|截至\s*$", prefix, re.I))
    if lower_only:
        lower = _date_endpoint(value, after) + (timedelta(days=1) if after else timedelta())
        return lower.isoformat(), None
    if upper_only:
        upper = _date_endpoint(value, not before) - (timedelta(days=1) if before else timedelta())
        return None, upper.isoformat()
    if len(value) == 10 or re.search(r"\b(?:in|during|year)\s*$|(?:在|年份)\s*$", prefix, re.I):
        return _date_endpoint(value, False).isoformat(), _date_endpoint(value, True).isoformat()
    raise ValueError("Unsupported wording around an explicit date token")


def _unsupported_subyear_dates(text: str) -> bool:
    """Do not let a partial numeric date disappear or become a whole year."""
    months = (r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|"
              r"Aug(?:ust)?|Sep(?:tember)?|Sept(?:ember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)")
    if re.search(rf"\b{months}\.?\s+(?:\d{{1,2}}(?:st|nd|rd|th)?\s*,?\s*)?\d{{4}}\b"
                 rf"|\b\d{{4}}\s+{months}\b|\d{{4}}年\s*\d{{1,2}}月"
                 r"|\b(?:Q[1-4]|quarters?)\b|季度", text, re.I):
        return True
    numeric_dates = re.findall(
        r"(?<![A-Za-z0-9_])(?:\d{4}[-/]\d{1,2}(?:[-/]\d{1,2})?|\d{1,2}[-/]\d{4})"
        r"(?![A-Za-z0-9_])", text)
    for value in numeric_dates:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            return True
        try:
            _date_endpoint(value, False)
        except ValueError:
            return True
    return False


def _unsupported_period_dates(text: str) -> bool:
    """Keep unsupported sub-year/open periods out of the annual heuristic."""
    if _unsupported_subyear_dates(text):
        return True
    closed = list(re.finditer(
        rf"\bfrom\s+{_YEAR_OR_DAY}\s+(?:to|through)\s+{_YEAR_OR_DAY}\b", text, re.I))
    for match in re.finditer(r"\b(?:before|after|since|until|from|through)\s+(?=\d{4}\b)"
                             r"|(?:自|截至)\s*(?=\d{4})|(?<=年)(?:之前|之后)", text, re.I):
        if not any(interval.start() <= match.start() < interval.end() for interval in closed):
            return True
    return False


def _shared_entity_values(text, context, dimension):
    """Canonical source values of ``dimension`` whose names occur in ``text``."""
    items = context.get(dimension) or []
    if isinstance(items, dict):
        items = items.get("options") or []
    found = set()
    for item in items:
        item = {"value": item} if isinstance(item, str) else item
        spellings = {item.get("value"), item.get("display")} - {None, ""}
        aliases = _entity_keys(item["value"], dimension) if dimension != "accounts" else set()
        patterns = [re.escape(spelling) for spelling in spellings]
        patterns.extend(r"[\s._-]*".join(map(re.escape, spelling)) for spelling in aliases)
        if any(re.search(r"(?<![A-Za-z0-9_])" + spelling + r"(?![A-Za-z0-9_])", text, re.I) for spelling in patterns):
            found.update(str(value).strip().casefold() for value in item.get("source_variants") or [item["value"]])
    return found


def _scope_failure(diagnostics, reason, **details):
    if diagnostics is not None:
        diagnostics.update(reason=reason, **details)
    return False


def literal_scope_preserved(question: str, context: dict, supplied_filters: dict, base_filters: dict,
                            *, check_dates: bool = True, diagnostics: dict | None = None,
                            shared_question: str | None = None) -> bool:
    """Check visible literal entities and explicit date tokens, not inferred intent.

    ``shared_question`` is the whole question when ``question`` is one part of a
    plan: a name stated once for every part ("For BP, how many ... and how many
    ...") may be filtered in each part without being repeated in it.
    """
    effective = {**base_filters, **{key: value for key, value in supplied_filters.items() if value is not None}}
    dataset = effective_dataset_scope(supplied_filters.get("dataset"), base_filters.get("dataset", "all"))
    explicit = question_contract(question).get("explicit_datasets", [])
    if dataset is None or explicit and dataset != ("all" if len(explicit) > 1 else explicit[0]):
        return _scope_failure(diagnostics, "dataset_scope_mismatch")
    for key, choose in (("date_from", max), ("date_to", min)):
        bounds = [str(value) for value in (base_filters.get(key), supplied_filters.get(key)) if value]
        effective[key] = choose(bounds) if bounds else None
    mentions = []
    # Only fields that exist in the queried collection can make a name ambiguous:
    # native ads have no accounts and social posts have no publishers.
    dimensions = {"native": ("sponsors", "publishers"), "social": ("sponsors", "accounts")}.get(
        dataset, ("sponsors", "publishers", "accounts"))
    for dimension in dimensions:
        items = context.get(dimension) or []
        if isinstance(items, dict):
            items = items.get("options") or []
        for item in items:
            item = {"value": item} if isinstance(item, str) else item
            spellings = {item.get("value"), item.get("display")} - {None, ""}
            # Use the same bounded source aliases as the tool executor.
            aliases = _entity_keys(item["value"], dimension) if dimension != "accounts" else set()
            patterns = [re.escape(spelling) for spelling in spellings]
            patterns.extend(r"[\s._-]*".join(map(re.escape, spelling)) for spelling in aliases)
            for spelling in patterns:
                pattern = r"(?<![A-Za-z0-9_])" + spelling + r"(?![A-Za-z0-9_])"
                for match in re.finditer(pattern, question, flags=re.I):
                    mentions.append((match.start(), match.end(), dimension, item))
    covered = set()
    required = {}
    for start, end, dimension, item in sorted(mentions, key=lambda m: m[1] - m[0], reverse=True):
        if any(index in covered for index in range(start, end)):
            continue
        namespaces = {m[2] for m in mentions if m[0] == start and m[1] == end}
        same_namespace = {str(m[3]["value"]).strip().casefold() for m in mentions
                          if m[0] == start and m[1] == end and m[2] == dimension}
        if len(same_namespace) > 1:
            return _scope_failure(diagnostics, "ambiguous_entity_alias", dimension=dimension)
        if len(namespaces) > 1:
            prefix = question[max(0, start - 70):start]
            roles = {key for key, pattern in {
                "publishers": r"(?:publisher|outlet|newspaper|媒体|出版商)\s*[:=]?\s*['\"]?\s*$",
                "sponsors": r"(?:sponsor|company|advertiser|sponsored by|赞助方|公司)\s*[:=]?\s*['\"]?\s*$",
                "accounts": r"(?:account|账号|账户)\s*[:=]?\s*['\"]?\s*$",
            }.items() if re.search(pattern, prefix, re.I)}
            if not roles:
                roles = {m[2] for m in mentions if m[0] == start and m[1] == end
                         and str(m[3]["value"]).casefold() in {str(v).casefold() for v in base_filters.get(m[2]) or []}}
            if not roles and dataset == "social" and namespaces == {"sponsors", "accounts"}:
                # A company's own account carries the company name; without the
                # word "account" the question is about the company.
                roles = {"sponsors"}
            if len(roles) != 1:
                return _scope_failure(diagnostics, "ambiguous_entity_namespace")
            if dimension not in roles:
                continue
        covered.update(range(start, end))
        wanted = {str(value).strip().casefold() for value in item.get("source_variants") or [item["value"]]}
        required.setdefault(dimension, set()).update(wanted)
    for dimension in ("sponsors", "publishers", "accounts"):
        known = [item if isinstance(item, str) else item.get("value") for item in (
            (context.get(dimension) or {}).get("options", []) if isinstance(context.get(dimension), dict)
            else context.get(dimension) or [])]

        def expanded(values):
            # Both sides resolve names as the tool does: "ONGC CSR" also reads
            # the stored spelling "ONGC_CSR" (Q round: a correct request refused).
            return {str(canonical).strip().casefold() for value in values
                    for canonical in (canonical_source_values(str(value), dimension, known) or [value])}

        wanted = expanded(required.get(dimension) or base_filters.get(dimension) or [])
        selected = expanded(effective.get(dimension) or [])
        if wanted != selected:
            shared = _shared_entity_values(shared_question, context, dimension) if shared_question else set()
            if not (wanted <= selected and selected - wanted <= shared):
                return _scope_failure(diagnostics, "entity_scope_mismatch", dimension=dimension)
    if not check_dates:
        return True
    # Entity-name dates do not become publication-date constraints.
    date_text = ''.join(char if index not in covered else ' ' for index, char in enumerate(question))
    if _RELATIVE_CALENDAR.search(date_text):
        return _scope_failure(diagnostics, "relative_date_requires_reference")
    try:
        scope = _literal_date_scope(date_text)
    except (ValueError, OverflowError):
        return _scope_failure(diagnostics, "unsupported_date_expression")
    for key, choose, endpoint in (("date_from", max, scope[0] if scope else None),
                                  ("date_to", min, scope[1] if scope else None)):
        bounds = [str(value) for value in (base_filters.get(key), endpoint) if value]
        expected = choose(bounds) if bounds else None
        if effective.get(key) != expected:
            return _scope_failure(diagnostics, "date_endpoint_mismatch", dimension=key,
                                  expected=expected, actual=effective.get(key))
    return True


def statistics_request_preserves_question(question: str, context: dict, arguments: dict,
                                         base_filters: dict, *, diagnostics: dict | None = None,
                                         shared_question: str | None = None) -> bool:
    """Check literal scope plus requested time operation; never supply a count.

    This is a bounded omission guard, not general semantic interpretation. The
    executor remains responsible for canonical names and scope intersection.
    Compare complete period ranges rather than requiring them in outer filters.
    """
    filters = arguments.get("filters") or {}
    missing_date = bool(re.search(
        r"\b(?:no|unknown|missing|without)\s+(?:a\s+)?(?:publication\s+)?dates?\b"
        r"|\bpublication\s+dates?\s+(?:is|are)\s+(?:unknown|missing)\b|缺失日期|日期未知|没有.{0,6}日期|无日期",
        question, re.I))
    known_date = bool(re.search(
        r"\b(?:known|with\s+a)\s+(?:publication\s+)?dates?\b|已知日期|有.{0,6}发布日期",
        question, re.I))
    presence = filters.get("date_presence") or base_filters.get("date_presence") or "any"
    if missing_date and presence != "missing":
        return _scope_failure(diagnostics, "date_presence_mismatch")
    if known_date and not missing_date and presence != "known":
        range_excludes_missing = bool(filters.get("date_from") or filters.get("date_to"))
        if not range_excludes_missing and filters.get("include_unknown_dates", base_filters.get("include_unknown_dates", True)):
            return _scope_failure(diagnostics, "date_presence_mismatch")
    wants_share = bool(re.search(r"\b(?:percentage|percent|proportion|share)\b|百分比|占比", question, re.I))
    if wants_share and arguments.get("measure") != "share":
        return _scope_failure(diagnostics, "share_measure_missing")
    grouping_prompt = r"\b(?:which|what|list|show|how\s+many)\s+(?:(?:all|the|distinct|different|source-listed)\s+)*"
    requested_groups = {dimension for dimension, (names, extra) in {
        "publishers": (r"publishers|outlets|newspapers", r"\bby\s+(?:publisher|outlet)\b|哪些媒体|列出.{0,12}媒体"),
        "sponsors": (r"sponsors|companies|advertisers", r"\bby\s+(?:sponsor|company)\b|哪些赞助方|列出.{0,12}赞助"),
        "platforms": (r"platforms", r"\bby\s+platform\b|哪些平台"),
        "accounts": (r"accounts", r"\bby\s+account\b|哪些账号"),
    }.items() if re.search(grouping_prompt + r"(?:" + names + r")\b|" + extra, question, re.I)}
    if requested_groups and (len(requested_groups) != 1 or arguments.get("group_by") not in requested_groups):
        return _scope_failure(diagnostics, "grouping_mismatch")
    entities = dict(filters)
    denominator = arguments.get("denominator_filters") or {}
    if arguments.get("measure") == "share" and denominator:
        for dimension in ("publishers", "sponsors", "accounts"):
            entities[dimension] = list(dict.fromkeys([
                *(filters.get(dimension) or base_filters.get(dimension) or []),
                *(denominator.get(dimension) or []),
            ]))
        # Names occurring in the comparison group cannot hide a changed
        # numerator. For an explicit "... are sponsored by X" target, read
        # the target independently, inheriting only the comparison scope.
        target = re.search(r"\b(?:are|were|is|was)\s+(.+)$|(?:其中|当中).{0,8}?(?:有|是)(.+)$", question, re.I)
        if target and not literal_scope_preserved(
                next(part for part in target.groups() if part is not None), context, filters,
                {**base_filters, **denominator}, check_dates=False, diagnostics=diagnostics):
            return False
    if not literal_scope_preserved(question, context, entities, base_filters, check_dates=False,
                                   diagnostics=diagnostics, shared_question=shared_question):
        return False

    # A literal stored name containing a year is not a date constraint.
    time_text = question
    for dimension in ("publishers", "sponsors", "accounts"):
        items = context.get(dimension) or []
        if isinstance(items, dict):
            items = items.get("options") or []
        for item in items:
            value = item if isinstance(item, str) else item.get("value", "")
            if value:
                time_text = re.sub(re.escape(value), " ", time_text, flags=re.I)
    if _RELATIVE_CALENDAR.search(time_text):
        return _scope_failure(diagnostics, "relative_date_requires_reference")
    yearly = bool(re.search(r"\b(?:by|per|each)\s+(?:publication\s+)?year\b|\byearly\b|按年|每年|逐年", time_text, re.I))
    highest_year = bool(re.search(
        r"\b(?:which|what)\b.{0,60}\byears?\b.{0,70}\b(?:most|highest|largest|maximum|greatest)\b"
        r"|\b(?:most|highest|largest|maximum|greatest)\b.{0,70}\byears?\b|哪.{0,8}年.{0,12}(?:最多|最高)", time_text, re.I))
    if (yearly or highest_year) and arguments.get("group_by") != "years":
        return _scope_failure(diagnostics, "year_grouping_missing")
    if highest_year and arguments.get("ranking") != "highest":
        return _scope_failure(diagnostics, "year_ranking_missing")

    iso_dates = re.findall(r"\b\d{4}-\d{2}-\d{2}\b", time_text)
    years_only = re.sub(r"\b\d{4}-\d{2}-\d{2}\b", " ", time_text)
    years = re.findall(r"\b(?:19|20)\d{2}\b", years_only)
    comparing = bool(re.search(r"\b(?:compare|versus|vs)\b|比较|对比", time_text, re.I))
    try:
        single_scope = _literal_date_scope(time_text)
    except (ValueError, OverflowError):
        single_scope = None
    # Separately named years that do not form one range ("in 2014, and how many
    # in 2018"; "2014 年和 2018 年分别") ask for one count per period.
    if (not comparing and single_scope is None and len(set(years)) >= 2 and not iso_dates
            and not re.search(r"\b(?:between|from|since|through|until)\b|至|到|之间", time_text, re.I)):
        comparing = True
    # A named grouping/collection comparison can share one explicit interval.
    # Without that other comparison axis, do not replace a comparison by a total.
    other_comparison = bool(requested_groups) or len(question_contract(question)["explicit_datasets"]) > 1
    shared_interval = single_scope is not None and other_comparison
    expects_periods = comparing and not shared_interval and (len(iso_dates) >= 2 or len(set(years)) >= 2)
    periods = arguments.get("periods") or []
    if expects_periods or periods:
        if _unsupported_period_dates(time_text):
            return _scope_failure(diagnostics, "unsupported_period_expression")
        if not expects_periods or not 2 <= len(periods) <= 3:
            return _scope_failure(diagnostics, "period_comparison_mismatch")
        if len(iso_dates) in (4, 6):
            expected = list(zip(iso_dates[::2], iso_dates[1::2]))
        elif len(iso_dates) == 2:
            expected = [(day, day) for day in iso_dates]
        elif len(years) in (2, 3) and len(set(years)) == len(years):
            expected = [(year + "-01-01", year + "-12-31") for year in years]
        else:
            return _scope_failure(diagnostics, "unsupported_period_expression")
        requested = [(period.get("date_from"), period.get("date_to")) for period in periods]
        clipped = [(max(lower, base_filters.get("date_from") or lower),
                    min(upper, base_filters.get("date_to") or upper)) for lower, upper in expected]
        actual = [(max(str(lower), base_filters.get("date_from") or str(lower)),
                   min(str(upper), base_filters.get("date_to") or str(upper)))
                  for lower, upper in requested if lower and upper]
        if not (len(actual) == len(requested) == len(clipped) and sorted(actual) == sorted(clipped)):
            return _scope_failure(diagnostics, "period_endpoint_mismatch")
        return True
    return literal_scope_preserved(question, context, entities, base_filters, diagnostics=diagnostics,
                                   shared_question=shared_question)


def entity_dates_used_as_filters(question: str, context: dict, args: dict) -> bool:
    """Block dates borrowed only from a literal entity name, not real date scope.

    This narrow guard does not parse dates generally. Existing UI date filters
    remain authoritative; only new model-supplied date endpoints are checked.
    """
    filters = args.get("filters") or {}
    endpoints = [filters.get(key) for key in ("date_from", "date_to") if filters.get(key)]
    if not endpoints:
        return False
    remainder = question.casefold()
    name_years = set()
    for dimension in ("sponsors", "publishers", "accounts"):
        values = context.get(dimension) or []
        if isinstance(values, dict):
            values = values.get("options") or []
        for item in values:
            name = item if isinstance(item, str) else (item.get("value") or item.get("name") or "")
            if name and name.casefold() in remainder and re.search(r"[（(].*\d{4}.*[)）]", name):
                name_years.update(re.findall(r"\b\d{4}\b", name))
                remainder = remainder.replace(name.casefold(), " ")
    if not name_years or re.search(r"\b\d{4}\b|\b(?:since|before|after|between|during|until)\b|自|之前|之后|期间|年份|年内", remainder):
        return False
    return any(str(value)[:4] in name_years for value in endpoints)

_MENTION = re.compile(
    r"\b(?:mention(?:s|ed|ing)?|refer(?:s|red|ring)?\s+to|"
    r"discuss(?:es|ed|ing)?|contain(?:s|ed|ing)?|feature(?:s|d|ing)?)\b"
    r"|提及|提到|谈到|讨论|含有|涉及",
    re.IGNORECASE,
)
_FRAMING = re.compile(
    r"\b(?:present(?:s|ed|ing)?|position(?:s|ed|ing)?|portray(?:s|ed|ing)?|"
    r"acknowledg(?:e|es|ed|ing)|assert(?:s|ed|ing)?|claim(?:ed|ing)?|"
    r"emphasiz(?:e|es|ed|ing)|highlight(?:s|ed|ing)?|"
    r"suggest(?:s|ed|ing)?|recommend(?:s|ed|ing)?|"
    r"offer(?:s|ed|ing)?|redirect(?:s|ed|ing)?|argu(?:e|es|ed|ing)|"
    r"describ(?:e|es|ed|ing)|say(?:s|ing)?|said|stat(?:ed|ing))\b"
    r"|\bpoint(?:s|ed|ing)?\s+out\b"
    r"|\b(?:ads?|advertisements?|articles?|posts?|records?|they)\s+"
    r"(?:(?:also|explicitly|not|do|does|did|often|ever)\s+)*states?\b"
    r"|\bstates?\s+(?:that|whether|how|what|their|its|our|the|a|an)\b"
    r"|\bmake(?:s)?\s+[^?。？！\n]{0,80}\b(?:claims|recommendations)\b"
    r"|声称|宣称|强调|承认|断言|暗示|建议|宣传|转移注意|指出|表示|表述|描述"
    r"|(?:描述|定位|塑造).{0,80}?为|(?:将|把).{0,80}?(?:作为|视为|称为)",
    re.IGNORECASE,
)
_TOPIC = re.compile(
    r"\b(?:ads?|advertisements?|articles?|posts?|records?)\b[^?。？！\n]{0,120}"
    r"\b(?:about|on the topic of)\b|关于|以.{1,60}?为主题",
    re.IGNORECASE,
)
_DISCLOSURE = re.compile(
    r"\bdisclos(?:e|es|ed|ing|ure|ures)\b|披露|广告标识|付费标识|赞助标识",
    re.IGNORECASE,
)
# A count of records, not a figure stated inside one source.
_QUANTITY = _COUNT_REQUEST
# Something is selected across records ("which year has the most records"),
# so the question is not one text search. Broader than _LIST on purpose.
_SELECTION = re.compile(
    r"\b(?:which|list|show|find)\b[^?。？！\n]{0,100}"
    r"\b(?:ads?|advertisements?|articles?|posts?|records?)\b|哪些[^？?。！!；;]{0,30}?(?:广告|文章|帖子)",
    re.IGNORECASE,
)
_LIST = re.compile(
    # The sources themselves are selected: "which (of the) Total ads ...",
    # "list the posts ...". "Which start-up does the ad describe" or "which
    # country has ... according to the ad" asks about a thing inside a source.
    r"\bwhich\s+(?:of\s+)?(?:(?!(?:does|do|did|is|are|was|were|has|have|had)\b)[\w'’&.-]+\s+){0,5}?"
    r"(?:ads?|advertisements?|articles?|posts?|records?)\b"
    r"|\b(?:list|show|find)\b[^?。？！\n]{0,100}\b(?:ads|advertisements|articles|posts|records)\b"
    # A floor only; the planner's declared answer shape covers other wording.
    r"|\b(?:every|all|any)\s+(?:of\s+the\s+)?(?:[\w'’&.-]+\s+){0,4}?(?:ads?|advertisements?|articles?|posts?)\b"
    r"|(?:哪些|哪几|所有|全部)[^？?。！!；;]{0,30}?(?:广告|文章|帖子)"
    r"|(?:广告|文章|帖子)(?:里|中)[，,]?\s*有?(?:哪些|哪几)",
    re.IGNORECASE,
)
# A label predicate is metadata even when its literal value contains a content
# verb. Strip that value only, so a separate content condition remains visible.
_LABEL_PREDICATE = re.compile(
    r"\b(?:with|have|has|having|assigned|carry|carrying|under)\s+"
    r"(?:the\s+)?(?:historical\s+)?labels?\s*(?:=|:|of|named)?\s*"
    r"(?:['\"][^'\"]+['\"]|[\w-]+)"
    r"|\b(?:label(?:ed|led)\s+(?:as\s+)?)"
    r"(?:['\"][^'\"]+['\"]|[\w-]+)"
    r"|(?:带有|具有|有|属于|标为|标注为)\s*(?:历史)?标签\s*"
    r"(?:['\"][^'\"]+['\"]|[\w-]+)",
    re.IGNORECASE,
)
_QUOTED_LITERAL = re.compile(r"(['\"])[^'\"]*\1")
# What may follow "which ... ads" in a selection by stored fields only. The
# fields are a closed set; the ways an ad can talk about something are not
# (B1K: quote, cite, appeal to, tell, 认为, 描绘 were missed by _FRAMING), so an
# unlisted remainder is presumed to be a content condition.
_METADATA_SELECTION_EN = re.compile(
    r"\b(?:by|from|sponsor(?:ed)?\s+by|paid\s+for\s+by)\s+[\w'’&.-]+"
    r"|\b(?:that|which|were|was|are|is|have|has|been|did|do|does|the|a|an|all|any|of|and|or|"
    r"native|social|sponsored|published|ran|run|appeared|placed|posted|carried|bought|dated|"
    r"collected|archived|released|stored|currently|total|collection|dataset|database|archive|publish|"
    r"publication|account|accounts|platform|outlet|outlets|publisher|publishers|title|titled|"
    r"label|labels|labeled|labelled|keyword|keywords|url|link|"
    r"in|on|at|by|from|for|during|before|after|between|since|through|until|to|"
    r"year|years|month|months|date|dates|known|unknown|no|without|with|"
    r"january|february|march|april|may|june|july|august|september|october|november|december)\b"
    r"|\b\d{4}s?\b|\b\d{1,2}(?:st|nd|rd|th)?\b|\b[A-Z][\w'’&.-]*|[\s,;:?!.()\-–&'’]",
)
_METADATA_SELECTION_ZH = re.compile(r"[\sA-Za-z0-9'’&.,，、：:()（）\-？?。！!]|" + "|".join(sorted(
    "哪些 广告 原生 社交 帖子 文章 记录 篇 条 是 在 由 于 从 到 至 年 月 日 发布 发表 刊登 投放 赞助 上 中 里 的 "
    "之前 之后 以前 以后 期间 以来 集合 数据库 有 共 所有 全部 媒体 平台 账号 和 或 与 及 日期 未知 没有 "
    "标题 标签 网址 链接".split(), key=len, reverse=True)))


def restricts_to_named_source(question: str, name: str) -> bool:
    """The question binds `name` to a source role ("sponsored by X", "the account X", "X 赞助的").

    Then an unknown name ends the read: the collection has no such source. A
    name used without a role may still occur in the text and is searched.
    """
    name = " ".join((name or "").split())
    if len(name) < 2:
        return False
    text = " ".join(question.translate(str.maketrans({"’": "'"})).split())
    n = re.escape(name)
    return bool(re.search(
        rf"\b(?:sponsored|paid\s+for|published|posted|placed|run)\s+by\s+(?:the\s+)?{n}(?![\w-])"
        rf"|\b(?:account|accounts|sponsor|sponsors|publisher|outlet|company|advertiser)\s+(?:named\s+|called\s+)?[\"']?{n}(?![\w-])"
        rf"|(?<![\w-]){n}(?:'s|')?\s+(?:native\s+|social\s+)?(?:ads?|advertisements?|posts?|account|accounts|sponsored)\b"
        # "Chevron's October 2020 posts", "TotalEnergies' CNBC advertisements" (B1K-Q009).
        rf"|(?<![\w-]){n}(?:'s|')\s+(?:[\w.-]+\s+){{1,3}}?(?:native\s+|social\s+)?(?:ads|advertisements|posts|tweets)\b"
        rf"|(?:账号|赞助方|赞助商|媒体|广告主)\s*[“\"「]?{n}|{n}[”\"」]?\s*(?:赞助|账号|发布|刊登|投放)",
        text, re.IGNORECASE))


def question_source_scope(question: str, context: dict, dataset: str) -> dict:
    """Sources and the one period the question binds a content read to.

    Only a name in a source role counts ("Chevron's October 2020 posts",
    "ads sponsored by X", "X 发布的帖子"); a name the ads talk about ("ads that
    mention Chevron") is content, not scope. A period counts when the question
    states exactly one with a preposition and it is not in the future, so a
    target year ("net zero in 2050") is not read as a publication date.
    Returns {dimension: [stored values]} plus date_from/date_to when stated.
    A content search that omitted these answered for the wrong records (B1K-Q009).
    """
    dimensions = {"native": ("sponsors",), "social": ("sponsors", "accounts")}.get(dataset, ("sponsors", "accounts"))
    folded = question.casefold()
    found = {}
    for dimension in dimensions:
        items = context.get(dimension) or []
        if isinstance(items, dict):
            items = items.get("options") or []
        for item in items:
            item = {"value": item} if isinstance(item, str) else item
            spellings = {item.get("value"), item.get("display")} - {None, ""}
            if dimension != "accounts":
                spellings |= set(_entity_keys(item["value"], dimension))
            if any(len(s) >= 2 and s.casefold() in folded and restricts_to_named_source(question, s)
                   for s in spellings):
                found.setdefault(item["value"], set()).add(dimension)
    scope = {}
    for value, dims in found.items():
        if len(dims) > 1:
            # A company's own account carries its name; "the account X" picks the account.
            n = re.escape(value)
            dims = {"accounts"} if re.search(rf"\baccounts?\s+(?:named\s+|called\s+)?[\"'“]?{n}|{n}[\"'”]?\s+account|账号\s*[“\"]?{n}",
                                             question, re.I) else {"sponsors"}
        scope.setdefault(dims.pop(), []).append(value)
    periods = stated_periods(question)
    for match in _SOURCE_MONTH.finditer(question):
        # "October 2020 posts": a month naming the sources needs no preposition.
        year, month = int(match["year"]), _MONTHS[match["month"].casefold()]
        period = {"text": match.group(0), "date_from": date(year, month, 1).isoformat(),
                  "date_to": date(year, month, calendar.monthrange(year, month)[1]).isoformat()}
        if all((p["date_from"], p["date_to"]) != (period["date_from"], period["date_to"]) for p in periods):
            periods.append(period)
    if len(periods) == 1 and periods[0]["date_from"] <= date.today().isoformat():
        scope.update(date_from=periods[0]["date_from"], date_to=periods[0]["date_to"])
    return scope


def _selection_predicate(text: str) -> str:
    """What a "which ... ads" question asks beyond selecting by stored fields ("" when nothing)."""
    match = _LIST.search(text)
    if not match:
        return ""
    if re.search(r"[一-鿿]", match.group(0)):
        return _METADATA_SELECTION_ZH.sub("", text[:match.start()] + text[match.end():])
    return _METADATA_SELECTION_EN.sub("", text[match.end():])


_MONTHS = {name.casefold(): number for number in range(1, 13)
           for name in (calendar.month_name[number], calendar.month_abbr[number])}
_MONTHS["sept"] = 9
_MONTH = "|".join(sorted(_MONTHS, key=len, reverse=True))
_STATED_PERIOD = re.compile(
    rf"\b(?:in|during|from|on|posted|published)\s+(?:(?P<day>\d{{1,2}})\s+)?"
    rf"(?P<month>{_MONTH})\.?\s+(?:(?P<day2>\d{{1,2}}),?\s+)?(?P<year>(?:19|20)\d\d)\b"
    rf"|\b(?:in|during)\s+(?P<year_only>(?:19|20)\d\d)\b(?!\s*[-–/]\d)"
    r"|(?P<zh_year>(?:19|20)\d\d)\s*年\s*(?P<zh_month>1[0-2]|0?[1-9])\s*月(?:\s*(?P<zh_day>[1-3]?\d)\s*日)?",
    re.IGNORECASE)


_SOURCE_MONTH = re.compile(
    rf"(?<![\w-])(?P<month>{_MONTH})\.?\s+(?P<year>(?:19|20)\d\d)\s+(?:native\s+|social\s+)?(?:ads|advertisements|posts|tweets)(?![\w-])",
    re.IGNORECASE)


def stated_periods(question: str) -> list[dict]:
    """Calendar periods the question states with a preposition ("in September 2019").

    Used only to prefer sources dated inside the period when several equally
    supported sources exist; it never removes evidence. Quoted titles are
    ignored so a year inside a title is not read as a date restriction.
    """
    text = _QUOTED_LITERAL.sub(" ", question)
    periods = []
    for match in _STATED_PERIOD.finditer(text):
        try:
            if match["year_only"]:
                year = int(match["year_only"])
                start, end = date(year, 1, 1), date(year, 12, 31)
            else:
                year = int(match["year"] or match["zh_year"])
                month = _MONTHS[match["month"].casefold()] if match["month"] else int(match["zh_month"])
                day = match["day"] or match["day2"] or match["zh_day"]
                if day:
                    start = end = date(year, month, int(day))
                else:
                    start = date(year, month, 1)
                    end = date(year, month, calendar.monthrange(year, month)[1])
        except (KeyError, ValueError):
            continue
        period = {"text": match.group(0).strip(), "date_from": start.isoformat(), "date_to": end.isoformat()}
        if period not in periods:
            periods.append(period)
    return periods


def in_stated_period(published_at, periods: list[dict]):
    """True/False for a dated source, None when undated or no period is stated."""
    if not periods or not published_at:
        return None
    day = str(published_at)[:10]
    return any(item["date_from"] <= day <= item["date_to"] for item in periods)


_EACH_SOURCE = re.compile(
    r"\b(?:each|every|all)\s+(?:of\s+the\s+)?(?:(?:social|native|forbes|news)\s+)?"
    r"(?:ads?|advertisements?|posts?|articles?|sources?)\b"
    r"|\b(?:ads|advertisements|posts|articles)\b"
    r"|每(?:一)?(?:篇|条|则|个)|逐(?:篇|条)|分别引用|各篇|这些(?:广告|帖子|文章)|哪些",
    re.IGNORECASE)


def several_sources_requested(question: str) -> bool:
    """The question asks about several sources ("ads", "each ad"), not one.

    Used only to ask the answer to cover every supplied source that supports
    the point; it never adds evidence or changes the answer format.
    """
    return bool(_EACH_SOURCE.search(_QUOTED_LITERAL.sub(" ", question)))


def question_contract(question: str) -> dict:
    """Preserve explicit task limits before the model chooses a data tool.

    An absent cue means unspecified, not proof of a metadata-only question.
    Literal labels and NC_/SC_ IDs remain usable metadata filters. The rules
    intentionally avoid maintaining lists of companies or scientific topics.
    """
    normalized = " ".join(question.translate(str.maketrans({
        "‘": "'", "’": "'", "“": '"', "”": '"',
    })).split())
    predicate_text = _QUOTED_LITERAL.sub(" ", _LABEL_PREDICATE.sub(" ", strip_citation_clauses(normalized)))
    if _DISCLOSURE.search(predicate_text):
        task = "disclosure"
    elif _FRAMING.search(predicate_text):
        task = "content_framing"
    elif _MENTION.search(predicate_text) or _TOPIC.search(predicate_text):
        task = "content_mentions"
    elif not _GROUPING_REQUEST.search(predicate_text) and _selection_predicate(predicate_text):
        # Sources are selected by something other than stored fields: screen
        # them, or label the answer as examples, instead of citing a few.
        task = "content_unspecified"
    else:
        task = "metadata_or_unspecified"
    content = task != "metadata_or_unspecified"
    return {
        "policy": POLICY_VERSION,
        "task": task,
        "content_condition": content,
        "requires_complete_list": bool(content and _LIST.search(normalized)),
        # Structural only, independent of predicate detection: an answer to a
        # question that selects sources is labelled whenever it was not screened.
        "selects_sources": bool(_LIST.search(normalized)),
        "requires_content_count": bool(content and _QUANTITY.search(normalized)),
        "coverage": "retrieved_examples_only" if content else "tool_defined",
        "detection": "conservative_surface_cues_not_general_semantic_classification",
        "original_metadata_only": original_metadata_question(normalized),
        "content_search": content_search_question(normalized),
        "quoted_title": bool(_QUOTED_TITLE.search(normalized)),
        # Several things asked about one source are one text search, not a plan.
        "compound_read_request": _compound_read_request(predicate_text) and not content_search_question(normalized),
        # Stored fields of one record located by its title: find it, then read its metadata.
        "record_fields_lookup": _located_record_fields_read(normalized),
        # "Use both collections" names both even when only "native ad" and
        # "post" follow (B1K: 8 correct reads of both were blocked as native-only).
        "explicit_datasets": (["native", "social"] if _BOTH_DATASETS.search(predicate_text) else
                              [dataset for dataset, pattern in _DATASETS.items() if pattern.search(predicate_text)]),
    }


def metadata_content_clarification(question: str) -> str:
    """Explain the blocked operation without inventing a content result."""
    if re.search(r"[\u4e00-\u9fff]", question):
        return (
            "元数据统计无法判断广告是否提及或表达某种观点。请使用证据检索查看有原文支持的例子；"
            "完整广告名单或内容计数需要经过审查的逐篇标注。"
        )
    return (
        "Metadata counts cannot answer a condition about what an advertisement says. "
        "Use evidence search for supported examples; a complete matching-ad list or "
        "content count requires reviewed article annotations."
    )

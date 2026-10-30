"""Flatten metrics.json into the row tables the published dashboard reads: one JSON array of rows per table.

Every value comes from metrics.json (scripts/rag_metrics_report.py); this only reshapes it and writes each
rule, label and verdict in words. Free and offline.

    .venv/Scripts/python -X utf8 reports/rag_metrics_20261029/dashboard_tables.py --out <dir>
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
LABEL = {"relevant": "相关", "not_relevant": "不相关", "disputed": "有争议", "neutral": "中性", "unlabelled": "未标"}
VERDICT = {"matches": "符合", "does_not_match": "不符合", "unclear": "不确定"}
ROUTE = {"pass": "通过", "review": "待审", "exclude": "排除"}
REFERENCE = {"positive": "正例", "negative": "反例", "disputed": "有争议", "neutral": "中性"}
ANNOTATION = {"yes": "是", "no": "否", "unclear": "不确定", "unverified_yes": "未核实的是", "missing": "无标注"}
FIELD = {"publisher": "媒体", "sponsor": "赞助方", "date": "日期", "disclosure_head": "披露标签开头"}
STATUS = {"answered": "已回答", "insufficient_evidence": "证据不足", "service_unavailable": "服务不可用"}
CONTENT_CLASS = {"content_single": "单篇内容", "content_multi": "多篇内容", "content_period": "某段时间的内容",
                 "cross_collection": "跨数据集"}
DISAGREE = {"missed": "漏列", "wrong": "误列"}
# what each order is, by the order_kind metrics.json records; the 10-29 depth run is named apart
ORDER = {"read": "筛查读取记录的先后", "judge": "判官概率（从高到低重排）", "evidence": "证据列表顺序", "lookup": "标题查找结果"}
CONDENSED = "压缩排名：只在 15 篇已编码的广告里排"
FULL_RANK = "全库名次（未编码的广告当作不相关，MRR 只可能偏低）"
HUMAN_RUNS = {"h1023": "10-23 单次判定", "h1024": "10-24 三组分流（网站展示的那次）", "h1028": "10-28 确认后的标准"}
HUMAN_NOTES = {"h1028": "代码 a650f6f；两块合并（S3-e 协议）"}  # from .runtime/s3e_20261028/protocol.md
# A Chinese gloss of each frame, written for this report. The English definition (from ref_v2) is what the AI annotator
# and adjudicator judged against; this only helps reading.
FRAME_ZH = {
    "biofuel_transport": "把生物燃料说成交通或航空的解决办法",
    "cite_iea": "引用国际能源署（IEA）的预测",
    "efficiency_cheapest": "把提高能效说成减排或降本最便宜、最先该做的办法",
    "employee_story": "讲一位有名有姓的员工或工程师的个人故事",
    "ev_charging": "说电动车需要新的充电基础设施",
    "everyday_products": "强调日常用品离不开石油和天然气",
    "future_vision": "描绘 2030 或 2050 年能源体系的图景",
    "gas_cleaner_coal": "说天然气比煤干净",
    "gas_energy_security": "说天然气或 LNG 对能源安全很重要",
    "gas_partner_renew": "把天然气定位成可再生能源的伙伴或备用",
    "gas_transition": "把天然气说成过渡燃料或桥梁燃料",
    "industry_emits": "承认油气行业本身是主要排放源",
    "lng_asia_coal": "把 LNG 说成亚洲替代煤的办法",
    "methane_priority": "把减少甲烷排放说成优先事项",
    "national_interest": "诉诸民族自豪感或国家经济利益",
    "oil_needed_decades": "主张几十年内仍然需要石油和天然气",
    "paris_support": "表示支持《巴黎协定》的目标",
    "plastics_essential": "把塑料或石化产品说成现代生活必不可少",
    "quote_outside_expert": "引用外部专家（如学者或分析师）的话",
    "renew_intermittent": "说可再生能源不稳定、没有备用就不可靠",
    "renew_not_ready": "主张可再生能源还不能取代化石燃料",
    "scenario_uncertainty": "承认未来能源需求或能源情景不确定",
    "solar_cheaper": "说太阳能越来越便宜、有成本竞争力",
    "sponsor_innovator": "把赞助方定位成技术创新者",
    "sponsor_renew_invest": "说赞助方在投资可再生能源",
    "sponsor_startups": "说赞助方支持或投资初创企业",
    "tech_exploration": "说数字技术或计算让油气勘探更高效",
    "transition_decades": "承认能源转型要花几十年",
    "trilemma": "讲可负担、可靠和清洁能源之间的取舍",
    "university_partner": "突出与大学或研究机构的合作",
}
QUOTE_LIMIT = 300
# the read funnel's stages in order: (table field, metrics.json funnel key)
FUNNEL = (("f10", "first_10"), ("f40", "first_40"), ("f120", "first_120"), ("fread", "read"), ("flisted", "listed"))
LISTED_STAGE = "最终列入名单（= 召回）"
B1K_STAGES = {"f10": "读取记录前 10 篇", "f40": "读取记录前 40 篇", "fread": "读取记录里有的", "flisted": LISTED_STAGE}
DEPTH_STAGES = {"f10": "检索前 10 名", "f40": "检索前 40 名", "f120": "检索前 120 名"}


def r6(value):
    return None if value is None else round(value, 6)


def yes(value):
    return "是" if value else "否"


def f3(value):
    return "—" if value is None else f"{value:.3f}"


def clip(text, limit=QUOTE_LIMIT):
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[:limit - 1] + "…"


def mean_of(summary, key):
    return (summary["order_mean"].get(key) or {}).get("mean")


def groups_text(groups):
    return " / ".join(f"{ROUTE[k]} {groups[k][0]}（人工相关 {groups[k][1]}）" for k in ("pass", "review", "exclude"))


def forms_text(alternatives):
    if alternatives is None:
        return None
    return "；".join("/".join(a["forms"]) + ("（整词）" if a["whole_word"] else "") for a in alternatives)


def brief(row):
    return {"title": row.get("title") or "（无标题）", "sponsor": row.get("sponsor"), "publisher": row.get("publisher"),
            "date": (row.get("date") or "")[:10] or None}


def judge_text(j):
    """How the saved order differed from the judge's probability order the scores use: one question's, or a run's
    sum (where labels_moved counts questions)."""
    if not j["inversions"] and not j["without_probability"]:
        return "按判官概率从高到低；保存的顺序就是这个顺序"
    text = f"按判官概率从高到低重排；保存的顺序里有 {j['inversions']} 对和概率相反"
    if j["inversions"]:
        text += ("，都在人工标签相同的广告之间" if not j["across_labels"]
                 else f"，其中 {j['across_labels']} 对是一篇相关、一篇不相关")
    if j["without_probability"]:
        text += f"；{j['without_probability']} 篇没有概率，排在最后"
    moved = j["labels_moved"]
    if not moved:
        return text + "；重排前后每个名次上的人工标签都一样，所以排序指标不变"
    return text + ("；重排改变了相关广告所在的名次" if moved is True else f"；{moved} 题的相关广告因此换了名次")


def coverage_text(s):
    return "预期的题都有回答记录" if not s["missing"] else f"缺 {len(s['missing'])} 题的回答记录：{'、'.join(s['missing'])}"


def funnel_fields(counts, names, basis, missing, short=None):
    """A headline row's read funnel: each stage's share of the relevant ads, count and name (all None for a stage
    that was not measured, never 0), what the stages are based on (in short and in full), which were not measured,
    and the set differences between the relevant ads in the read record and those listed."""
    relevant = counts["relevant"]
    out = {"f_relevant": relevant, "f_short": short, "f_basis": basis, "f_missing": missing}
    for field, key in FUNNEL:
        n = counts.get(key)
        out.update({field: r6(n / relevant) if n is not None and relevant else None, f"{field}_n": n,
                    f"{field}_name": names[field] if n is not None else None})
    out["f_text"] = " → ".join([f"相关 {relevant}"] + [f"{out[f + '_name']} {out[f + '_n']}" for f, _ in FUNNEL
                                                      if out[f + "_n"] is not None])
    out.update({"not_read": relevant - counts["read"] if counts.get("read") is not None else None,
                "read_not_listed": counts.get("read_not_listed"), "listed_not_read": counts.get("listed_not_read")})
    return out


def first_read_text(s):
    """The first batch a run's screened answers recorded and how their read records compare with it, e.g.
    "40 篇；23/23 读够篇数，27/27 范围内全在记录里"."""
    batch = "、".join(f"{k} 篇" for k in s["first_read"]) or "—"
    b = s["first_batch"]
    parts = ([f"{b['read_target_count']}/{b['scope_at_least_target']} 读够篇数"] if b["scope_at_least_target"] else []) + (
        [f"{b['read_whole_scope']}/{b['scope_below_target']} 范围内全在记录里"] if b["scope_below_target"] else [])
    return f"{batch}；" + ("，".join(parts) or "没有记了首批目标的题")


def b1k_funnel(s):
    b = s["first_batch"]
    return funnel_fields(s["funnel"], B1K_STAGES,
                         f"已保存的筛查读取记录（读了哪些广告、先后）。运行记录的首批读取目标是 {'、'.join(s['first_read']) or '—'} 篇："
                         f"范围内可检索的广告不少于这么多的 {b['scope_at_least_target']} 个题次，{b['read_target_count']} 个"
                         f"读取记录够这个篇数（只核对篇数）；不足这么多的 {b['scope_below_target']} 个题次，"
                         f"{b['read_whole_scope']} 个范围内的广告都在记录里（按集合核对）；{b['read_on']} 个记录比首批目标长，"
                         f"最长 {s['max_read']} 篇" + (f"；{b['outside_scope_in_record']} 个记录里有本报告算作范围外的广告"
                                                     f"（都记为不相关）" if b["outside_scope_in_record"] else ""),
                         "检索前 120 名：没有记录（运行只存了筛查读取记录）", short="筛查读取记录")


def headline(m):
    H, S = m["human"]["summary"], m["b1k"]["summary"]
    info = {r["run"]: r for r in m["b1k"]["runs"]}
    articles = m["provenance"]["human"]["articles"]
    rows = []
    for run in ("h1024", "h1028", "h1023"):
        s, items = H[run], [r for r in m["human"]["questions"] if r["run"] == run]
        judge = run != "h1023"
        note = []
        if s.get("groups"):
            fw = s["final_with_flagged_micro"]
            note.append(f"{groups_text(s['groups'])}；把待审也算进名单：P {f3(fw['precision'])} R {f3(fw['recall'])} F1 {f3(fw['f1'])}")
        if run in HUMAN_NOTES:
            note.append(HUMAN_NOTES[run])
        note.append(f"NDCG@10 只作前排参考，衡量判官排得准不准，不是检索：{judge_text(s['judge_order'])}" if judge
                    else "NDCG@10 只作前排参考，按筛查读取记录的先后")
        alt = s.get("final_with_flagged_micro") or {}
        stages = {"fread": f"判定记录里有的（每题 {articles} 篇都有判定）", "flisted": LISTED_STAGE}
        rows.append({"key": f"human_{run[1:]}", "short": f"人工 {run[1:3]}-{run[3:]}", "set": "人工标注集", "kind": "list",
                     **funnel_fields(s["funnel"], stages, f"每题 {articles} 篇已编码的广告都有判定记录",
                                     f"读取记录前 10、前 40 篇：不适用（每题只给 {articles} 篇已编码的广告）",
                                     short=f"判定记录（每题 {articles} 篇）"),
                     "variant": HUMAN_RUNS[run], "truth": "人工逐句编码",
                     "alt_label": "把待审也算进名单" if alt else None, "alt_precision": r6(alt.get("precision")),
                     "alt_recall": r6(alt.get("recall")), "alt_f1": r6(alt.get("f1")),
                     "scale": f"{len(items)} 题 × {articles} 篇 = {sum(len(r['ads']) for r in items)} 对，"
                              f"{sum(r['n_relevant'] for r in items)} 对相关",
                     "run": f"{run[1:3]}-{run[3:]} · {'、'.join(s['screening_policy'])} · 数据版本 {next(iter(s['data_version']))[:8]}",
                     "precision": r6(s["final_micro"]["precision"]), "recall": r6(s["final_micro"]["recall"]),
                     "f1": r6(s["final_micro"]["f1"]), "mrr": None, "ndcg10": r6(mean_of(s, "ndcg@10")),
                     "order_basis": ORDER["judge" if judge else "read"], "note": "；".join(note)})
    d, depth = H["depth"], m["human"]["depth"]
    found = "；".join(f"前 {k} 名 {d['found'][str(k)]}/{d['relevant']}（{f3(d['pooled_full_recall'][f'r@{k}'])}）" for k in (10, 40, 120))
    full = d["full_rank_mean"]
    coverage = (f"{d['coded']} 个已编码的题—广告对都排到了" if not d["not_ranked"]
                else f"{d['coded']} 个已编码的题—广告对里有 {d['not_ranked']} 个没排到，算没找到")
    if d["flag_mismatch"]:
        coverage += f"；运行文件里抄的人工标记有 {d['flag_mismatch']} 处和人工编码不同，按人工编码算"
    counts = {"relevant": d["relevant"], **{f"first_{k}": d["found"][str(k)] for k in (10, 40, 120)}}
    rows.append({"key": "human_depth", "short": "人工 10-29 压缩排名", "set": "人工标注集", "variant": "10-29 当日检索排序",
                 "truth": "人工逐句编码", "kind": "list",
                 **funnel_fields(counts, DEPTH_STAGES, f"检索深度参考：10-29 当日检索对 {depth[0]['ranked']} 篇的名次",
                                 "读取记录、列入：没测（这次只排了名次，没有筛查）", short="全库检索名次"),
                 "scale": f"{d['questions']} 题 × {articles} 篇，{d['relevant']} 个相关的题—广告对在 {depth[0]['ranked']} 篇里的名次",
                 "run": f"10-29 · 数据版本 {m['provenance']['human']['depth']['data_version'][:8]}",
                 "precision": None, "recall": None, "f1": None, "mrr": None,
                 "ndcg10": r6(d["condensed_mean"]["ndcg@10"]["mean"]), "order_basis": CONDENSED,
                 "note": f"相关的题—广告对在全部 {depth[0]['ranked']} 篇里的名次：{found}；NDCG@10 只作前排参考，"
                         f"全库名次（未编码的广告当作不相关）是 {f3(full['ndcg@10']['mean'])}；{coverage}"})
    head = info["wB1"]
    run_text = (f"{head['from_utc'][5:10]} · {'、'.join(head['screening_policy'])} · 快照 {next(iter(head['data_version']))[:8]}")
    k = S["keyword"]["headline"]
    ref = k["final_reference_micro"]
    wrong = k["wrong_listings_by_reference"]
    rows.append({"key": "keyword", "short": "关键词题", "set": "合成·关键词题", "variant": "按字面关键词", "truth": "关键词规则（字面）",
                 "kind": "list", **b1k_funnel(k),
                 "alt_label": "按冻结参考 ref_v2", "alt_precision": r6(ref["precision"]), "alt_recall": r6(ref["recall"]),
                 "alt_f1": r6(ref["f1"]), "wrong_total": k["final_micro"]["fp"], "wrong_disputed": wrong.get("disputed", 0),
                 "wrong_negative": wrong.get("negative", 0), "wrong_unreviewed": wrong.get("not_reviewed", 0),
                 "scale": f"{k['questions']} 题（new6 跑两遍：wB1、wB2），{coverage_text(k)}", "run": run_text,
                 "precision": r6(k["final_micro"]["precision"]), "recall": r6(k["final_micro"]["recall"]),
                 "f1": r6(k["final_micro"]["f1"]), "mrr": None, "ndcg10": r6(mean_of(k, "ndcg@10")),
                 "order_basis": ORDER["read"],
                 "note": f"按 ref_v2（AI 认可的近义说法不算对也不算错）：P {f3(ref['precision'])} R {f3(ref['recall'])} "
                         f"F1 {f3(ref['f1'])}"})
    f = S["frame"]["headline"]
    rows.append({"key": "frame", "short": "框架题", "set": "合成·框架题", "variant": "按冻结参考 ref_v2", "truth": "AI 标注 + AI 裁定",
                 "kind": "list", **b1k_funnel(f),
                 "scale": f"{f['questions']} 题，{f['with_truth']} 题有正例，{coverage_text(f)}", "run": run_text,
                 "precision": r6(f["final_micro"]["precision"]), "recall": r6(f["final_micro"]["recall"]),
                 "f1": r6(f["final_micro"]["f1"]), "mrr": None, "ndcg10": r6(mean_of(f, "ndcg@10")),
                 "order_basis": ORDER["read"],
                 "note": f"{f['empty_truth']} 道无正例的题里 {f['empty_truth_correct']} 道一篇没列"})
    c = S["content"]["headline"]
    rows.append({"key": "content", "short": "内容题", "set": "合成·内容题", "variant": "按来源广告", "truth": "出题用的来源广告",
                 "kind": "content", "hit1": r6(mean_of(c, "hit@1")), "hit5": r6(mean_of(c, "hit@5")),
                 "cited": r6(c["source_cited"]["mean"]),
                 "scale": f"{c['questions']} 题，{coverage_text(c)}", "run": run_text, "precision": None, "recall": None,
                 "f1": None, "mrr": r6(mean_of(c, "rr")), "ndcg10": r6(mean_of(c, "ndcg@10")), "order_basis": ORDER["evidence"],
                 "note": f"来源排第 1：{f3(mean_of(c, 'hit@1'))}；前 5：{f3(mean_of(c, 'hit@5'))}；"
                         f"回答引用了来源：{f3(c['source_cited']['mean'])}；{c['no_evidence_list']} 题没有证据列表，排序记 0"})
    t = S["title"]["headline"]
    rows.append({"key": "title", "short": "标题题", "set": "合成·标题题", "variant": "按标题查找", "truth": "题里给的标题 + 记录字段",
                 "kind": "content", "hit1": r6(mean_of(t, "hit@1")), "record_found": r6(t["record_found"]["mean"]),
                 "fields_correct": r6(t["fields_correct"]["mean"]),
                 "scale": f"{t['questions']} 题，{coverage_text(t)}", "run": run_text, "precision": None, "recall": None,
                 "f1": None, "mrr": r6(mean_of(t, "rr")), "ndcg10": None, "order_basis": ORDER["lookup"],
                 "note": f"找到对的那篇：{f3(t['record_found']['mean'])}；字段全对：{f3(t['fields_correct']['mean'])}"})
    return rows


def runs_table(m):
    S, info, rows = m["b1k"]["summary"], {r["run"]: r for r in m["b1k"]["runs"]}, []
    for kind in ("keyword", "frame", "content", "title"):
        for name in [*info, "headline"]:
            s, meta = S[kind][name], info.get(name)
            row = {"key": f"{kind}|{name}", "kind": kind, "run": "wB1+wB2" if name == "headline" else name,
                   "question_set": meta["question_set"] if meta else "new6",
                   "when": f"{meta['from_utc'][5:10]} {meta['from_utc'][11:16]}–{meta['to_utc'][11:16]}" if meta else "两遍合计",
                   "policy": "、".join(p.replace("list-screening-", "") for p in meta["screening_policy"]) if meta else "v17",
                   "answers": meta["answers"] if meta else None,
                   "not_answered": "、".join(f"{k} {v}" for k, v in meta["not_answered"].items()) or "0" if meta else None,
                   "order_check": (f"{meta['order_check']['rank_equals_position']}/{meta['order_check']['matched_with_rank']}"
                                   if meta else None),
                   "questions": s["questions"], "missing": len(s["missing"]), "with_truth": s["with_truth"],
                   "empty_order": s["empty_order"], "empty_ok": f"{s['empty_truth_correct']}/{s['empty_truth']}",
                   "mrr": r6(mean_of(s, "rr")), "ndcg10": r6(mean_of(s, "ndcg@10"))}
            for basis, prefix in (("final_micro", ""), ("final_reference_micro", "ref_"), ("final_old_scorer_micro", "old_")):
                if s.get(basis):
                    row.update({f"{prefix}precision": r6(s[basis]["precision"]), f"{prefix}recall": r6(s[basis]["recall"]),
                                f"{prefix}f1": r6(s[basis]["f1"])})
            if kind in ("keyword", "frame"):
                fun = funnel_fields(s["funnel"], B1K_STAGES, None, None)
                row.update({"set": "合成·关键词题" if kind == "keyword" else "合成·框架题", "order": ORDER["read"],
                            "k_note": "NDCG@120：按读取记录的先后，截到第 120 篇",
                            "ndcg120": r6(mean_of(s, "ndcg@120")), "p10": r6(mean_of(s, "p@10")),
                            "pmax10": r6(mean_of(s, "pmax@10")), "not_screened": "、".join(s["not_screened"]) or "—",
                            "first_read": first_read_text(s), "max_read": s["max_read"],
                            **{key: fun[key] for key in ("f_relevant", "f10", "f40", "fread", "flisted", "not_read",
                                                         "read_not_listed", "listed_not_read")}})
            elif kind == "content":
                row.update({"hit1": r6(mean_of(s, "hit@1")), "hit5": r6(mean_of(s, "hit@5")),
                            "cited": r6(s["source_cited"]["mean"]), "no_evidence": s["no_evidence_list"]})
            else:
                row.update({key: r6(s[key]["mean"]) for key in ("record_found", "title_exact", "fields_correct")})
            rows.append(row)
    for run in ("h1023", "h1024", "h1028"):
        s = m["human"]["summary"][run]
        row = {"key": f"human|{run}", "kind": "human", "set": "人工标注集", "run": HUMAN_RUNS[run],
               "k_note": "NDCG@15：每题 15 篇全排",
               "policy": "、".join(s["screening_policy"]),
               "questions": s["questions"], "missing": len(s["missing"]), "precision": r6(s["final_micro"]["precision"]),
               "recall": r6(s["final_micro"]["recall"]), "f1": r6(s["final_micro"]["f1"]),
               "mrr": r6(mean_of(s, "rr")), "ndcg10": r6(mean_of(s, "ndcg@10")), "ndcg15": r6(mean_of(s, "ndcg@15")),
               "p10": r6(mean_of(s, "p@10")), "pmax10": r6(mean_of(s, "pmax@10")), "r10": r6(mean_of(s, "r@10")),
               "order": ORDER["judge" if run != "h1023" else "read"],
               "groups": groups_text(s["groups"]) if s.get("groups") else "—"}
        if s.get("final_with_flagged_micro"):
            fw = s["final_with_flagged_micro"]
            row.update({"flagged_precision": r6(fw["precision"]), "flagged_recall": r6(fw["recall"]), "flagged_f1": r6(fw["f1"])})
        rows.append(row)
    # the 10-29 ranking, both ways, for the checks page's list MRR and whole-length NDCG
    d = m["human"]["summary"]["depth"]
    ranked = m["human"]["depth"][0]["ranked"]
    for key, run, order, means, whole, k_note in (
            ("condensed", "10-29 压缩排名", CONDENSED, d["condensed_mean"], "ndcg15", "NDCG@15：只排已编码的 15 篇"),
            ("full", "10-29 全库名次", FULL_RANK, d["full_rank_mean"], "ndcg120",
             f"NDCG@120：{ranked} 篇里的前 120 名，不是全长")):
        rows.append({"key": f"depth|{key}", "kind": "depth", "set": "人工标注集", "run": run, "order": order, "k_note": k_note,
                     "questions": d["questions"], "mrr": r6(means["rr"]["mean"]), "ndcg10": r6(means["ndcg@10"]["mean"]),
                     whole: r6(means["ndcg@" + whole[4:]]["mean"])})
    return rows


def order_note(r):
    """Where one human question's order comes from, with the check behind it."""
    if r["order_kind"] == "judge":
        return judge_text(r["judge_order"])
    matched, same = r["order_check"]
    return f"按筛查读取记录的先后；被判“符合”且记了检索名次的 {matched} 篇里，{same} 篇的名次等于记录里的位置"


def q_human(m):
    depth = {d["label"]: d for d in m["human"]["depth"]}
    rows = []
    for r in m["human"]["questions"]:
        c, o, d = r["criterion"] or {}, r["order"], depth.get(r["label"])
        rules = [*("算：" + x for x in c.get("counts", [])), *("不算：" + x for x in c.get("does_not_count", []))]
        found = ("；".join(f"前 {k} 名 {round(d['full_rank'][f'r@{k}'] * d['n_relevant'])}/{d['n_relevant']}"
                            for k in (10, 40, 120)) if d else None)
        rows.append({"key": f"human|{r['run']}|{r['label']}", "run": r["run"], "label": r["label"], "question": r["question"],
                     "rules": "；".join(rules) or "（这次没有书面规则，按问题原文判）",
                     "searches": " ｜ ".join(r["searches"]) or "（没有记录）", "relevant": r["n_relevant"],
                     "listed": r["n_listed"], "flagged": r["n_flagged"], **{k: r["final"][k] for k in ("tp", "fp", "fn")},
                     "precision": r6(r["final"]["precision"]), "recall": r6(r["final"]["recall"]), "f1": r6(r["final"]["f1"]),
                     "ndcg10": r6(o["ndcg@10"]), "read_all": f"{r['funnel']['read']}/{r['funnel']['relevant']}",
                     "order": ORDER[r["order_kind"]], "order_note": order_note(r),
                     "groups": groups_text(r["groups"]) if r.get("groups") else "—", "depth_found": found,
                     "depth_ndcg10": r6(d["condensed"]["ndcg@10"]) if d else None,
                     "depth_full_ndcg10": r6(d["full_rank"]["ndcg@10"]) if d else None})
    return rows


def ads_human(m):
    ranks = {(d["label"], a["record_id"]): a["rank"] for d in m["human"]["depth"] for a in d["ranks"]}
    rows = []
    for r in m["human"]["questions"]:
        for a in r["ads"]:
            rows.append({"key": f"human|{r['run']}|{r['label']}|{a['record_id']}", "q": f"human|{r['run']}|{r['label']}",
                         "position": a["position"], "saved_position": a["saved_position"], "doc": a["doc"], **brief(a),
                         "label": LABEL[a["label"]],
                         "coded": " ／ ".join(clip(x, 200) for x in a["coded_sentences"]) or "—",
                         "verdict": VERDICT.get(a["verdict"], a["verdict"] or "—"), "route": ROUTE.get(a["route"], "—"),
                         "meets": a["meets"], "listed": yes(a["listed"]), "disagree": DISAGREE.get(a["disagreement"]),
                         "quote": clip(a["quote"]) or "—", "depth_rank": ranks.get((r["label"], a["record_id"]))})
    return rows


def funnel_text(f):
    """One list question's funnel in words."""
    if not f["relevant"]:
        return "没有相关广告"
    text = (f"相关 {f['relevant']} 篇：读取记录前 10 篇里 {f['first_10']} 篇，前 40 篇里 {f['first_40']} 篇，"
            f"记录里共 {f['read']} 篇（累计）；最终列入 {f['listed']} 篇，在记录里但没列入 {f['read_not_listed']} 篇")
    return text + (f"，列入但不在读取记录里 {f['listed_not_read']} 篇" if f["listed_not_read"] else "")


def read_note(r):
    """One list question's saved read record against the first batch it recorded, with the searchable ads in scope
    as this report counts them (the run's own scope_total counts more): a small scope by set, a wide one by count."""
    if not r["screened"]:
        return "没走名单筛查，筛查读取记录为空"
    batch, n, in_scope = r.get("first_read"), r["n_read"], r["criterion"]["ads_in_scope"]
    outside = f"；记录里有 {r['read_outside_scope']} 篇在本报告算的范围外" if r.get("read_outside_scope") else ""
    if batch is None:
        return f"读取记录 {n} 篇（运行记录没有首批目标）" + outside
    text = f"读取记录 {n} 篇；首批目标 {batch} 篇"
    if in_scope < batch:
        missed = r["in_scope_not_read"]
        text += f"，范围内可检索的只有 {in_scope} 篇，" + (f"其中 {missed} 篇不在记录里" if missed else "都在记录里")
    elif n < batch:
        text += "，记录不够首批目标的篇数"
    elif n > batch:
        text += f"，比首批目标多 {n - batch} 篇"
    return text + outside


def not_screened_text(r):
    """Why a list question has no read order, from the answer's recorded route and status only."""
    route, status = r.get("route"), r["status"]
    state = STATUS.get(status, status or "没有状态")
    if status not in ("answered", "insufficient_evidence"):
        how = f"回答失败（{state}）"
    elif route == "clarify":
        how = "反问了用户"
    elif route == "evidence":
        how = "直接给了证据回答" + ("（证据不足）" if status == "insufficient_evidence" else "")
    else:
        how = f"走了 {route} 路线（{state}）" if route else f"路线没有记录（{state}）"
    return f"否：{how}，筛查读取记录为空，" + ("相关的都记作不在记录里，排序记 0" if r["n_relevant"] else "这题没有正例，不算排序")


def list_common(r):
    o = r["order"] or {}
    return {"key": f"{'keyword' if r['group'] == 'T1' else 'frame'}|{r['run']}|{r['query_id']}", "run": r["run"],
            "qid": r["query_id"], "question": r["question"], "scope": r["criterion"]["scope_words"],
            "in_scope": r["criterion"]["ads_in_scope"], "searches": " ｜ ".join(r["searches"]) or "（没有记录）",
            "relevant": r["n_relevant"], "listed": r["n_listed"], "read": r["n_read"],
            "screened": "是" if r["screened"] else not_screened_text(r),
            **{k: r["final"][k] for k in ("tp", "fp", "fn")}, "precision": r6(r["final"]["precision"]),
            "recall": r6(r["final"]["recall"]), "f1": r6(r["final"]["f1"]), "ndcg10": r6(o.get("ndcg@10")),
            "f10_n": r["funnel"]["first_10"], "f40_n": r["funnel"]["first_40"], "fread_n": r["funnel"]["read"],
            "funnel": funnel_text(r["funnel"]), "read_note": read_note(r),
            "status": STATUS.get(r["status"], r["status"])}


def q_keyword(m):
    rows = []
    for r in m["b1k"]["questions"]["keyword"]:
        c, ref, wrong = r["criterion"], r["final_reference"], r["final"]["fp_by_reference"]
        rows.append({**list_common(r), "rule": c["rule"], "forms": forms_text(c["alternatives"]) or "（没有展开成写法，按正则原文匹配）",
                     "truth_check": "一致" if c["truth_matches_rule"] else "不一致",
                     "ref_precision": r6(ref["precision"]), "ref_recall": r6(ref["recall"]), "ref_f1": r6(ref["f1"]),
                     "wrong_disputed": wrong.get("disputed", 0), "wrong_negative": wrong.get("negative", 0),
                     "wrong_unreviewed": wrong.get("not_reviewed", 0)})
    return rows


def q_frame(m):
    rows = []
    for r in m["b1k"]["questions"]["frame"]:
        c = r["criterion"]
        counts = "；".join(f"{ANNOTATION.get(k, k)} {v}" for k, v in sorted(c["annotation_counts"].items(), key=lambda kv: (-kv[1], kv[0])))
        rows.append({**list_common(r), "frame_id": c["frame_id"], "frame": FRAME_ZH[c["frame_id"]], "frame_en": c["en"],
                     "annotations": counts, "unlabelled": r["final"]["unlabelled_listed"],
                     "empty_ok": "—" if r["n_relevant"] else yes(not r["n_listed"])})
    return rows


def ads_list(m, kind):
    rows = []
    for r in m["b1k"]["questions"][kind]:
        for a in r.get("ads") or []:
            why = a["why"]
            row = {"key": f"{kind}|{r['run']}|{r['query_id']}|{a['record_id']}", "q": f"{kind}|{r['run']}|{r['query_id']}",
                   "position": a["position"], **brief(a), "label": LABEL[a["label"]],
                   "reference": REFERENCE.get(why.get("reference"), "—"),
                   "adjudicator": {"yes": "认可", "no": "不认可"}.get(why.get("adjudicator"), "—"),
                   "adjudicator_quote": clip(why.get("adjudicator_quote")) or "—", "in_scope": yes(why["in_scope"]),
                   "verdict": VERDICT.get(a["verdict"], a["verdict"]) if a["position"] else "不在记录里",
                   "listed": yes(a["listed"]), "disagree": DISAGREE.get(a["disagreement"]), "quote": clip(a["quote"]) or "—"}
            if kind == "keyword":
                row.update({"forms": "；".join(f"{form} ×{n}" for form, n in why["forms"]) or "（没有）",
                            "in_title": yes(why["in_title"])})
            else:
                row["annotation"] = ANNOTATION.get(why.get("annotation"), "无标注")
            rows.append(row)
    return rows


def q_content(m):
    rows = []
    for r in m["b1k"]["questions"]["content"]:
        c, o = r["criterion"], r["order"] or {}
        sources = "；".join(" · ".join(x for x in (s.get("title") or "（无标题）", s.get("sponsor"), s.get("publisher"),
                                                   (s.get("date") or "")[:10]) if x) for s in c["sources"])
        rows.append({"key": f"content|{r['run']}|{r['query_id']}", "run": r["run"], "qid": r["query_id"],
                     "question": r["question"], "class": CONTENT_CLASS.get(r["class"], r["class"]), "sources": sources,
                     "quotes": " ／ ".join(f"「{clip(q, 240)}」" for q in c["quotes"]) or "—",
                     "points": " ／ ".join(clip(p, 240) for p in c["required_points"]) or "—",
                     "searches": " ｜ ".join(r["searches"]) or "（没有记录）", "relevant": r["n_relevant"],
                     "evidence": r["evidence_records"], "cited_n": r["sources_cited"], "rr": r6(o.get("rr")),
                     "first": o.get("first_relevant"), "hit1": r6(o.get("hit@1")), "hit5": r6(o.get("hit@5")),
                     "ndcg10": r6(o.get("ndcg@10")), "status": STATUS.get(r["status"], r["status"])})
    return rows


def ads_content(m):
    rows = []
    for r in m["b1k"]["questions"]["content"]:
        for a in r.get("ads") or []:
            rows.append({"key": f"content|{r['run']}|{r['query_id']}|{a['record_id']}", "q": f"content|{r['run']}|{r['query_id']}",
                         "position": a["position"], **brief(a), "label": "来源" if a["label"] == "relevant" else "不是来源",
                         "cited": yes(a["cited"]), "disagree": "来源没被引用" if a["disagreement"] == "missed" else None})
    return rows


def q_title(m):
    rows = []
    for r in m["b1k"]["questions"]["title"]:
        fields = "；".join(f"{FIELD[k]}：标准 {v['expected']} ｜ 回答 {v['shown'] if v['shown'] is not None else '（没有）'}"
                          f" {'✓' if v['match'] else '✗'}" for k, v in r["fields"].items())
        rows.append({"key": f"title|{r['run']}|{r['query_id']}", "run": r["run"], "qid": r["query_id"],
                     "question": r["question"], "class": "按标题查披露标签" if r["class"] == "disclosure_by_title" else "按标题查字段",
                     "title": " ／ ".join(r["criterion"]["titles"]), "searched": " ／ ".join(t or "" for t in r["title_searched"]),
                     "exact": yes(r["title_exact"]), "found": yes(r["record_found"]), "fields": fields,
                     "fields_ok": yes(r["fields_correct"]), "answer": clip(r["answer"], 240), "rr": r6((r["order"] or {}).get("rr"))})
    return rows


def rules_table(m):
    by_rule = {}
    for r in m["b1k"]["questions"]["keyword"]:
        item = by_rule.setdefault(r["criterion"]["rule"], {"forms": forms_text(r["criterion"]["alternatives"]),
                                                             "questions": set(), "example": r["question"]})
        item["questions"].add(r["query_id"])
    return [{"key": f"rule-{i:02d}", "rule": rule, "forms": item["forms"] or "（没有展开成写法，按正则原文匹配）",
             "questions": len(item["questions"]), "ids": "、".join(sorted(item["questions"])), "example": item["example"]}
            for i, (rule, item) in enumerate(sorted(by_rule.items(), key=lambda kv: kv[0].lower()), 1)]


def frames_table(m):
    by_frame = {}
    for r in m["b1k"]["questions"]["frame"]:
        c = r["criterion"]
        item = by_frame.setdefault(c["frame_id"], {"en": c["en"], "questions": set()})
        item["questions"].add(r["query_id"])
    return [{"key": fid, "zh": FRAME_ZH[fid], "en": item["en"], "questions": len(item["questions"]),
             "ids": "、".join(sorted(item["questions"]))} for fid, item in sorted(by_frame.items())]


def checks_table(m):
    """Earlier published numbers, copied from where they were published, beside this report's at the same precision."""
    H, primer, old = m["human"]["summary"], m["checks"]["primer_recomputed"], m["checks"]["old_scorer"]
    shipped = m["human"]["shipped_groups"]

    def groups(g):
        return " / ".join(f"{g[k][0]}[{g[k][1]}]" for k in ("pass", "review", "exclude"))

    def pct(s):
        return f"P {s['precision']:.0%} / R {s['recall']:.0%}"

    h23, h24, h24f, h28 = (H["h1023"]["final_micro"], H["h1024"]["final_micro"], H["h1024"]["final_with_flagged_micro"],
                           H["h1028"]["final_micro"])
    rows = [
        ("h1023", "10-23 单次判定的名单", "TP 29、FP 8、FN 0；P 0.78 / R 1.00 / F1 0.88", "CF18（client_finish.md）",
         f"TP {h23['tp']}、FP {h23['fp']}、FN {h23['fn']}；P {h23['precision']:.2f} / R {h23['recall']:.2f} / F1 {h23['f1']:.2f}"),
        ("h1024", "10-24 三组（方括号里是人工相关数）",
         " / ".join(f"{shipped[k]}[{shipped[k + '_human_yes']}]" for k in ("pass", "review", "exclude")),
         "网站记录 relevance_validation.v1.json", groups(H["h1024"]["groups"])),
        ("h1024p", "10-24 入选组；入选 + 待审", "P 83% / R 86% / F1 0.85；57% / 100%", "C20 英文说明草稿（10-29，私有）",
         f"{pct(h24)} / F1 {h24['f1']:.2f}；{h24f['precision']:.0%} / {h24f['recall']:.0%}"),
        ("h1028", "10-28 三组；列出的名单", "30[24] / 21[5] / 24[0]；精确率 0.80，召回 0.83", "S3-e 结果（work.md）",
         f"{groups(H['h1028']['groups'])}；精确率 {h28['precision']:.2f}，召回 {h28['recall']:.2f}"),
        ("primer", "讲解页：排序（它的算法跳过读取记录为空的题）", "列表题 MRR 0.76、NDCG@120 0.76；内容题 MRR 0.90",
         "C20 英文说明草稿（10-29，私有）",
         f"列表题 MRR {primer['mrr']:.2f}、NDCG@120 {primer['ndcg@120']:.2f}；内容题 MRR {primer['content_mrr']:.2f}"),
        ("curve", "排序曲线：合计 R@120；内容题来源排第 1", "0.941；0.869", "reports/retrieval_rank_20261027",
         f"{primer['pooled_recall@120']:.3f}；{primer['content_hit@1']:.3f}"),
    ]
    out = [{"key": key, "item": item, "before": before, "source": source, "now": now,
            "status": "一致" if before == now else "不一致"} for key, item, before, source, now in rows]
    for kind, words in (("content", "内容题：回答引用来源的比例"), ("title", "标题题：对错"),
                        ("keyword", "关键词题：按当时的算法重算的列对数、正例数、列出数、精确率、召回")):
        c = old[kind]
        differs = "、".join(f"{d['run']} {d['query_id']}（{'、'.join(d['fields'])}）" for d in c["differs"])
        out.append({"key": f"old_{kind}", "item": words, "before": "当时评分器的逐题分数", "source": "各运行目录的 scores_*.json",
                    "now": f"{c['same']}/{c['total']} 题一致" + (f"；不一致：{differs}" if differs else ""),
                    "status": "一致" if c["same"] == c["total"] else f"{c['total'] - c['same']} 题不一致"})
    for item in old["adjudication_changed"]:
        then, title = item["then"], item.get("title")
        then_words = ("没问过" if not then else
                      f"回答“{'是' if then['verdict'] == 'yes' else '否'}”，引用“{clip(then['quote'], 120)}”"
                      + ("，正文里找得到，算认可" if then["accepted"] else "，正文里找不到这句原文，不算认可"))
        ref_words = (f"{REFERENCE.get(item['reference'], item['reference'] or '没有记录')}，AI 裁判"
                     f"{ {'yes': '认可', 'no': '不认可'}.get(item['reference_adjudicator'], '没给结论') }"
                     + (f"，引用“{clip(item['reference_quote'], 120)}”" if item.get("reference_quote") else ""))
        out.append({"key": f"adj|{item['run']}|{item['query_id']}|{item['record_id']}",
                    "item": f"关键词题 {item['run']} {item['query_id']}：广告《{title or item['record_id']}》",
                    "before": f"评分当时的 AI 裁定：{then_words}", "source": "该运行目录 cache/adjudicate-*.json",
                    "now": f"ref_v2：{ref_words}", "status": "两种口径对这篇结论不同"})
    return out


TABLES = {"headline": headline, "runs": runs_table, "q_human": q_human, "ads_human": ads_human, "q_keyword": q_keyword,
          "ads_keyword": lambda m: ads_list(m, "keyword"), "q_frame": q_frame, "ads_frame": lambda m: ads_list(m, "frame"),
          "q_content": q_content, "ads_content": ads_content, "q_title": q_title, "rules": rules_table,
          "frames": frames_table, "checks": checks_table}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--metrics", type=Path, default=HERE / "metrics.json")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    m = json.load(open(args.metrics, encoding="utf-8"))
    args.out.mkdir(parents=True, exist_ok=True)
    for name, build in TABLES.items():
        rows = build(m)
        columns = list(dict.fromkeys(key for row in rows for key in row))  # every row has every column, in one order
        rows = [{key: row.get(key) for key in columns} for row in rows]
        assert len({row["key"] for row in rows}) == len(rows), f"{name}: keys repeat"
        text = json.dumps(rows, ensure_ascii=False, separators=(",", ":"))
        (args.out / f"{name}.json").write_text(text, encoding="utf-8")
        print(f"{name}: {len(rows)} rows, {len(text.encode('utf-8')) / 1024:.0f} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Prepare grouped content evaluation; never call a model or create gold.

The original 24 client questions remain a seen regression baseline. Candidate
variants test engineering coverage only until independently reviewed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


def digest(value: str) -> str:
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def normalized_tokens(value: str) -> list[str]:
    return re.findall(r'[a-z0-9]+', value.casefold())


def canonical_url(value: str) -> str:
    """Drop only known analytics parameters, retaining content parameters."""
    parts = urlsplit(value.strip())
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
             if not k.casefold().startswith('utm_') and k.casefold() not in {'gclid', 'fbclid'}]
    return urlunsplit((parts.scheme.casefold(), parts.netloc.casefold(), parts.path,
                      urlencode(sorted(query)), ''))


def shingles(tokens: list[str]) -> set[tuple[str, ...]]:
    return {tuple(tokens[i:i + 5]) for i in range(max(0, len(tokens) - 4))}


def character_shingles(tokens: list[str]) -> set[str]:
    compact = ''.join(tokens)
    return {compact[i:i + 9] for i in range(max(0, len(compact) - 8))}


def article_groups(records: list[dict], threshold: float = .88) -> tuple[dict, list[dict]]:
    """Conservatively group exact copies, same URLs and long near copies.

    Heuristics produce candidates requiring source review. They are not a
    declaration that two advertisements have the same counting identity.
    """
    if not 0 < threshold <= 1:
        raise ValueError('invalid near-duplicate threshold')
    ids = [r['record_id'] for r in records]
    if len(ids) != len(set(ids)):
        raise ValueError('duplicate record identity')
    parent = {rid: rid for rid in ids}

    def find(rid: str) -> str:
        while parent[rid] != rid:
            parent[rid] = parent[parent[rid]]
            rid = parent[rid]
        return rid

    def union(a: str, b: str) -> None:
        a, b = find(a), find(b)
        if a != b:
            parent[max(a, b)] = min(a, b)

    prepared = []
    for record in records:
        tokens = normalized_tokens(record['body'])
        prepared.append((record['record_id'], canonical_url(record['url']),
                         digest(' '.join(tokens)), len(tokens), shingles(tokens), character_shingles(tokens)))
    edges = []
    for i, (rid, url, body, length, phrases, characters) in enumerate(prepared):
        for oid, other_url, other_body, other_length, other_phrases, other_chars in prepared[:i]:
            reason, score = None, None
            if url and url == other_url:
                reason = 'same_source_url'
            elif length and body == other_body:
                reason = 'same_normalized_text'
            elif min(length, other_length) >= 60:
                denominator = min(len(phrases), len(other_phrases))
                score = len(phrases & other_phrases) / denominator if denominator else 0
                if score >= threshold:
                    reason = 'long_text_containment_candidate'
                else:
                    # Saved HTML can lose spaces between words. A second,
                    # stricter character comparison catches that extraction
                    # variation; it remains a grouping proposal, not equality.
                    denominator = min(len(characters), len(other_chars))
                    char_score = len(characters & other_chars) / denominator if denominator else 0
                    if char_score >= .95:
                        reason, score = 'long_character_containment_candidate', char_score
            if reason:
                union(rid, oid)
                edges.append({'left': rid, 'right': oid, 'reason': reason, 'similarity': score,
                              'review_status': 'candidate_not_human_verified'})
    return {rid: 'AG-' + digest(find(rid))[:16] for rid in ids}, edges


def assign_splits(group_ids: set[str], *, seen_groups: set[str], seed: str) -> dict[str, str]:
    """Known exposures always remain development; unknown exposure is blocked."""
    return {group: 'development' if group in seen_groups else
            ('holdout_candidate' if int(digest(seed + group)[:8], 16) % 5 == 0 else 'development_candidate')
            for group in group_ids}


def assert_split_integrity(cases: list[dict]) -> None:
    """Entity substitutions and article relatives cannot cross dev/test."""
    partitions: dict[tuple[str, str], set[str]] = {}
    for case in cases:
        for key in ('template_family_id', 'article_group_id'):
            value = case.get(key)
            if value:
                partitions.setdefault((key, value), set()).add(case['split'])
    leakage = [(key, value) for (key, value), splits in partitions.items() if len(splits) > 1]
    if leakage:
        raise ValueError(f'split leakage: {leakage}')
    for case in cases:
        if case['split'] == 'holdout' and (case.get('previously_exposed') is not False
                                           or case.get('human_gold_approved') is not True):
            raise ValueError('holdout needs explicit unseen declaration and approved gold')


def reviewed_membership_score(reference: dict[str, str], returned: set[str], *,
                              independent_review_complete: bool) -> dict:
    """Draft/unknown membership cannot produce a definitive accuracy score."""
    if set(reference.values()) - {'positive', 'negative', 'unknown', 'not_reviewed'}:
        raise ValueError('invalid reference membership state')
    if returned - reference.keys():
        raise ValueError('returned records outside frozen scope')
    if not independent_review_complete or any(v in {'unknown', 'not_reviewed'} for v in reference.values()):
        return {'status': 'awaiting_independent_full_review', 'precision': None, 'recall': None,
                'reviewed_pairs': sum(v in {'positive', 'negative'} for v in reference.values()),
                'planned_pairs': len(reference)}
    relevant = {rid for rid, state in reference.items() if state == 'positive'}
    tp, fp, fn = len(returned & relevant), len(returned - relevant), len(relevant - returned)
    return {'status': 'scored_frozen_scope', 'tp': tp, 'fp': fp, 'fn': fn,
            'precision': tp / (tp + fp) if tp + fp else None,
            'recall': tp / (tp + fn) if tp + fn else None,
            'scope_count': len(reference)}


def prepare(snapshot: Path, questions: Path, out: Path) -> dict:
    if out.exists() and any(out.iterdir()):
        raise ValueError('output must be new or empty; preserve prior evaluation preparations')
    raw = json.loads(snapshot.read_text(encoding='utf-8'))
    records = [r for r in raw['records'] if r['active'] and r['dataset'] == 'native' and r['payload']['countable']]
    content = [{'record_id':r['record_id'],'url':r['payload']['url'],'body':r['body']} for r in records]
    groups, edges = article_groups(content)
    # The current collection has been used throughout development. No unseen
    # claim is inferred from hashing, randomization or unfinished human review.
    splits = assign_splits(set(groups.values()), seen_groups=set(groups.values()), seed='20261006-v1')
    definitions = json.loads(questions.read_text(encoding='utf-8'))['questions']
    baseline = [{'question_id':q['question_id'],'question_exact':q['question_exact'],
                 'role':'seen_regression_baseline','previously_exposed':True} for q in definitions]
    templates = [
        ('mentions_concept', 'Which advertisements mention {concept}?', ['blue hydrogen','carbon capture and storage','recycling']),
        ('frames_concept', 'Which advertisements present {concept} as {attribute}?', ['blue hydrogen|a low-carbon fuel','carbon capture and storage|essential for emission reduction','recycling|reducing emissions']),
        ('attributes_sponsor', 'How does {sponsor} describe reducing its own emissions? Cite the advertisements and distinguish plans from achieved results.', ['ExxonMobil','PETRONAS','Shell']),
        ('comparison_sponsor', 'How do {sponsor_a} and {sponsor_b} describe their environmental efforts? Cite evidence for each.', ['ExxonMobil|Shell','PETRONAS|TotalEnergies','Shell|bp']),
        ('actor_responsibility', 'Which advertisements describe {actor} as responsible for environmental action?', ['individual consumers','governments','companies']),
        ('policy_recommendation', 'Which advertisements recommend {policy}? Distinguish proposed from already adopted policy.', ['a carbon price','CCS tax credits','permit reform']),
    ]
    variants = []
    for family, template, entities in templates:
        for index, entity in enumerate(entities):
            pieces = entity.split('|')
            slots = ({'concept':pieces[0],'attribute':pieces[-1]} if family == 'frames_concept' else
                     {'sponsor_a':pieces[0],'sponsor_b':pieces[-1]} if family == 'comparison_sponsor' else
                     {'sponsor':entity,'concept':entity,'actor':entity,'policy':entity})
            variants.append({'case_id':f'{family}-{index+1}','template_family_id':family,
                             'question':template.format(**slots),'split':'development',
                             'previously_exposed':True,'human_gold_approved':False,
                             'purpose':'entity_substitution_regression_not_unseen_test'})
    assert_split_integrity(variants)
    out.mkdir(parents=True, exist_ok=True)
    inputs = {'snapshot_sha256':hashlib.sha256(snapshot.read_bytes()).hexdigest(),
              'questions_sha256':hashlib.sha256(questions.read_bytes()).hexdigest()}
    result = {'schema_version':'content-generalization-preparation-v1', 'status':'draft_not_performance',
              **inputs,'seed':'20261006-v1','scope_count':len(records),'article_group_count':len(set(groups.values())),
              'groups': [{'record_id':rid,'article_group_id':group,'split':splits[group],
                          'exposure':'current_collection_development_used'} for rid,group in sorted(groups.items())],
              'grouping_edges':edges,'baseline':baseline,'development_variants':variants,
              'independent_test_cases':[],'independent_test_status':'needs_new_articles_and_independent_gold',
              'gold_created':False,'model_calls':0,'performance_score':None}
    (out/'preparation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({**inputs,'scope_count':len(records),'groups':len(set(groups.values())),
                      'variants':len(variants),'independent_test_cases':0,'performance_score':None}))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot',type=Path,required=True)
    parser.add_argument('--questions',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args = parser.parse_args()
    prepare(args.snapshot,args.questions,args.out)


if __name__ == '__main__':
    main()

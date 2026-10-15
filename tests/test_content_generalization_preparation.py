"""Behavioral checks: grouping, leakage, unknowns and incomplete evaluation."""
import importlib.util
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    'prepare_content_generalization', Path(__file__).parents[1] / 'scripts/prepare_content_generalization.py')
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def test_tracking_parameters_do_not_change_group_but_content_params_do():
    assert module.canonical_url('https://a.example/item?utm_source=x&id=2#anchor') == 'https://a.example/item?id=2'
    assert module.canonical_url('https://a.example/item?id=2') != module.canonical_url('https://a.example/item?id=3')


def test_long_shared_copy_is_one_group_without_merging_distinct_short_navigation():
    body = ' '.join(f'word{i}' for i in range(100))
    groups, _ = module.article_groups([
        {'record_id':'a','url':'https://a.example/a','body':body},
        {'record_id':'b','url':'https://b.example/b','body':'Header '+body+' Footer'},
        {'record_id':'c','url':'https://c.example/c','body':'Menu About Contact'},
        {'record_id':'d','url':'https://d.example/d','body':'Menu About News Contact'},
    ])
    assert groups['a'] == groups['b']
    assert groups['c'] != groups['d']


def test_empty_documents_do_not_become_exact_copies():
    groups, _ = module.article_groups([
        {'record_id':'a','url':'https://a.example/a','body':''},
        {'record_id':'b','url':'https://b.example/b','body':''},
    ])
    assert groups['a'] != groups['b']


def test_saved_page_spacing_loss_does_not_leak_same_article():
    tokens = [f'differenttoken{i}' for i in range(120)]
    body = ' '.join(tokens)
    damaged = ' '.join(tokens[i] + tokens[i+1] for i in range(0,120,2))
    groups, edges = module.article_groups([
        {'record_id':'a','url':'https://a.example/a','body':body},
        {'record_id':'b','url':'https://b.example/b','body':damaged},
    ])
    assert groups['a'] == groups['b']
    assert edges[0]['reason'] == 'long_character_containment_candidate'


def test_known_exposures_cannot_enter_holdout_by_random_seed():
    assert set(module.assign_splits({'a','b'},seen_groups={'a','b'},seed='any').values()) == {'development'}


@pytest.mark.parametrize('shared_key', ['template_family_id','article_group_id'])
def test_swapping_company_or_article_does_not_avoid_family_leakage(shared_key):
    cases = [{'split':'development',shared_key:'same'}, {'split':'holdout_candidate',shared_key:'same'}]
    with pytest.raises(ValueError,match='split leakage'):
        module.assert_split_integrity(cases)


@pytest.mark.parametrize('gold,seen', [(False,False),(True,True),(True,None)])
def test_independent_test_requires_both_approved_gold_and_unseen_declaration(gold,seen):
    with pytest.raises(ValueError,match='holdout needs'):
        module.assert_split_integrity([{'split':'holdout','human_gold_approved':gold,'previously_exposed':seen}])


def test_unknown_sources_cannot_be_scored_as_negatives():
    result = module.reviewed_membership_score({'a':'positive','b':'unknown'},{'a'},independent_review_complete=True)
    assert result['precision'] is None and result['recall'] is None
    assert result['reviewed_pairs'] == 1


def test_unreviewed_ai_reference_cannot_publish_score():
    assert module.reviewed_membership_score({'a':'positive'},{'a'},independent_review_complete=False)['precision'] is None


def test_empty_answer_keeps_missed_positive_in_recall():
    result = module.reviewed_membership_score({'a':'positive','b':'negative'},set(),independent_review_complete=True)
    assert result['precision'] is None and result['recall'] == 0 and result['fn'] == 1


def test_complete_membership_uses_distinct_records_and_rejects_out_of_scope():
    result = module.reviewed_membership_score({'a':'positive','b':'negative'},{'a','b'},independent_review_complete=True)
    assert result['precision'] == .5 and result['recall'] == 1
    with pytest.raises(ValueError,match='outside frozen scope'):
        module.reviewed_membership_score({'a':'positive'},{'outside'},independent_review_complete=True)

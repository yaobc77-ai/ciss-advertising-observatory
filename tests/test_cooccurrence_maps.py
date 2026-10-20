"""Knowledge-map arithmetic and rules on fictional incidence matrices."""
import pytest

from observatory.cooccurrence_maps import (
    jaccard,
    lift,
    pair_counts,
    project,
    select_edges,
    semantic_projection,
)


def test_jaccard_is_co_occurrence_over_the_union():
    assert jaccard(6, 10, 8) == pytest.approx(0.5)  # 6 / (10 + 8 - 6)


def test_a_high_jaccard_can_still_be_below_chance():
    # Both tags are in 80 of 100 posts and together in 60: J = 0.6, lift = 60*100/(80*80) ~ 0.94.
    assert jaccard(60, 80, 80) == pytest.approx(0.6)
    assert lift(60, 80, 80, 100) == pytest.approx(0.9375)


def units_from(pairs):
    return {f"u{n}": set(entities) for n, entities in enumerate(pairs)}


def test_minimum_co_occurrence_drops_single_shared_units():
    units = units_from([("#kites", "#harbor"), ("#kites", "#harbor"), ("#kites", "#gale")])
    occurs, together = pair_counts(units)
    candidates, kept = select_edges(occurs, together, len(units), min_co=2, top_k=8)
    assert [(e["source"], e["target"], e["co"]) for e in candidates] == [("#harbor", "#kites", 2)]
    assert kept == candidates


def test_an_edge_is_kept_when_either_end_ranks_it_in_its_top_k():
    # #hub links to four tags; with top_k=1 it keeps only its strongest, but each
    # leaf keeps its only edge, so all four edges stay.
    pairs = [("#hub", f"#leaf{n}") for n in range(4) for _ in range(2 + n)] + [("#hub",)] * 3
    units = units_from(pairs)
    occurs, together = pair_counts(units)
    _, kept = select_edges(occurs, together, len(units), min_co=2, top_k=1)
    assert len(kept) == 4
    # Two hubs sharing weak leaves: an edge neither end ranks first is dropped.
    units = units_from([("#a", "#b")] * 5 + [("#a", "#c")] * 2 + [("#c", "#b")] * 2 + [("#c", "#d")] * 6)
    occurs, together = pair_counts(units)
    _, kept = select_edges(occurs, together, len(units), min_co=2, top_k=1)
    assert {(e["source"], e["target"]) for e in kept} == {("#a", "#b"), ("#c", "#d")}


def test_communities_and_coordinates_are_reproducible_with_the_seed():
    units = units_from([("#a", "#b")] * 4 + [("#b", "#c")] * 4 + [("#x", "#y")] * 4 + [("#y", "#z")] * 4)
    first = project(units, view="hashtags", unit_kind="post", node_kind="hashtag", edge_meaning="same post")
    again = project(units, view="hashtags", unit_kind="post", node_kind="hashtag", edge_meaning="same post")
    assert first == again
    by_id = {node["id"]: node for node in first["nodes"]}
    assert by_id["#a"]["community_id"] == by_id["#c"]["community_id"] != by_id["#x"]["community_id"]
    assert all(node["topic_id"] is None for node in first["nodes"])  # topic stays separate from community


def test_every_edge_keeps_its_evidence_units_and_the_counts_add_up():
    units = units_from([("#kites", "#harbor")] * 3 + [("#kites",)] * 2)
    result = project(units, view="hashtags", unit_kind="post", node_kind="hashtag", edge_meaning="same post",
                     unit_refs={f"u{n}": f"/records/post-{n}" for n in range(5)})
    edge = result["edges"][0]
    assert (edge["co"], edge["n_a"], edge["n_b"]) == (3, 3, 5)
    assert edge["units"] == ["u0", "u1", "u2"] and edge["unit_refs"] == ["/records/post-0", "/records/post-1", "/records/post-2"]
    assert result["counts"] == {"corpus_units": 5, "candidate_nodes": 2, "final_nodes": 2,
                                "candidate_edges": 1, "kept_edges": 1}
    assert result["params"]["min_co"] == 2 and result["params"]["top_k"] == 8


def test_the_semantic_projection_is_reproducible_and_labelled_as_names_not_co_occurrence():
    items = [{"id": f"t{n}", "label": f"tag {n}", "kind": "hashtag"} for n in range(4)]
    vectors = [[1, 0, 0], [0.9, 0.1, 0], [0, 1, 0], [0, 0.9, 0.1]]
    first, again = semantic_projection(items, vectors), semantic_projection(items, vectors)
    assert first == again and first["label"] == "名称语义相近，不是共同出现"
    assert first["nodes"][0]["neighbours"][0]["id"] == "t1"


def test_the_panel_reads_the_latest_build_and_explains_an_edge(tmp_path):
    from observatory.cooccurrence_ui import detail_for, figure_for, latest_maps, summary_for

    units = units_from([("#kites", "#harbor")] * 3 + [("#kites",)] * 2)
    view = project(units, view="hashtags", unit_kind="X post", node_kind="hashtag", edge_meaning="same post",
                   unit_refs={f"u{n}": f"/records/post-{n}" for n in range(5)})
    (tmp_path / "abc").mkdir()
    (tmp_path / "abc" / "knowledge_maps.json").write_text(
        __import__("json").dumps({"data_version": "f" * 64, "views": {"hashtags": view}, "semantic": None}))
    maps = latest_maps(tmp_path)
    assert maps["views"]["hashtags"]["counts"]["kept_edges"] == 1
    assert len(figure_for(view, "community_id").data) == 3
    assert "kept edges 1" in str(summary_for(maps, view))
    text = str(detail_for(view, ["edge", 0]))
    assert "3 / (3 + 5 − 3) = 0.600" in text and "/records/post-0" in text
    assert detail_for(view, ["edge", 9]) == "Click an edge midpoint or a node for details."

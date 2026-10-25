"""Knowledge maps: one evidence matrix projected into several co-occurrence maps.

An incidence matrix says which entities (hashtags, handles, labels, companies)
occur in which evidence units (posts, ads). Every pair of entities gets its
co-occurrence count, both occurrence counts, Jaccard similarity and lift. Edges
pass a minimum co-occurrence and are kept when either end ranks them among its
top-k by Jaccard. Louvain communities use Jaccard weights; ForceAtlas2
coordinates are computed at build time. Community, topic and coordinates are
separate fields, and every parameter is written into the output.

A co-occurrence is a fact about recorded fields, not a finding about meaning;
the semantic map is a separate projection of name embeddings.
"""
from __future__ import annotations

from collections import defaultdict
from itertools import combinations

import networkx as nx
import numpy as np

SCHEMA_VERSION = "knowledge-maps-v1"
DEFAULTS = {"min_co": 2, "top_k": 8, "seed": 20261020, "resolution": 1.0, "layout_iterations": 300}


def jaccard(co, n_a, n_b):
    """Share of the units holding either entity that hold both."""
    union = n_a + n_b - co
    return co / union if union else 0.0


def lift(co, n_a, n_b, n_units):
    """Co-occurrence relative to independence: below 1 is rarer than chance."""
    return co * n_units / (n_a * n_b) if n_a and n_b else 0.0


def pair_counts(units):
    """Occurrence counts per entity and the units behind each co-occurring pair.

    ``units`` maps a unit ID to the entities it contains.
    """
    occurs = defaultdict(int)
    together = defaultdict(list)
    for unit_id in sorted(units):
        entities = sorted(set(units[unit_id]))
        for entity in entities:
            occurs[entity] += 1
        for a, b in combinations(entities, 2):
            together[(a, b)].append(unit_id)
    return dict(occurs), dict(together)


def select_edges(occurs, together, n_units, *, min_co, top_k):
    """Candidate edges (co >= min_co) and the kept ones (in either end's top-k by Jaccard)."""
    candidates = []
    for (a, b), unit_ids in together.items():
        co = len(unit_ids)
        if co < min_co:
            continue
        candidates.append({"source": a, "target": b, "co": co, "n_a": occurs[a], "n_b": occurs[b],
                           "jaccard": round(jaccard(co, occurs[a], occurs[b]), 6),
                           "lift": round(lift(co, occurs[a], occurs[b], n_units), 6), "units": unit_ids})
    by_node = defaultdict(list)
    for index, edge in enumerate(candidates):
        by_node[edge["source"]].append(index)
        by_node[edge["target"]].append(index)
    kept = set()
    for node, indexes in by_node.items():
        # Highest Jaccard first; ties go to the larger co-occurrence, then the name.
        ranked = sorted(indexes, key=lambda i: (-candidates[i]["jaccard"], -candidates[i]["co"],
                                                candidates[i]["source"], candidates[i]["target"]))
        kept.update(ranked[:top_k])
    return candidates, [candidates[i] for i in sorted(kept, key=lambda i: (candidates[i]["source"], candidates[i]["target"]))]


def communities_and_layout(nodes, edges, *, seed, resolution, iterations):
    """Louvain communities (Jaccard weights) and ForceAtlas2 coordinates, both seeded."""
    graph = nx.Graph()
    graph.add_nodes_from(sorted(nodes))
    for edge in edges:
        graph.add_edge(edge["source"], edge["target"], weight=edge["jaccard"])
    groups = nx.community.louvain_communities(graph, weight="weight", resolution=resolution, seed=seed)
    # Stable numbering: larger communities first, then by their first member.
    ordered = sorted((sorted(group) for group in groups), key=lambda group: (-len(group), group[0]))
    community = {node: index for index, group in enumerate(ordered) for node in group}
    positions = nx.forceatlas2_layout(graph, max_iter=iterations, seed=seed, weight="weight") if len(graph) else {}
    xy = {node: (round(float(point[0]), 4), round(float(point[1]), 4)) for node, point in positions.items()}
    return community, xy


def project(units, *, view, unit_kind, node_kind, edge_meaning, labels=None, topics=None, unit_refs=None,
            params=None, notes=()):
    """One projected map: counts, nodes with community/topic/coordinates, edges with evidence."""
    params = {**DEFAULTS, **(params or {})}
    occurs, together = pair_counts(units)
    candidate_nodes = sorted(entity for entity, n in occurs.items() if n >= params["min_co"])
    candidates, kept = select_edges(occurs, together, len(units), min_co=params["min_co"], top_k=params["top_k"])
    nodes = sorted({edge["source"] for edge in kept} | {edge["target"] for edge in kept})
    community, xy = communities_and_layout(nodes, kept, seed=params["seed"], resolution=params["resolution"],
                                           iterations=params["layout_iterations"])
    labels, topics, unit_refs = labels or {}, topics or {}, unit_refs or {}
    return {
        "schema_version": SCHEMA_VERSION, "view": view, "unit_kind": unit_kind, "node_kind": node_kind,
        "edge_meaning": edge_meaning, "params": params, "notes": list(notes),
        "counts": {"corpus_units": len(units), "candidate_nodes": len(candidate_nodes), "final_nodes": len(nodes),
                   "candidate_edges": len(candidates), "kept_edges": len(kept)},
        "nodes": [{"id": node, "label": labels.get(node, node), "n": occurs[node],
                   "community_id": community.get(node), "topic_id": topics.get(node),
                   "x": xy.get(node, (0.0, 0.0))[0], "y": xy.get(node, (0.0, 0.0))[1]} for node in nodes],
        "edges": [{**edge, "unit_refs": [unit_refs.get(unit, unit) for unit in edge["units"]]} if unit_refs else edge
                  for edge in kept],
    }


def semantic_projection(items, vectors, *, neighbours=5, label="Similar names (not co-occurrence)"):
    """PCA of name embeddings to 2-D with each item's nearest names by cosine.

    ``items`` are dicts with at least id/label/kind, in the same order as ``vectors``.
    """
    matrix = np.asarray(vectors, dtype=float)
    centred = matrix - matrix.mean(axis=0)
    _, _, components = np.linalg.svd(centred, full_matrices=False)
    # A component's sign is arbitrary: fix it so the largest loading is positive.
    signs = np.sign(components[:2][np.arange(2), np.abs(components[:2]).argmax(axis=1)])
    coords = centred @ (components[:2].T * signs)
    unit = matrix / np.linalg.norm(matrix, axis=1, keepdims=True)
    cosine = unit @ unit.T
    np.fill_diagonal(cosine, -np.inf)
    nodes = []
    for index, item in enumerate(items):
        order = np.argsort(-cosine[index], kind="stable")[:neighbours]
        nodes.append({**item, "x": round(float(coords[index, 0]), 4), "y": round(float(coords[index, 1]), 4),
                      "neighbours": [{"id": items[j]["id"], "cosine": round(float(cosine[index, j]), 4)} for j in order]})
    return {"schema_version": SCHEMA_VERSION, "view": "semantic", "label": label,
            "method": "PCA via numpy SVD of name embeddings; top cosine neighbours", "nodes": nodes,
            "counts": {"items": len(items)}}

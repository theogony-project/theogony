"""Tests for Jaccard cluster identity mapping."""

from __future__ import annotations

from theogony.clustering.identity import map_cluster_identity
from theogony.core.model import ClusterSummary, KnowledgeNode, NodeType, SourceRef


def _node(nid: str) -> KnowledgeNode:
    return KnowledgeNode(
        id=nid,
        label=nid,
        source_ref=SourceRef(source_type="test", identifier="1"),
        node_type=NodeType.CONCEPT,
    )


def test_map_identity_inherits_when_jaccard_above_threshold() -> None:
    prev = ClusterSummary(
        cluster_id="c-old",
        cluster_label="sem",
        member_count=10,
        centroid=[1.0, 0.0],
        dominant_node_type=NodeType.CONCEPT,
        dominant_source_type="t",
    )
    members = {f"n{i}" for i in range(10)}
    new_assign = {nid: 0 for nid in members}
    centroids = {0: [1.0, 0.0]}
    nodes = {nid: _node(nid) for nid in members}
    r = map_cluster_identity(
        new_assignments=new_assign,
        new_centroids=centroids,
        previous_summaries=[prev],
        previous_members={"c-old": members},
        jaccard_threshold=0.7,
        nodes_by_id=nodes,
    )
    assert r.inherited_count == 1
    assert all(r.assignments[nid] == "c-old" for nid in members)


def test_map_identity_mints_when_jaccard_below_threshold() -> None:
    prev_members = {f"n{i}" for i in range(10)}
    new_members = {f"n{i}" for i in range(10, 20)}
    new_assign = {nid: 0 for nid in new_members}
    centroids = {0: [1.0, 0.0]}
    prev = ClusterSummary(
        cluster_id="c-old",
        cluster_label=None,
        member_count=10,
        centroid=[1.0, 0.0],
        dominant_node_type=None,
        dominant_source_type=None,
    )
    nodes = {nid: _node(nid) for nid in new_members}
    r = map_cluster_identity(
        new_assignments=new_assign,
        new_centroids=centroids,
        previous_summaries=[prev],
        previous_members={"c-old": prev_members},
        jaccard_threshold=0.7,
        nodes_by_id=nodes,
    )
    assert r.minted_count == 1
    assert r.assignments[next(iter(new_members))].startswith("cluster-")


def test_map_identity_one_to_one_matching() -> None:
    """Only one new cluster can inherit a given previous id (greedy one-to-one)."""
    prev_set = {f"p{i}" for i in range(10)}
    big = set(prev_set)  # perfect overlap → inherits
    small = {f"p{i}" for i in range(3)} | {f"s{i}" for i in range(7)}  # 3/17 overlap < 0.2
    new_assign: dict[str, int] = {}
    for nid in big:
        new_assign[nid] = 0
    for nid in small:
        new_assign[nid] = 1
    centroids = {0: [1.0, 0.0], 1: [0.0, 1.0]}
    prev = ClusterSummary(
        cluster_id="old",
        cluster_label=None,
        member_count=10,
        centroid=[1.0, 0.0],
        dominant_node_type=None,
        dominant_source_type=None,
    )
    nodes = {nid: _node(nid) for nid in big | small}
    r = map_cluster_identity(
        new_assignments=new_assign,
        new_centroids=centroids,
        previous_summaries=[prev],
        previous_members={"old": prev_set},
        jaccard_threshold=0.2,
        nodes_by_id=nodes,
    )
    inherited = sum(1 for s in r.summaries if s.cluster_id == "old")
    assert inherited == 1


def test_map_identity_handles_noise_points() -> None:
    new_assign = {"a": 0, "noise": -1}
    centroids = {0: [1.0, 0.0]}
    nodes = {"a": _node("a"), "noise": _node("noise")}
    r = map_cluster_identity(
        new_assignments=new_assign,
        new_centroids=centroids,
        previous_summaries=[],
        previous_members={},
        jaccard_threshold=0.7,
        nodes_by_id=nodes,
    )
    assert r.assignments["noise"] is None
    assert r.noise_count == 1


def test_map_identity_preserves_label_on_inherit() -> None:
    members = {"x1", "x2", "x3", "x4", "x5"}
    new_assign = {nid: 0 for nid in members}
    prev = ClusterSummary(
        cluster_id="cid",
        cluster_label="code",
        member_count=5,
        centroid=[1.0, 0.0],
        dominant_node_type=None,
        dominant_source_type=None,
    )
    nodes = {nid: _node(nid) for nid in members}
    r = map_cluster_identity(
        new_assignments=new_assign,
        new_centroids={0: [1.0, 0.0]},
        previous_summaries=[prev],
        previous_members={"cid": members},
        jaccard_threshold=0.7,
        nodes_by_id=nodes,
    )
    assert r.summaries[0].cluster_label == "code"


def test_map_identity_tie_breaks_by_ascending_prev_id() -> None:
    new_members = {"n1", "n2", "n3", "n4", "n5"}
    new_assign = {nid: 0 for nid in new_members}
    centroids = {0: [1.0, 0.0]}
    prev_lo = ClusterSummary(
        cluster_id="a-prev",
        cluster_label=None,
        member_count=5,
        centroid=[1.0, 0.0],
        dominant_node_type=None,
        dominant_source_type=None,
    )
    prev_hi = ClusterSummary(
        cluster_id="z-prev",
        cluster_label=None,
        member_count=5,
        centroid=[1.0, 0.0],
        dominant_node_type=None,
        dominant_source_type=None,
    )
    same_overlap = {"n1", "n2", "n3"}
    nodes = {nid: _node(nid) for nid in new_members}
    r = map_cluster_identity(
        new_assignments=new_assign,
        new_centroids=centroids,
        previous_summaries=[prev_lo, prev_hi],
        previous_members={"a-prev": same_overlap, "z-prev": same_overlap},
        jaccard_threshold=0.3,
        nodes_by_id=nodes,
    )
    assert r.assignments["n1"] == "a-prev"

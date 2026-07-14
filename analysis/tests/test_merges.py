import textwrap

from merges import load_merges, apply_merges


def test_load_merges_reads_groups(tmp_path):
    p = tmp_path / "m.yaml"
    p.write_text(textwrap.dedent("""
        groups:
          - labels: ["A", "B"]
            reason: "same place"
          - labels: ["C", "D", "E"]
            reason: "also same place"
    """))
    assert load_merges(str(p)) == [["A", "B"], ["C", "D", "E"]]


def test_load_merges_missing_file_returns_empty(tmp_path):
    assert load_merges(str(tmp_path / "nope.yaml")) == []


def test_apply_merges_collapses_a_group_onto_its_first_label():
    ids = [0, 0, 1, 2, 3]
    labels = {0: "Church-Wellesley", 1: "Church and Wellesley",
              2: "Church-Wellesley Village", 3: "Parkdale"}
    groups = [["Church-Wellesley", "Church and Wellesley", "Church-Wellesley Village"]]

    new_ids, new_labels = apply_merges(ids, labels, groups)

    # the three church clusters now share ONE id...
    assert new_ids[0] == new_ids[1] == new_ids[2] == new_ids[3]
    # ...labelled with the group's first entry...
    assert new_labels[new_ids[0]] == "Church-Wellesley"
    # ...and Parkdale is untouched and still distinct.
    assert new_ids[4] != new_ids[0]
    assert new_labels[new_ids[4]] == "Parkdale"


def test_apply_merges_is_case_insensitive():
    ids = [0, 1]
    labels = {0: "Old town", 1: "old town toronto"}
    new_ids, new_labels = apply_merges(ids, labels, [["Old Town", "OLD TOWN TORONTO"]])
    assert new_ids[0] == new_ids[1]


def test_apply_merges_ignores_labels_that_match_no_cluster():
    # the snapshot changes over time; a stale entry must not crash the pipeline
    ids = [0]
    labels = {0: "Parkdale"}
    new_ids, new_labels = apply_merges(ids, labels, [["Parkdale", "A Name Nobody Used"]])
    assert new_labels[new_ids[0]] == "Parkdale"


def test_apply_merges_with_no_groups_is_identity():
    ids = [0, 1]
    labels = {0: "A", 1: "B"}
    assert apply_merges(ids, labels, []) == (ids, labels)


def test_apply_merges_tolerates_a_duplicated_label_in_one_group():
    # a copy-paste slip in the hand-edited merges.yaml must not crash the pipeline
    ids = [0, 1]
    labels = {0: "Parkdale", 1: "Other"}
    new_ids, new_labels = apply_merges(ids, labels, [["Parkdale", "Parkdale"]])
    assert set(new_ids) <= set(new_labels)          # no dangling ids
    assert new_labels[new_ids[0]] == "Parkdale"


def test_apply_merges_refuses_to_chain_across_groups():
    # merges.yaml is hand-edited. A label in two groups would fuse all three
    # clusters transitively -- the failure that once fused 130 neighbourhoods.
    # Fail loudly rather than silently chaining.
    import pytest
    ids = [0, 1, 2]
    labels = {0: "A", 1: "B", 2: "C"}
    with pytest.raises(ValueError, match="more than one group"):
        apply_merges(ids, labels, [["A", "B"], ["C", "A"]])


def test_apply_merges_never_leaves_an_id_without_a_label():
    # THE invariant build_clusters depends on: labels[cid] must never KeyError.
    ids = [0, 1, 2, 3]
    labels = {0: "A", 1: "B", 2: "C", 3: "D"}
    groups = [["A", "B"], ["C", "D"]]
    new_ids, new_labels = apply_merges(ids, labels, groups)
    for cid in new_ids:
        assert cid in new_labels

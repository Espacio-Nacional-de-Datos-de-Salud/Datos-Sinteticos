"""Preprocessing utilities for data and metadata transformation."""

import pandas as pd
from backend.src.core.logging_config import get_logger
from backend.src.core.preprocessing.logical_rules import ForeignKeysConsistencyRule

logger = get_logger(__name__)


def validate_referential_integrity(parent_col: pd.Series, child_col: pd.Series) -> tuple[int, int]:
    """Counts how many values in child_col are not present in parent_col (orphans).

    Example: if parent_col has values {1, 2, 3} and child_col has values [2, 2, 3, 4, NaN],
    then the function returns (1, 4) because there are 4 non-null values in child_col
    and 1 of them (the value 4) is not found in parent_col. Null values in child_col are ignored
    and do not contribute to the total count.

    Args:
        parent_col (pd.Series): PK column of the parent table.
        child_col (pd.Series): FK column of the child table.

    Returns:
        tuple[int, int]: ``(orphan_count, total)`` where ``total`` is the number
            of non-null values in ``child_col`` and ``orphan_count`` is how many
            of those are not found in ``parent_col``. Returns ``(0, 0)`` if
            ``child_col`` has no non-null values.
    """
    parent_vals = set(parent_col.dropna().unique())
    child_non_null = child_col.dropna()
    total = len(child_non_null)
    if total == 0:
        return 0, 0
    return int((~child_non_null.isin(parent_vals)).sum()), total


def group_fks_by_child(relationships: dict) -> dict[str, list[dict]]:
    """Group foreign keys by child table name.

    Args:
        relationships (dict): Structure with ``fks`` list.

    Returns:
        dict[str, list[dict]]: Mapping of child table name to its list of FK dicts.
    """
    grouped: dict[str, list[dict]] = {}
    for fk in relationships.get("fks", []):
        grouped.setdefault(fk["child"], []).append(fk)
    return grouped


def format_relationships(relationships: dict) -> dict:
    """Converts relationships to the format accepted by LogicalRuleManager.

    Transforms relationship structure from format {fks: [...]} into a dictionary
    optimized for fast lookups (child, parent) -> [(fk_column, pk_column), ...].

    Args:
        relationships (dict): Structure with detected FKs
            {fks: [{child, parent, fk_column, pk_column}, ...]}.

    Returns:
        dict: Formatted relationships {(child_table, parent_table): [(fk_col, pk_col), ...]}.

    Example:
        >>> rels_raw = {"fks": [{"child": "orders", "parent": "users", ...}]}
        >>> rels_fmt = format_relationships(rels_raw)
    """
    formatted_relationships = {}

    sorted_fks = sorted(
        relationships.get("fks", []),
        key=lambda x: x.get("is_context", False) or x.get("direct", False),
        reverse=True,
    )

    for rel in sorted_fks:
        # LogicalRuleManager relationships format: (child, parent) -> [(fk, pk), ...]
        key = (rel["child"], rel["parent"])
        val = (rel["fk_column"], rel["pk_column"])
        formatted_relationships.setdefault(key, []).append(val)
    return formatted_relationships


def assign_default_context_keys(relationships: dict) -> dict:
    """Marks the first FK of each child table as context key by default.

    If any FK in that table is already explicitly marked with ``is_context=True``,
    that selection is respected and any duplicate is cleaned.

    Args:
        relationships (dict): Structure with ``fks``.

    Returns:
        dict: The same structure, updated in-place.
    """
    fks_by_child = group_fks_by_child(relationships)  # references into relationships["fks"]

    for child_fks in fks_by_child.values():
        if not child_fks:
            continue

        explicit_context_idx = next(
            (index for index, fk in enumerate(child_fks) if fk.get("is_context")),
            None,
        )

        # Keep track of parents that are marked direct
        direct_parents = {fk["parent"] for fk in child_fks if fk.get("direct")}

        def get_covered(fk_index: int, fks_list: list = child_fks) -> set[int]:
            fk_a = fks_list[fk_index]
            covered = {fk_index}
            parent_a_fks = fks_by_child.get(fk_a["parent"], [])
            parent_a_targets = {p["parent"] for p in parent_a_fks}

            for j, fk_b in enumerate(fks_list):
                if fk_b["parent"] in parent_a_targets or fk_b["parent"] == fk_a["parent"]:
                    covered.add(j)
            return covered

        uncovered = set(range(len(child_fks)))

        if explicit_context_idx is not None:
            first_chosen_idx = explicit_context_idx
            direct_parents.add(child_fks[first_chosen_idx]["parent"])
            uncovered -= get_covered(explicit_context_idx)
        else:
            first_chosen_idx = None

        while uncovered:
            best_idx = None
            best_cover = set()

            for i in sorted(list(uncovered)):
                cov = get_covered(i) & uncovered
                is_self_ref = child_fks[i]["parent"] == child_fks[i]["child"]

                # Penalty logic for selecting the first context key (first_chosen_idx)
                # If we haven't picked a context key, heavily penalize self-references
                if best_idx is None:
                    best_idx = i
                    best_cover = cov
                else:
                    curr_best_is_self = (
                        child_fks[best_idx]["parent"] == child_fks[best_idx]["child"]
                    )

                    if len(cov) > len(best_cover):
                        if first_chosen_idx is None and is_self_ref and not curr_best_is_self:
                            # New option offers more coverage, but it's a self-ref. Keep the non-self-ref if this is the first choice.
                            pass
                        else:
                            best_idx = i
                            best_cover = cov
                    elif len(cov) == len(best_cover):
                        if first_chosen_idx is None and curr_best_is_self and not is_self_ref:
                            # Swap to the non-self-referencing option if coverage is exactly the same and we're picking the context key
                            best_idx = i
                            best_cover = cov

            if best_idx is None:
                # Fallback if no valid options were selected cleanly
                best_idx = min(uncovered)
                best_cover = get_covered(best_idx) & uncovered

            direct_parents.add(child_fks[best_idx]["parent"])
            if first_chosen_idx is None:
                first_chosen_idx = best_idx

            uncovered -= best_cover

        for index, fk in enumerate(child_fks):
            fk["is_context"] = index == first_chosen_idx
            fk["direct"] = fk["parent"] in direct_parents

            logger.debug(
                f"Set key for child {fk['child']} to "
                f"{fk['parent']}.{fk['fk_column']}: "
                f"is_context={fk['is_context']}, direct={fk['direct']}"
            )

    return relationships


def infer_foreign_keys_consistency_rules(
    relationships: dict,
) -> list[ForeignKeysConsistencyRule]:
    """Infers rules to reconstruct non-context FKs through the context parent.

    Args:
        relationships (dict): Detected relationships structure.

    Returns:
        list[ForeignKeysConsistencyRule]: List of inferred rules, sorted by context depth.
    """

    fks_by_child = group_fks_by_child(relationships)
    context_depths = _compute_context_depths(fks_by_child)
    inferred_rules: list[tuple[int, ForeignKeysConsistencyRule]] = []

    for child_name, child_fks in fks_by_child.items():
        anchors = [fk for fk in child_fks if fk.get("is_context") or fk.get("direct")]
        if not anchors:
            continue

        for child_fk in child_fks:
            if child_fk in anchors:
                continue

            source_fk = None
            current_parent_name = None

            queue = [anchor["parent"] for anchor in anchors]
            visited = set(queue)

            while queue:
                curr_p_name = queue.pop(0)
                curr_p_fks = fks_by_child.get(curr_p_name, [])

                source_fk = _select_parent_source_fk(curr_p_fks, child_fk)
                if source_fk is not None:
                    current_parent_name = curr_p_name
                    break

                p_anchors = [fk for fk in curr_p_fks if fk.get("is_context") or fk.get("direct")]
                for p_anchor in p_anchors:
                    if p_anchor["parent"] not in visited:
                        visited.add(p_anchor["parent"])
                        queue.append(p_anchor["parent"])

            if source_fk is None or current_parent_name == child_name:
                continue
            logger.debug(
                f"Infer rule for child {child_name} FK {child_fk['fk_column']} \
                through parent {current_parent_name} FK {source_fk['fk_column']} \
                (context depth: {context_depths.get(child_name, 0)})"
            )
            inferred_rules.append(
                (
                    context_depths.get(child_name, 0),
                    ForeignKeysConsistencyRule(
                        table_origin=current_parent_name,
                        table_target=child_name,
                        target_col=child_fk["fk_column"],
                        source_col=source_fk["fk_column"],
                        referenced_table=child_fk["parent"],
                    ),
                )
            )

    inferred_rules.sort(key=lambda item: item[0], reverse=True)
    return [rule for _, rule in inferred_rules]


def _compute_context_depths(fks_by_child: dict[str, list[dict]]) -> dict[str, int]:
    """Computes the topological depth of each table in the context tree.

    Args:
        fks_by_child (dict[str, list[dict]]): FKs grouped by child table.

    Returns:
        dict[str, int]: Mapping of table names to their context depth.
    """
    memo: dict[str, int] = {}
    visiting: set[str] = set()

    def resolve_depth(table_name: str) -> int:
        if table_name in memo:
            return memo[table_name]
        if table_name in visiting:
            return 0

        visiting.add(table_name)
        anchors = [
            fk
            for fk in fks_by_child.get(table_name, [])
            if fk.get("is_context") or fk.get("direct")
        ]

        if not anchors:
            depth = 0
        else:
            depth = 1 + max(resolve_depth(anchor["parent"]) for anchor in anchors)

        visiting.remove(table_name)
        memo[table_name] = depth
        return depth

    for table_name in fks_by_child:
        resolve_depth(table_name)

    return memo


def _select_parent_source_fk(parent_fks: list[dict], child_fk: dict) -> dict | None:
    """Selects which parent FK matches the child FK to enable propagation.

    Args:
        parent_fks (list[dict]): List of FKs in the parent table.
        child_fk (dict): The child FK we want to propagate.

    Returns:
        dict | None: The matching parent FK dict, or None if no match is found.
    """
    exact_matches = [
        fk
        for fk in parent_fks
        if fk["parent"] == child_fk["parent"] and fk["fk_column"] == child_fk["fk_column"]
    ]
    if len(exact_matches) == 1:
        return exact_matches[0]

    table_matches = [fk for fk in parent_fks if fk["parent"] == child_fk["parent"]]
    if len(table_matches) == 1:
        return table_matches[0]

    return None

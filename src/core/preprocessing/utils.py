"""Preprocessing utilities for data and metadata transformation."""

from src.core.preprocessing.logical_rules import ForeignKeysConsistencyRule


def group_fks_by_child(relationships: dict) -> dict[str, list[dict]]:
    """Group foreign keys by child table name.

    Args:
        relationships: Structure with ``fks`` list.

    Returns:
        Mapping of child table name to its list of FK dicts.
    """
    grouped: dict[str, list[dict]] = {}
    for fk in relationships.get("fks", []):
        grouped.setdefault(fk["child"], []).append(fk)
    return grouped


def format_relationships(relationships: dict) -> dict:
    """Converts relationships to the format accepted by LogicalRuleManager.

    Transforms relationship structure from format {fks: [...]} into a dictionary
    optimized for fast lookups (child, parent) -> (fk_column, pk_column).

    Args:
        relationships (dict): Structure with detected FKs
            {fks: [{child, parent, fk_column, pk_column}, ...]}.

    Returns:
        dict: Formatted relationships {(child_table, parent_table): (fk_col, pk_col)}.

    Example:
        >>> rels_raw = {"fks": [{"child": "orders", "parent": "users", ...}]}
        >>> rels_fmt = format_relationships(rels_raw)
    """
    formatted_relationships = {}
    for rel in relationships["fks"]:
        # LogicalRuleManager relationships format: (child, parent) -> (fk, pk)
        key = (rel["child"], rel["parent"])
        val = (rel["fk_column"], rel["pk_column"])
        formatted_relationships[key] = val
    return formatted_relationships


def assign_default_context_keys(relationships: dict) -> dict:
    """Marks the first FK of each child table as context key by default.

    If any FK in that table is already explicitly marked with ``is_context=True``,
    that selection is respected and any duplicate is cleaned.

    Args:
        relationships (dict): Estructura con ``fks``.

    Returns:
        dict: La misma estructura, actualizada in-place.
    """
    fks_by_child = group_fks_by_child(relationships)  # references into relationships["fks"]

    for child_fks in fks_by_child.values():
        selected_index = next(
            (index for index, fk in enumerate(child_fks) if fk.get("is_context")),
            0,
        )
        for index, fk in enumerate(child_fks):
            fk["is_context"] = index == selected_index

    return relationships


def infer_foreign_keys_consistency_rules(
    relationships: dict,
) -> list[ForeignKeysConsistencyRule]:
    """Infers rules to reconstruct non-context FKs through the context parent."""

    fks_by_child = group_fks_by_child(relationships)
    context_depths = _compute_context_depths(fks_by_child)
    inferred_rules: list[tuple[int, ForeignKeysConsistencyRule]] = []

    for child_name, child_fks in fks_by_child.items():
        context_fk = next((fk for fk in child_fks if fk.get("is_context")), None)
        if context_fk is None:
            continue

        parent_name = context_fk["parent"]
        parent_fks = fks_by_child.get(parent_name, [])

        for child_fk in child_fks:
            if child_fk is context_fk:
                continue

            source_fk = _select_parent_source_fk(parent_fks, child_fk)
            if source_fk is None:
                continue

            inferred_rules.append(
                (
                    context_depths.get(child_name, 0),
                    ForeignKeysConsistencyRule(
                        table_origin=parent_name,
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
    memo: dict[str, int] = {}
    visiting: set[str] = set()

    def resolve_depth(table_name: str) -> int:
        if table_name in memo:
            return memo[table_name]
        if table_name in visiting:
            return 0

        visiting.add(table_name)
        context_fk = next(
            (fk for fk in fks_by_child.get(table_name, []) if fk.get("is_context")),
            None,
        )

        if context_fk is None:
            depth = 0
        else:
            depth = 1 + resolve_depth(context_fk["parent"])

        visiting.remove(table_name)
        memo[table_name] = depth
        return depth

    for table_name in fks_by_child:
        resolve_depth(table_name)

    return memo


def _select_parent_source_fk(parent_fks: list[dict], child_fk: dict) -> dict | None:
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

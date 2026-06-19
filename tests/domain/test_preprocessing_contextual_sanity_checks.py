import pandas as pd
from backend.src.domain.preprocessing_contextual_sanity_checks import (
    _build_table_name_to_pks_mapping,
    _build_table_definition,
    _deduplicate_definitions,
    _collect_all_fks_to_check,
    _select_parent_consistency_fk,
    _collect_all_contextual_relationships_to_check,
    _build_general_sanity_check_row,
    _get_referential_skip_reason,
    _evaluate_single_referential_integrity_check,
    _get_contextual_skip_reason,
    _evaluate_single_contextual_fk_check,
)
from backend.src.domain.preprocessing.logical_rules import (
    ForeignKeysConsistencyRule,
    LogicalRuleManager,
)

# -----------------------------------------------------------------------------
# Metadata Extraction Tests
# -----------------------------------------------------------------------------

def test_build_table_name_to_pks_mapping():
    metadata = {
        "tables": [
            {"name": "users", "primary_key": "id"},
            {"name": "logs"}, # no PK
            {"name": "orders", "primary_key": "order_id"},
        ]
    }
    mapping = _build_table_name_to_pks_mapping(metadata)
    assert mapping == {"users": "id", "orders": "order_id"}

def test_build_table_definition():
    metadata = {
        "tables": [
            {"name": "users", "primary_key": "id"},
            {"name": "orders", "primary_key": "order_id"},
        ]
    }
    defs = _build_table_definition(metadata)
    assert "users" in defs
    assert "orders" in defs
    assert defs["users"]["primary_key"] == "id"

def test_deduplicate_definitions():
    definitions = [
        {"a": 1, "b": 2, "c": 3},
        {"a": 1, "b": 2, "c": 4}, # duplicate based on a,b
        {"a": 2, "b": 2, "c": 3},
    ]
    deduped = _deduplicate_definitions(definitions, ("a", "b"))
    assert len(deduped) == 2
    assert deduped[0]["c"] == 3
    assert deduped[1]["a"] == 2

# -----------------------------------------------------------------------------
# Check Collection Tests
# -----------------------------------------------------------------------------

def test_collect_all_fks_to_check_metadata_only():
    metadata = {
        "tables": [
            {
                "name": "orders",
                "foreign_keys": [
                    {"column": "user_id", "referenced_table": "users"}
                ]
            }
        ]
    }
    checks = _collect_all_fks_to_check(metadata)
    assert len(checks) == 1
    assert checks[0] == {"child_table": "orders", "child_fk_column": "user_id", "parent_table": "users"}

def test_collect_all_fks_to_check_with_rules():
    metadata = {"tables": []}
    rule_manager = LogicalRuleManager(rules=[
        ForeignKeysConsistencyRule(table_origin="users", table_target="orders", source_col="id", target_col="user_id", referenced_table="users")
    ])
    checks = _collect_all_fks_to_check(metadata, rule_manager)
    assert len(checks) == 1
    assert checks[0] == {"child_table": "orders", "child_fk_column": "user_id", "parent_table": "users"}

def test_select_parent_consistency_fk():
    parent_fks = [
        {"column": "company_id", "referenced_table": "company"},
        {"column": "other_id", "referenced_table": "other"}
    ]
    child_fk = {"column": "company_id", "referenced_table": "company"}
    
    # Exact match
    res = _select_parent_consistency_fk(parent_fks, child_fk)
    assert res == parent_fks[0]
    
    # Table match only
    child_fk2 = {"column": "comp_id", "referenced_table": "company"}
    res2 = _select_parent_consistency_fk(parent_fks, child_fk2)
    assert res2 == parent_fks[0]
    
    # Ambiguity
    parent_fks_ambig = [
        {"column": "company_id1", "referenced_table": "company"},
        {"column": "company_id2", "referenced_table": "company"}
    ]
    res3 = _select_parent_consistency_fk(parent_fks_ambig, child_fk2)
    assert res3 is None

def test_collect_all_contextual_relationships_to_check():
    metadata = {
        "tables": [
            {
                "name": "company",
                "foreign_keys": []
            },
            {
                "name": "department",
                "foreign_keys": [
                    {"column": "company_id", "referenced_table": "company"}
                ]
            },
            {
                "name": "employee",
                "foreign_keys": [
                    {"column": "dept_id", "referenced_table": "department", "is_context": True},
                    {"column": "comp_id", "referenced_table": "company"}
                ]
            }
        ]
    }
    checks = _collect_all_contextual_relationships_to_check(metadata)
    assert len(checks) == 1
    assert checks[0] == {
        "child_table": "employee",
        "parent_table": "department",
        "context_fk_column": "dept_id",
        "child_fk_column": "comp_id",
        "parent_source_column": "company_id"
    }

# -----------------------------------------------------------------------------
# Evaluation Tests
# -----------------------------------------------------------------------------

def test_get_referential_skip_reason():
    data = {"child": pd.DataFrame({"fk": [1]}), "parent": pd.DataFrame({"id": [1]})}
    pks = {"parent": "id"}
    
    # Success
    assert _get_referential_skip_reason("child", "fk", "parent", data, pks) is None
    
    # Missing child table
    assert "Table 'missing' not found" in _get_referential_skip_reason("missing", "fk", "parent", data, pks)
    
    # Missing parent table
    assert "Parent table 'missing' not found" in _get_referential_skip_reason("child", "fk", "missing", data, pks)
    
    # Missing PK in metadata
    assert "PK for 'parent' not found" in _get_referential_skip_reason("child", "fk", "parent", data, {})
    
    # Missing child col
    assert "Child column 'bad_fk' not found" in _get_referential_skip_reason("child", "bad_fk", "parent", data, pks)
    
    # Missing parent PK col in data
    bad_data = {"child": pd.DataFrame({"fk": [1]}), "parent": pd.DataFrame({"bad": [1]})}
    assert "Parent PK column 'id' not found" in _get_referential_skip_reason("child", "fk", "parent", bad_data, pks)

def test_evaluate_single_referential_integrity_check():
    fk_check = {"child_table": "child", "child_fk_column": "fk", "parent_table": "parent"}
    pks = {"parent": "id"}
    
    # Pass
    data_pass = {"child": pd.DataFrame({"fk": [1, 2]}), "parent": pd.DataFrame({"id": [1, 2, 3]})}
    res = _evaluate_single_referential_integrity_check(fk_check, data_pass, pks)
    assert res["status"] == "PASS"
    assert res["failed_rows"] == 0
    assert res["total_rows"] == 2
    
    # Fail
    data_fail = {"child": pd.DataFrame({"fk": [1, 4]}), "parent": pd.DataFrame({"id": [1, 2, 3]})}
    res = _evaluate_single_referential_integrity_check(fk_check, data_fail, pks)
    assert res["status"] == "FAIL"
    assert res["failed_rows"] == 1
    assert res["total_rows"] == 2
    assert "examples: 4" in res["details"]
    
    # Skip
    data_skip = {"child": pd.DataFrame({"fk": [1]})}
    res = _evaluate_single_referential_integrity_check(fk_check, data_skip, pks)
    assert res["status"] == "SKIPPED"
    assert "Parent table 'parent' not found" in res["details"]

def test_get_contextual_skip_reason():
    data = {
        "child": pd.DataFrame({"ctx": [1], "fk": [2]}),
        "parent": pd.DataFrame({"id": [1], "src": [2]})
    }
    pks = {"parent": "id"}
    
    assert _get_contextual_skip_reason("child", "parent", "ctx", "fk", "src", data, pks) is None
    
    # Missing child column
    assert "Missing child columns: bad" in _get_contextual_skip_reason("child", "parent", "bad", "fk", "src", data, pks)
    
    # Missing parent column
    assert "Missing parent columns: bad" in _get_contextual_skip_reason("child", "parent", "ctx", "fk", "bad", data, pks)

def test_evaluate_single_contextual_fk_check():
    check = {
        "child_table": "child", "parent_table": "parent",
        "context_fk_column": "ctx", "child_fk_column": "fk", "parent_source_column": "src"
    }
    pks = {"parent": "id"}
    
    # Pass
    data_pass = {
        "child": pd.DataFrame({"ctx": [10, 20], "fk": [100, 200]}),
        "parent": pd.DataFrame({"id": [10, 20], "src": [100, 200]})
    }
    res = _evaluate_single_contextual_fk_check(check, data_pass, pks)
    assert res["status"] == "PASS"
    assert res["failed_rows"] == 0
    
    # Fail
    data_fail = {
        "child": pd.DataFrame({"ctx": [10, 20], "fk": [100, 999]}),
        "parent": pd.DataFrame({"id": [10, 20], "src": [100, 200]})
    }
    res = _evaluate_single_contextual_fk_check(check, data_fail, pks)
    assert res["status"] == "FAIL"
    assert res["failed_rows"] == 1
    assert "1 mismatches" in res["details"]
    
    # Skip
    data_skip = {"child": pd.DataFrame({"ctx": [10], "fk": [100]})}
    res = _evaluate_single_contextual_fk_check(check, data_skip, pks)
    assert res["status"] == "SKIPPED"

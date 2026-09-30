import pandas as pd
import pytest
from unittest.mock import patch

from backend.src.domain.general_sanity_checks import (
    run_general_sanity_checks,
    sanity_check_referential_integrity,
    sanity_check_contextual_fk_consistency,
)


@patch("backend.src.domain.general_sanity_checks.sanity_check_referential_integrity")
@patch("backend.src.domain.general_sanity_checks.sanity_check_contextual_fk_consistency")
def test_run_general_sanity_checks(mock_contextual, mock_referential):
    mock_referential.return_value = pd.DataFrame([{"check": "ref"}])
    mock_contextual.return_value = pd.DataFrame([{"check": "ctx"}])
    
    result = run_general_sanity_checks({"table1": pd.DataFrame(), "table2": pd.DataFrame()}, {})
    assert len(result) == 2
    assert list(result["check"]) == ["ref", "ctx"]

@patch("backend.src.domain.general_sanity_checks.sanity_check_referential_integrity")
@patch("backend.src.domain.general_sanity_checks.sanity_check_contextual_fk_consistency")
def test_run_general_sanity_checks_empty(mock_contextual, mock_referential):
    mock_referential.return_value = pd.DataFrame()
    mock_contextual.return_value = pd.DataFrame()
    
    result = run_general_sanity_checks({"table1": pd.DataFrame(), "table2": pd.DataFrame()}, {})
    assert result.empty

def test_sanity_check_referential_integrity_single_df():
    result = sanity_check_referential_integrity(pd.DataFrame(), {})
    assert result.empty

def test_sanity_check_referential_integrity_one_table():
    result = sanity_check_referential_integrity({"table1": pd.DataFrame()}, {})
    assert result.empty

@patch("backend.src.domain.general_sanity_checks._build_table_name_to_pks_mapping")
@patch("backend.src.domain.general_sanity_checks._collect_all_fks_to_check")
@patch("backend.src.domain.general_sanity_checks._evaluate_single_referential_integrity_check")
def test_sanity_check_referential_integrity_with_checks(
    mock_eval, mock_collect, mock_build
):
    mock_build.return_value = {"table1": ["id"]}
    mock_collect.return_value = [{"fk": "check1"}, {"fk": "check2"}]
    mock_eval.side_effect = [{"status": "PASS"}, {"status": "FAIL"}]
    
    synthetic_data = {"table1": pd.DataFrame(), "table2": pd.DataFrame()}
    result = sanity_check_referential_integrity(synthetic_data, {})
    
    assert len(result) == 2
    assert list(result["status"]) == ["PASS", "FAIL"]
    assert mock_eval.call_count == 2

@patch("backend.src.domain.general_sanity_checks._build_table_name_to_pks_mapping")
@patch("backend.src.domain.general_sanity_checks._collect_all_fks_to_check")
def test_sanity_check_referential_integrity_no_fks(mock_collect, mock_build):
    mock_build.return_value = {"table1": ["id"]}
    mock_collect.return_value = []
    
    synthetic_data = {"table1": pd.DataFrame(), "table2": pd.DataFrame()}
    result = sanity_check_referential_integrity(synthetic_data, {})
    assert result.empty

def test_sanity_check_contextual_fk_consistency_single_df():
    result = sanity_check_contextual_fk_consistency(pd.DataFrame(), {})
    assert result.empty

def test_sanity_check_contextual_fk_consistency_one_table():
    result = sanity_check_contextual_fk_consistency({"table1": pd.DataFrame()}, {})
    assert result.empty

@patch("backend.src.domain.general_sanity_checks._build_table_name_to_pks_mapping")
@patch("backend.src.domain.general_sanity_checks._collect_all_contextual_relationships_to_check")
@patch("backend.src.domain.general_sanity_checks._evaluate_single_contextual_fk_check")
def test_sanity_check_contextual_fk_consistency_with_checks(
    mock_eval, mock_collect, mock_build
):
    mock_build.return_value = {"table1": ["id"]}
    mock_collect.return_value = [{"ctx": "check1"}]
    mock_eval.return_value = {"status": "PASS"}
    
    synthetic_data = {"table1": pd.DataFrame(), "table2": pd.DataFrame()}
    result = sanity_check_contextual_fk_consistency(synthetic_data, {})
    
    assert len(result) == 1
    assert result["status"][0] == "PASS"

@patch("backend.src.domain.general_sanity_checks._build_table_name_to_pks_mapping")
@patch("backend.src.domain.general_sanity_checks._collect_all_contextual_relationships_to_check")
def test_sanity_check_contextual_fk_consistency_no_checks(mock_collect, mock_build):
    mock_build.return_value = {"table1": ["id"]}
    mock_collect.return_value = []
    
    synthetic_data = {"table1": pd.DataFrame(), "table2": pd.DataFrame()}
    result = sanity_check_contextual_fk_consistency(synthetic_data, {})
    assert result.empty


# -----------------------------------------------------------------------------
# Referential Integrity Integration Tests
# -----------------------------------------------------------------------------

def get_ref_metadata():
    """Metadata defining a simple parent-child relationship for referential integrity."""
    return {
        "tables": [
            {
                "name": "users",
                "primary_key": "id",
            },
            {
                "name": "orders",
                "primary_key": "id",
                "foreign_keys": [
                    {
                        "column": "user_id",
                        "referenced_table": "users",
                    }
                ]
            }
        ]
    }

def test_referential_integrity_pass():
    """Tests referential integrity when all foreign keys point to valid parent records."""
    metadata = get_ref_metadata()
    synthetic_data = {
        "users": pd.DataFrame({"id": [1, 2, 3], "name": ["Alice", "Bob", "Charlie"]}),
        "orders": pd.DataFrame({"id": [101, 102], "user_id": [1, 2], "amount": [50, 100]}),
    }
    
    report = sanity_check_referential_integrity(synthetic_data, metadata)
    assert len(report) == 1
    assert report.iloc[0]["table"] == "orders"
    assert report.iloc[0]["status"] == "PASS"
    assert report.iloc[0]["failed_rows"] == 0
    assert report.iloc[0]["total_rows"] == 2

def test_referential_integrity_fail():
    """Tests referential integrity when some foreign keys point to non-existent parent records."""
    metadata = get_ref_metadata()
    synthetic_data = {
        "users": pd.DataFrame({"id": [1], "name": ["Alice"]}),
        # user_id 2 and 3 do not exist in the users table
        "orders": pd.DataFrame({"id": [101, 102, 103], "user_id": [1, 2, 3], "amount": [50, 100, 150]}),
    }
    
    report = sanity_check_referential_integrity(synthetic_data, metadata)
    assert len(report) == 1
    assert report.iloc[0]["table"] == "orders"
    assert report.iloc[0]["status"] == "FAIL"
    assert report.iloc[0]["failed_rows"] == 2
    assert report.iloc[0]["total_rows"] == 3
    assert "examples: 2, 3" in report.iloc[0]["details"]

# -----------------------------------------------------------------------------
# Contextual FK Consistency Integration Tests
# -----------------------------------------------------------------------------

def get_ctx_metadata():
    """
    Metadata defining a grandparent -> parent -> child hierarchy.
    - Grandparent: company
    - Parent: department
    - Child: employee
    
    The employee table has a contextual FK to department, and a regular FK to company.
    The consistency check verifies that employee.company_id == department.company_id
    """
    return {
        "tables": [
            {
                "name": "company",
                "primary_key": "id",
            },
            {
                "name": "department",
                "primary_key": "id",
                "foreign_keys": [
                    {
                        "column": "company_id",
                        "referenced_table": "company",
                    }
                ]
            },
            {
                "name": "employee",
                "primary_key": "id",
                "foreign_keys": [
                    {
                        "column": "department_id",
                        "referenced_table": "department",
                        "is_context": True,  # This tells the system that department is the parent context
                    },
                    {
                        "column": "company_id",
                        "referenced_table": "company",
                    }
                ]
            }
        ]
    }

def test_contextual_fk_consistency_pass():
    """Tests contextual consistency when the child's derived FK matches the parent's FK."""
    metadata = get_ctx_metadata()
    synthetic_data = {
        "company": pd.DataFrame({"id": [10, 20]}),
        "department": pd.DataFrame({"id": [100, 200], "company_id": [10, 20]}),
        "employee": pd.DataFrame({"id": [1000, 1001], "department_id": [100, 200], "company_id": [10, 20]}),
    }
    
    report = sanity_check_contextual_fk_consistency(synthetic_data, metadata)
    assert len(report) == 1
    assert report.iloc[0]["table"] == "employee"
    assert report.iloc[0]["status"] == "PASS"
    assert report.iloc[0]["failed_rows"] == 0
    assert report.iloc[0]["total_rows"] == 2

def test_contextual_fk_consistency_fail():
    """Tests contextual consistency when the child's derived FK mismatches the parent's FK."""
    metadata = get_ctx_metadata()
    synthetic_data = {
        "company": pd.DataFrame({"id": [10, 20]}),
        "department": pd.DataFrame({"id": [100, 200], "company_id": [10, 20]}),
        # Employee 1001 points to department 200 (which belongs to company 20),
        # but the employee's company_id is incorrectly set to 10.
        "employee": pd.DataFrame({"id": [1000, 1001], "department_id": [100, 200], "company_id": [10, 10]}),
    }
    
    report = sanity_check_contextual_fk_consistency(synthetic_data, metadata)
    assert len(report) == 1
    assert report.iloc[0]["table"] == "employee"
    assert report.iloc[0]["status"] == "FAIL"
    assert report.iloc[0]["failed_rows"] == 1
    assert report.iloc[0]["total_rows"] == 2
    assert "1 mismatches" in report.iloc[0]["details"]

# -----------------------------------------------------------------------------
# Combined Orchestrator Integration Test
# -----------------------------------------------------------------------------

def test_run_general_sanity_checks_integration():
    """Tests that the orchestrator function successfully aggregates both check types."""
    metadata = get_ctx_metadata()
    synthetic_data = {
        "company": pd.DataFrame({"id": [10, 20]}),
        "department": pd.DataFrame({"id": [100, 200], "company_id": [10, 20]}),
        # Introduce a contextual mismatch for employee 1001
        "employee": pd.DataFrame({"id": [1000, 1001], "department_id": [100, 200], "company_id": [10, 10]}),
    }
    
    report = run_general_sanity_checks(synthetic_data, metadata)
    
    # We expect 4 checks in total:
    # 1. Referential: department -> company (PASS)
    # 2. Referential: employee -> department (PASS)
    # 3. Referential: employee -> company (PASS, since company 10 exists in company table)
    # 4. Contextual: employee via department -> company (FAIL, mismatch on company_id)
    assert len(report) == 4
    
    contextual_report = report[report["check"] == "contextual_fk_consistency"]
    assert len(contextual_report) == 1
    assert contextual_report.iloc[0]["status"] == "FAIL"
    
    ref_report = report[report["check"] == "referential_integrity"]
    assert len(ref_report) == 3
    assert all(ref_report["status"] == "PASS")


from backend.src.domain.general_sanity_checks import sanity_check_column_health


def test_column_health_flags_fully_null_column():
    df = pd.DataFrame({"id": [1, 2, 3], "end_date": [None, None, None]})
    report = sanity_check_column_health({"t": df})
    assert not report.empty
    flagged = report[report["rule"].str.contains("end_date")]
    assert len(flagged) == 1
    assert flagged.iloc[0]["status"] == "FAIL"
    assert flagged.iloc[0]["failed_rows"] == 3
    # The populated column must not be flagged.
    assert report["rule"].str.contains("'id'").sum() == 0


def test_column_health_treats_blank_strings_as_null():
    df = pd.DataFrame({"x": ["", "  ", "\t"]})
    report = sanity_check_column_health({"t": df})
    assert len(report) == 1
    assert report.iloc[0]["status"] == "FAIL"


def test_column_health_passes_when_all_columns_have_data():
    df = pd.DataFrame({"a": [1, 2], "b": ["x", "y"]})
    assert sanity_check_column_health({"t": df}).empty


def test_column_health_flags_empty_table():
    df = pd.DataFrame({"a": [], "b": []})
    report = sanity_check_column_health({"t": df})
    assert len(report) == 1
    assert "is empty" in report.iloc[0]["rule"]
    assert report.iloc[0]["total_rows"] == 0


def test_column_health_partial_null_not_flagged_by_default():
    # 1/3 null is below the default (fully-empty) threshold.
    df = pd.DataFrame({"x": [1, None, 3]})
    assert sanity_check_column_health({"t": df}).empty

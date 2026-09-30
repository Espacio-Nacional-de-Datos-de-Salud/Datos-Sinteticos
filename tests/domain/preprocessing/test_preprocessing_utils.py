import pandas as pd

from backend.src.domain.preprocessing import utils


def test_validate_referential_integrity_counts_orphans() -> None:
    parent = pd.Series([1, 2, 3])
    child = pd.Series([2, 2, 4, None])

    orphan_count, total = utils.validate_referential_integrity(parent, child)

    assert orphan_count == 1
    assert total == 3


def test_format_relationships_orders_context_first() -> None:
    relationships = {
        "fks": [
            {"child": "orders", "parent": "users", "fk_column": "user_id", "pk_column": "id"},
            {
                "child": "orders",
                "parent": "accounts",
                "fk_column": "account_id",
                "pk_column": "id",
                "is_context": True,
            },
        ]
    }

    formatted = utils.format_relationships(relationships)

    assert ("orders", "accounts") in formatted
    assert formatted[("orders", "accounts")][0] == ("account_id", "id")

def test_assign_default_context_keys_handles_no_relationships() -> None:
    relationships = {"fks": []}

    assigned = utils.assign_default_context_keys(relationships)

    assert assigned["fks"] == []

def test_assign_default_context_keys_sets_first_as_context_by_default() -> None:
    relationships = {
        "fks": [
            {
                "child": "orders", 
                "parent": "users", 
                "fk_column": "user_id", 
                "pk_column": "id"
            },
            {
                "child": "orders",
                "parent": "accounts",
                "fk_column": "account_id",
                "pk_column": "id",
            },
        ]
    }

    assigned = utils.assign_default_context_keys(relationships)

    # no intertwined relationships, first one set as context by default
    assert assigned["fks"][0]["is_context"]
    # other one should not be set as context
    assert not assigned["fks"][1]["is_context"]
    # both should be marked as direct, as they both are needed
    assert assigned["fks"][0]["direct"]
    assert assigned["fks"][1]["direct"]

def test_assign_default_context_keys_does_not_override_existing_context() -> None:
    relationships = {
        "fks": [
            {
                "child": "orders", 
                "parent": "users", 
                "fk_column": "user_id", 
                "pk_column": "id",
            },
            {
                "child": "orders",
                "parent": "accounts",
                "fk_column": "account_id",
                "pk_column": "id",
                "is_context": True,
            },
        ]
    }

    assigned = utils.assign_default_context_keys(relationships)

    # existing context should remain unchanged
    assert assigned["fks"][1]["is_context"]
    # other one should not be set as context
    assert not assigned["fks"][0]["is_context"]
    # both should be marked as direct, as they both are needed
    assert assigned["fks"][0]["direct"]
    assert assigned["fks"][1]["direct"]

def test_assign_default_context_keys_does_not_allow_multiple_contexts() -> None:
    relationships = {
        "fks": [
            {
                "child": "orders", 
                "parent": "users", 
                "fk_column": "user_id", 
                "pk_column": "id",
                "is_context": True,
            },
            {
                "child": "orders",
                "parent": "accounts",
                "fk_column": "account_id",
                "pk_column": "id",
                "is_context": True,
            },
        ]
    }

    assigned = utils.assign_default_context_keys(relationships)
    # first one will remain as context
    assert assigned["fks"][0]["is_context"]
    # other one should have context removed
    assert not assigned["fks"][1]["is_context"]
    # both should be marked as direct, as they both are needed
    assert assigned["fks"][0]["direct"]
    assert assigned["fks"][1]["direct"]

def test_assign_default_context_keys_keeps_existing_context_when_other_better() -> None:
    relationships = {
        "fks": [
            {
                "child": "orders", 
                "parent": "users", 
                "fk_column": "user_id", 
                "pk_column": "id",
            },
            {
                "child": "orders",
                "parent": "accounts",
                "fk_column": "account_id",
                "pk_column": "id",
            },
            {
                "child": "users",
                "parent": "accounts",
                "fk_column": "account_id",
                "pk_column": "id",
            },
            {
                "child": "orders",
                "parent": "otherTable",
                "fk_column": "other_id",
                "pk_column": "id",
                "is_context": True,
            },
        ]
    }
    # child.orders has two parents, users & accounts
    # but accounts can be accessed through users
    # so orders ->users should be set as direct
    # and users -> accounts direct and context
    # but orders -> otherTable already set as context for orders, so should remain that way


    assigned = utils.assign_default_context_keys(relationships)

    assert not assigned["fks"][0]["is_context"]
    assert not assigned["fks"][1]["is_context"]
    assert assigned["fks"][2]["is_context"]
    assert assigned["fks"][3]["is_context"]

    assert assigned["fks"][0]["direct"]
    assert not assigned["fks"][1]["direct"]
    assert assigned["fks"][2]["direct"]
    assert assigned["fks"][3]["direct"]


def test_assign_default_context_keys_two_trees() -> None:
    relationships = {
        "fks": [
            {
                "child": "orders", 
                "parent": "users", 
                "fk_column": "user_id", 
                "pk_column": "id",
            },
            {
                "child": "orders",
                "parent": "accounts",
                "fk_column": "account_id",
                "pk_column": "id",
            },
            {
                "child": "users",
                "parent": "accounts",
                "fk_column": "account_id",
                "pk_column": "id",
            },


            {
                "child": "otherBase",
                "parent": "otherParent",
                "fk_column": "other_id",
                "pk_column": "id",
            },
            {
                "child": "otherParent",
                "parent": "otherGrandparent",
                "fk_column": "grand_id",
                "pk_column": "id",
            },
            {
                "child": "otherBase",
                "parent": "otherDifParent",
                "fk_column": "other_dif_id",
                "pk_column": "id",
            }
        ]
    }
    # child.orders has two parents, users & accounts
    # but accounts can be accessed through users
    # so orders ->users should be set as direct
    # and users -> accounts direct and context
    # but orders -> otherTable already set as context for orders, so should remain that way


    assigned = utils.assign_default_context_keys(relationships)

    assert assigned["fks"][0]["is_context"]
    assert not assigned["fks"][1]["is_context"]
    assert assigned["fks"][2]["is_context"]

    assert assigned["fks"][0]["direct"]
    assert not assigned["fks"][1]["direct"]
    assert assigned["fks"][2]["direct"]


    assert assigned["fks"][3]["is_context"]
    assert assigned["fks"][4]["is_context"]
    assert not assigned["fks"][5]["is_context"]

    assert assigned["fks"][3]["direct"]
    assert assigned["fks"][4]["direct"]
    assert assigned["fks"][5]["direct"]

def test_assign_default_context_keys_only_self_referencing() -> None:
    relationships = {
        "fks": [
            {
                "child": "employees", 
                "parent": "employees", 
                "fk_column": "manager_id", 
                "pk_column": "id",
            }
        ]
    }

    assigned = utils.assign_default_context_keys(relationships)

    assert not assigned["fks"][0]["is_context"]
    assert not assigned["fks"][0]["direct"]

def test_assign_default_context_keys_multiple_self_referencing() -> None:
    relationships = {
        "fks": [
            {
                "child": "employees", 
                "parent": "employees", 
                "fk_column": "manager_id", 
                "pk_column": "id",
            },
            {
                "child": "managers", 
                "parent": "managers", 
                "fk_column": "_id", 
                "pk_column": "id",
            },
            {
                "child": "owners", 
                "parent": "owners", 
                "fk_column": "_id", 
                "pk_column": "id",
            }

        ]
    }

    assigned = utils.assign_default_context_keys(relationships)

    assert not assigned["fks"][0]["is_context"]
    assert not assigned["fks"][0]["direct"]
    assert not assigned["fks"][1]["is_context"]
    assert not assigned["fks"][1]["direct"]
    assert not assigned["fks"][2]["is_context"]
    assert not assigned["fks"][2]["direct"]

def test_assign_default_context_keys_one_self_reference_one_normal() -> None:
    relationships = {
        "fks": [
            {
                "child": "employees", 
                "parent": "employees", 
                "fk_column": "works_with", 
                "pk_column": "id",
            },
            {
                "child": "employees", 
                "parent": "managers", 
                "fk_column": "manager_id", 
                "pk_column": "id",
            }
        ]
    }

    assigned = utils.assign_default_context_keys(relationships)

    assert not assigned["fks"][0]["is_context"]
    assert not assigned["fks"][0]["direct"]
    assert assigned["fks"][1]["is_context"]
    assert assigned["fks"][1]["direct"]

def test_compute_context_depths() -> None:
    relationships = {
        "fks": [
            {
                "child": "orders", 
                "parent": "users", 
                "fk_column": "user_id", 
                "pk_column": "id",
                "is_context": True,
            },
            {
                "child": "users",
                "parent": "accounts",
                "fk_column": "account_id",
                "pk_column": "id",
                "is_context": True,
            },
            {
                "child": "orders",
                "parent": "otherTable",
                "fk_column": "other_id",
                "pk_column": "id",
            },
        ]
    }

    depths = utils._compute_context_depths(utils.group_fks_by_child(relationships))

    assert depths["accounts"] == 0
    assert depths["users"] == 1
    assert depths["orders"] == 2
from pathlib import Path

from backend.src.sessions import configs


def test_strip_template_header_removes_banner() -> None:
    example_text = (
        f"# {configs._EXAMPLE_CONFIG_HEADER_MARK}\n"
        "# Comment\n"
        "\n"
        "key: value\n"
    )

    stripped = configs._strip_template_header(example_text)

    assert stripped.startswith("key: value")


def test_real_content_for_rules_yaml_is_minimal() -> None:
    content = configs._content_for_real_from_example("ignored", Path("rules.yaml"))

    assert "rules: []" in content


def test_real_relative_key_for_alias() -> None:
    rel = configs._real_relative_key_for("rules")

    assert rel.as_posix() == "rules.yaml"

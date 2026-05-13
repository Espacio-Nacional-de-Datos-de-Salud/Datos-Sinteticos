"""Tests for the persistent interactive CLI session."""

from __future__ import annotations

import pytest

import backend.src.cli.main as cli_main
import backend.src.cli.wizard as wizard
from backend.src.cli.wizard import INTERACTIVE_EXIT


def test_interactive_session_runs_multiple_workflows_before_quit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prompts = iter(
        [
            ["--mode", "i", "--files", "/data/a.csv"],
            ["--mode", "t", "--inspection-id", "inspection_1"],
            INTERACTIVE_EXIT,
        ]
    )
    calls: list[list[str]] = []

    monkeypatch.setattr(cli_main, "print_session_banner", lambda: None)
    monkeypatch.setattr(cli_main, "prompt_for_workflow", lambda: next(prompts))
    monkeypatch.setattr(
        cli_main,
        "_run_args",
        lambda args, *, exit_on_error: calls.append(args),
    )

    cli_main._run_interactive_session()

    assert calls == [
        ["--mode", "i", "--files", "/data/a.csv"],
        ["--mode", "t", "--inspection-id", "inspection_1"],
    ]


def test_interactive_session_continues_after_argparse_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prompts = iter(
        [["--bad-flag"], ["--mode", "s", "--model-id", "model_1"], INTERACTIVE_EXIT]
    )
    calls: list[list[str]] = []

    def fake_run_args(args: list[str], *, exit_on_error: bool) -> None:
        calls.append(args)
        if args == ["--bad-flag"]:
            raise SystemExit(2)

    monkeypatch.setattr(cli_main, "print_session_banner", lambda: None)
    monkeypatch.setattr(cli_main, "prompt_for_workflow", lambda: next(prompts))
    monkeypatch.setattr(cli_main, "_run_args", fake_run_args)

    cli_main._run_interactive_session()

    assert calls == [["--bad-flag"], ["--mode", "s", "--model-id", "model_1"]]


def test_prompt_accepts_inline_mode_command(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "builtins.input", lambda _: "simulate --model-id model_1 --sample-size 25"
    )

    assert wizard.prompt_for_workflow() == [
        "--mode",
        "s",
        "--model-id",
        "model_1",
        "--sample-size",
        "25",
    ]


def test_prompt_opens_execution_menu(monkeypatch: pytest.MonkeyPatch) -> None:
    responses = iter(["ejecutar", "simulate --model-id model_1 --sample-size 25"])
    monkeypatch.setattr("builtins.input", lambda _: next(responses))

    assert wizard.prompt_for_workflow() == [
        "--mode",
        "s",
        "--model-id",
        "model_1",
        "--sample-size",
        "25",
    ]


def test_prompt_can_view_results_and_return(monkeypatch: pytest.MonkeyPatch) -> None:
    responses = iter(["resultados", "modelos", "volver"])
    viewed_catalogs: list[str] = []

    monkeypatch.setattr("builtins.input", lambda _: next(responses))
    monkeypatch.setattr(
        wizard,
        "_print_catalog",
        lambda catalog_type: viewed_catalogs.append(catalog_type),
    )

    assert wizard.prompt_for_workflow() is None
    assert viewed_catalogs == ["models"]


def test_prompt_can_go_back_from_execution_menu(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    responses = iter(["ejecutar", "volver"])
    monkeypatch.setattr("builtins.input", lambda _: next(responses))

    assert wizard.prompt_for_workflow() is None

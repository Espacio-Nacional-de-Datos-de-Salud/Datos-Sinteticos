[<-- Back to Main Index](../../README.md)
# Testing Guide

This document outlines the testing strategy, test organization, and execution commands for the project. The test suite verifies the application across multiple layers to catch regressions and ensure system reliability.

## Test Organization

The test suite is organized into five categories:

### 1. API Endpoint Integration Tests (`test_api_endpoints.py`)
Verify the HTTP request/response cycle for the FastAPI application. They test artifact catalog operations, configuration management, job cancellation, downloads, and metadata fallback routing using environment isolation fixtures.

### 2. End-to-End Service Flow Tests (`test_e2e_inspection_flow.py`, `test_e2e_simulation_flow.py`)
Stub external dependencies (file I/O, synthesis engines) to test the service layer's real dispatch, error handling, and cancellation logic. They ensure multi-step workflows process data correctly and respect cancellation events.

### 3. Domain Logic Unit Tests (`test_logical_rules.py`, `test_config_rules_defaults.py`, `test_inspection_rules_scoping.py`)
Verify core business logic in isolation:
- **Logical Rules**: Round-trip encoding/decoding behavior and violation detection.
- **Config Defaults**: Ensure configuration initializes properly without leaking example files.

### 4. Pipeline Unit Tests (`test_pipeline_executor.py`, `test_pipeline_loader.py`, `test_pipeline_main.py`)
Verify the pipeline orchestration layer:
- **Executor**: Job configuration resolution, step dispatch, artifact threading, and error propagation.
- **Loader**: YAML parsing, field defaults, and directory expansion.

### 5. CLI and Service Unit Tests (`test_cli_commands.py`, `test_evaluation_subprocess.py`, `test_services_artifacts.py`)
Verify CLI dispatch and service wiring:
- **Main CLI**: Command routing and artifact threading.
- **Subprocess**: Subprocess evaluation execution and error handling.
- **Artifacts**: Generator, metadata, and rule manager integration.

## Test Execution

Use the following `make` commands to run tests from the project root:

```bash
# Run the core test suite (excludes evaluation tests)
make test

# Run evaluation-specific tests (requires .venv_eval)
make test-eval
```

## Code Coverage

Code coverage measures the percentage of your codebase executed during tests. High coverage reduces the likelihood of undetected bugs, though it does not guarantee perfect functionality.

You can generate a comprehensive coverage report using:

```bash
make coverage
```

This command runs the entire test suite (both core and evaluation) and generates an interactive HTML report in the `htmlcov/` directory. Open `htmlcov/index.html` in your browser to view line-by-line coverage details, identify untested branches, and pinpoint areas needing additional tests.

## Fixtures

Our tests use `pytest` fixtures to maintain clean, isolated environments:
- **`isolated_files_root` / `isolated_config_root`**: Temporary directories to prevent real filesystem pollution.
- **`tmp_path`**: Built-in pytest temporary directory.
- **`monkeypatch`**: Used for replacing module attributes with test doubles.

When writing new tests, prefer these fixtures over mocking global state to maintain test speed and isolation.

[<-- Back to Main Index](../../README.md)

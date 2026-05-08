[<-- Back to Main Index](../../README.md)

# Repository Guidelines

> [!NOTE]
> The original purpose of this document was to provide a clear set of instructions for AI-based coding agents. However, these guidelines are standard for developers too, to ensure consistency, quality, and maintainability.


## 📁 Repository Context & Structure

- **Project**: Synthetic Data Tool for the ENDS (Espacio Nacional de Datos de Salud).
- **Core Technology**: Python 3.12.3, `uv`, Mostly AI Engine.

### Directory Overview
| Path | Purpose |
| :--- | :--- |
| `backend/config/` | YAML configuration (`default/` committed, `overrides/` gitignored and deep-merged) — `general.yaml`, `evaluation.yaml`, `mostly_ai.yaml`, `rules.yaml`, `pipelines/` |
| `backend/src/config/` | Config-loading code and non-tunable constants (`general.py`, `execution.py`, `evaluation.py`) |
| `data/` | Input datasets (usually symlinked) |
| `docs/` | Repository documentation (Markdown) |
| `outputs/` | Resulting artifacts (`models/`, `simulations/`, `evaluations/`) |
| `scripts/` | Automation and setup scripts |
| `src/` | Main source code (core logic, preprocessing, evaluation) |
| `tests/` | Pytest categorization |

---

## ⟨〉Committing Code

Adhere to the Conventional Commits format. Messages should be:
- atomic
- imperative
- clear and descriptive
- lowercase

**Format**: `<type>(<scope>): <subject>`

- **Simple scopes only**: examples `frontend`, `backend`, `api`.

| Type | Description |
| :--- | :--- |
| `✨feat` | A new feature |
| `🐛fix` | A bug fix |
| `📚docs` | Documentation changes |
| `🎨style` | Formatting, white-space, etc. (no logic changes) |
| `🔨refactor` | Code restructuring without adding features or fixing bugs |
| `🧪test` | Adding or correcting tests |
| `🧹chore` | Changes to build process, tools, or libraries |

- **Subject**: A short description in the imperative, present tense (e.g., `add date inequality rule` and not `Date inequality rule was added`).
- **Emoji**: Not mandatory, just makes it visually easier to group or identify types of commits.
---

## 🛠 Coding Standards & Guidelines

### 1. Minimize Git Diff Noise
Unnecessary modifications clutter the git history and make reviewing code difficult. As explained before a commit should either be a feature, a fix, a documentation change, a style change, a refactor, a test change or a chore change. But it can't be a feature and a style change at the same time because it makes it difficult to understand what logic changed.

- **Formatting**: Avoid changing the formatting of existing code unless explicitly fixing a style violation. FOR THAT USE RUFF FORMATTER (see section 3) and make automatic.
- **Focus**: Stick to the original code structure and formatting.
- **Comments**: Only add comments that are strictly necessary and concise. Comments should be minimized as they clutter code and need maintining as code changes, its better to make code autoexplainable.

### 2. Type Hints
**MANDATORY**: All function signatures and class properties MUST have comprehensive Python type hints.
- *Example*: `def calculate_duration(start: datetime, end: datetime) -> int:`

### 3. Formatting & Linting
- **Tool**: We use `ruff` (configured in `pyproject.toml`).
    - Enable automatic formatting in VSCode, if not you would need to run `ruff format` manually every time before committing.
- **Line Length**: 100 characters.
- **Rules**: Always adhere to the selected rule sets (`E`, `F`, `I`, `UP`, `B`).

### 4. Language & Naming
- **Internal Logic**: Everything (variable names, functions, logic) MUST be in **English**.
- **Descriptive Naming**: Variable and function names should be descriptive and verbose. 
  - ❌ Avoid: `cat`, `mod`, `i`, `df_2`.
  - ✅ Use: `category`, `model_instance`, `index`, `diagnoses_dataframe`.
- **Existing Code**: Do not start translating existing Spanish strings/comments to English unless explicitly requested, to keep the diffs clean.

---

## 📝 Docstring Structure

All functions and classes must use the Google Style format for docstrings:

```python
def example_function(param1: str, param2: int) -> bool:
    """Brief description of what the function does. 

    More detailed description if needed.

    Args:
        param1 (str): Description of param1.
        param2 (int): Description of param2.

    Returns:
        bool: Description of what the function returns.
    
    Raises:
        ValueError: Description of the condition that causes this error.

    Example:
        >>> result = example_function("hello", 5)
        >>> True
    """
    pass
```

---

## 📚 Documentation

Every significant task requires analyzing its impact on documentation:
1. Update existing `.md` files in `docs/` if logic changes.
2. Create a new `.md` file if a new concept or architectural part is added.
3. Update the `README.md` if the entry point or basic setup changes.

[<-- Back to Main Index](../../README.md)

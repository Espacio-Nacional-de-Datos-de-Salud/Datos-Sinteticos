"""Cleanup entry point for generated catalog artifacts."""

import argparse

from backend.src.core.catalog.inspections import cleanup_inspections
from backend.src.core.catalog.models import cleanup_models
from backend.src.core.catalog.pipelines import cleanup_pipelines
from backend.src.core.catalog.simulations import cleanup_simulations


def cleanup_all(stale_hours: int = 24) -> dict[str, dict[str, list[str]]]:
    """Run catalog cleanup for all generated run types."""
    deleted_inspections_empty, deleted_inspections_orphans, deleted_inspections_duplicates = (
        cleanup_inspections(
            stale_hours=stale_hours,
        )
    )
    deleted_models_empty, deleted_models_orphans, skipped_models = cleanup_models(
        stale_hours=stale_hours,
    )
    deleted_simulations_empty, deleted_simulations_orphans, skipped_simulations = (
        cleanup_simulations(stale_hours=stale_hours)
    )
    deleted_pipelines_empty, deleted_pipelines_orphans = cleanup_pipelines(
        stale_hours=stale_hours,
    )

    return {
        "inspections": {
            "empty": deleted_inspections_empty,
            "orphans": deleted_inspections_orphans,
            "duplicates": deleted_inspections_duplicates,
        },
        "models": {
            "empty": deleted_models_empty,
            "orphans": deleted_models_orphans,
            "skipped": skipped_models,
        },
        "simulations": {
            "empty": deleted_simulations_empty,
            "orphans": deleted_simulations_orphans,
            "skipped": skipped_simulations,
        },
        "pipelines": {
            "empty": deleted_pipelines_empty,
            "orphans": deleted_pipelines_orphans,
        },
    }


def main() -> None:
    """CLI entry point for catalog cleanup."""
    parser = argparse.ArgumentParser(description="Clean generated catalog artifacts")
    parser.add_argument("--stale-hours", type=int, default=24, help="Cleanup age threshold")
    args = parser.parse_args()

    results = cleanup_all(stale_hours=args.stale_hours)
    for category, cleanup_result in results.items():
        deleted_count = len(cleanup_result.get("empty", [])) + len(
            cleanup_result.get("orphans", [])
        )
        skipped_count = len(cleanup_result.get("skipped", []))
        if skipped_count:
            print(f"{category}: deleted {deleted_count}, skipped {skipped_count}")
        else:
            print(f"{category}: deleted {deleted_count}")


if __name__ == "__main__":
    main()

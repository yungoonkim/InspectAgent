"""Utility script to compute and persist baseline brightness statistics for MVTec AD Bottle dataset."""

from pathlib import Path
import json
import sys

from backend.config import PROJECT_ROOT, get_settings
from backend.vision import compute_baseline_statistics


def main() -> int:
    settings = get_settings()
    train_good_dir = settings.absolute_dataset_path / "train" / "good"

    if not train_good_dir.exists():
        print(f"Error: Dataset train/good directory not found at {train_good_dir}", file=sys.stderr)
        return 1

    output_path = PROJECT_ROOT / "data" / "baseline_brightness.json"
    print(f"Calculating baseline brightness statistics from: {train_good_dir}")

    stats = compute_baseline_statistics(train_good_dir, force_refresh=True, save_path=output_path)

    print(f"Computed stats for {stats['sample_count']} images.")
    print(f"Saved baseline statistics to: {output_path}")
    print(json.dumps(stats, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

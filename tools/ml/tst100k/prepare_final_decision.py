"""Seal unused TST100K scenes for the final risk-aware selector experiment.

This CPU preflight reads manifests only. It neither stages photographs nor
loads the expert edits or any model checkpoint.
"""

from __future__ import annotations

import json
from pathlib import Path

from .data import DATASET_REVISION, fetch_manifest
from .prepare_selector import checksum, scene_set, select_rows
from .prepare_v4 import mounted_file

SEED = 8413
COUNTS = {"train": 1024, "validation": 256, "final": 256}


def excluded_scenes(old: dict, audit: dict, v4: dict, selector: dict) -> set[str]:
    """Count every earlier target or reference, including sealed partitions."""
    manifests = (old, v4, selector)
    if any(item["datasetRevision"] != DATASET_REVISION for item in manifests):
        raise RuntimeError("An earlier run used a different dataset revision")
    rows = [row for group in old["splits"].values() for row in group]
    rows.extend(audit["rows"])
    rows.extend(v4["rows"])
    rows.extend(row for group in selector["splits"].values() for row in group)
    return scene_set(rows)


def main() -> None:
    output = Path("/kaggle/working/colorcheck-tst100k-final-decision-preflight")
    output.mkdir(parents=True, exist_ok=True)
    old = json.loads(mounted_file("colorcheck-tst100k-expanded-validation", "splits.json").read_text())
    audit = json.loads(mounted_file("colorcheck-tst100k-fresh-evaluation", "splits.json").read_text())
    v4 = json.loads(mounted_file("colorcheck-tst100k-v4-preflight", "final-holdout.json").read_text())
    selector = json.loads(mounted_file("colorcheck-tst100k-selector-preflight", "selector-splits.json").read_text())
    excluded = excluded_scenes(old, audit, v4, selector)
    splits = select_rows(fetch_manifest(), excluded, COUNTS, SEED)
    payload = {"datasetRevision": DATASET_REVISION, "seed": SEED, "splits": splits}
    summary = {
        "ready": True,
        "counts": {name: len(rows) for name, rows in splits.items()},
        "excludedScenes": len(excluded),
        "manifestSha256": checksum(payload),
        "finalSha256": checksum({"rows": splits["final"]}),
        "note": "Manifest-only preflight; no photographs or expert edits opened.",
    }
    (output / "splits.json").write_text(json.dumps(payload, indent=2))
    (output / "preflight.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary), flush=True)


if __name__ == "__main__":
    main()

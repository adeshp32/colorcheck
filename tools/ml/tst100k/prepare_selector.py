"""Reserve unseen TST100K scenes before fitting a deployment selector.

This preflight reads only JSON manifests. It never fetches photographs, opens
expert edits, or loads either candidate matcher.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .data import DATASET_REVISION, fetch_manifest, scene_id
from .prepare_v4 import mounted_file

SEED = 7201
COUNTS = {"train": 1024, "validation": 256, "final": 256}


def scene_set(rows: list[dict]) -> set[str]:
    """Count a photograph in either target or reference position."""
    return {scene_id(row[key]) for row in rows for key in ("content", "reference")}


def select_rows(records: list[dict], excluded: set[str], counts: dict[str, int] = COUNTS) -> dict:
    """Hash-rank eligible rows, keeping all three partitions scene-disjoint."""
    ranked = sorted(
        records,
        key=lambda row: hashlib.sha256(
            f"{SEED}:{row['content']}:{row['reference']}:{row['gt']}".encode()
        ).digest(),
    )
    partitions = {name: [] for name in counts}
    occupied = set(excluded)
    for name, count in counts.items():
        targets = set()
        for row in ranked:
            target = scene_id(row["content"])
            reference = scene_id(row["reference"])
            if (target in occupied or reference in occupied or target == reference
                    or scene_id(row["gt"]) != target or target in targets):
                continue
            partitions[name].append(row)
            targets.add(target)
            if len(partitions[name]) == count:
                break
        if len(partitions[name]) != count:
            raise ValueError(f"Insufficient unseen {name} targets: {len(partitions[name])}/{count}")
        occupied.update(scene_set(partitions[name]))
    return partitions


def checksum(payload: dict) -> str:
    """Hash canonical JSON, independent of whitespace in the saved file."""
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def main() -> None:
    output = Path("/kaggle/working/colorcheck-tst100k-selector-preflight")
    output.mkdir(parents=True, exist_ok=True)
    old = json.loads(mounted_file("colorcheck-tst100k-expanded-validation", "splits.json").read_text())
    audit = json.loads(mounted_file("colorcheck-tst100k-fresh-evaluation", "splits.json").read_text())
    v4 = json.loads(mounted_file("colorcheck-tst100k-v4-preflight", "final-holdout.json").read_text())
    if old["datasetRevision"] != DATASET_REVISION or v4["datasetRevision"] != DATASET_REVISION:
        raise RuntimeError("Pinned dataset revision changed")
    excluded = scene_set([
        row for rows in old["splits"].values() for row in rows
    ] + audit["rows"] + v4["rows"])
    partitions = select_rows(fetch_manifest(), excluded)
    payload = {"datasetRevision": DATASET_REVISION, "seed": SEED, "splits": partitions}
    (output / "selector-splits.json").write_text(json.dumps(payload, indent=2))
    result = {
        "ready": True,
        "counts": {name: len(rows) for name, rows in partitions.items()},
        "excludedScenes": len(excluded),
        "manifestSha256": checksum(payload),
        "finalSha256": checksum({"rows": partitions["final"]}),
        "note": "Manifest-only preflight; no photographs or expert edits opened.",
    }
    (output / "preflight.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()

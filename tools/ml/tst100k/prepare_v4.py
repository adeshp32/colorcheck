"""Freeze v4's final holdout and verify strong-edit validation coverage.

Run this on Kaggle CPU before training. It excludes every scene used by v3 or
its later audit, then checks that validation can test the stated hypothesis.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from torch.utils.data import DataLoader

from .data import TripletDataset, fetch_manifest, scene_id, stage_images

FINAL_SEED = 6109
FINAL_COUNT = 256
STRONG_EDIT_THRESHOLD = 0.08


def mounted_file(kernel_slug: str, name: str) -> Path:
    """Resolve a mounted output without confusing two similarly named files."""
    matches = [
        path for path in Path("/kaggle/input").rglob(name)
        if kernel_slug in path.parts
    ]
    if len(matches) != 1:
        raise RuntimeError(f"Expected one {name} from {kernel_slug}; found {matches}")
    return matches[0]


def select_final_rows(records: list[dict], old_splits: dict, audit_rows: list[dict]) -> list[dict]:
    """Select fixed, never-seen target and reference scenes by hash rank."""
    used = {
        scene_id(row[key])
        for rows in (*old_splits.values(), audit_rows)
        for row in rows
        for key in ("content", "reference")
    }
    ranked = sorted(
        records,
        key=lambda row: hashlib.sha256(
            f"{FINAL_SEED}:{row['content']}:{row['reference']}:{row['gt']}".encode()
        ).digest(),
    )
    selected = []
    targets = set()
    for row in ranked:
        target = scene_id(row["content"])
        reference = scene_id(row["reference"])
        if (
            target in used or reference in used or target == reference
            or target in targets or scene_id(row["gt"]) != target
        ):
            continue
        selected.append(row)
        targets.add(target)
        if len(selected) == FINAL_COUNT:
            break
    if len(selected) != FINAL_COUNT:
        raise ValueError(f"Expected {FINAL_COUNT} untouched targets; found {len(selected)}")
    return selected


def strong_edit_count(rows: list[dict], scratch: Path) -> int:
    """Count source/expert pairs with at least 0.08 mean RGB change."""
    loader = DataLoader(TripletDataset(rows, scratch, 128), batch_size=8, num_workers=2)
    return sum(
        int(((batch["expected"] - batch["source"]).abs().mean(dim=(1, 2, 3))
            >= STRONG_EDIT_THRESHOLD).sum())
        for batch in loader
    )


def main() -> None:
    output = Path("/kaggle/working/colorcheck-tst100k-v4-preflight")
    scratch = Path("/kaggle/temp/colorcheck-tst100k-v4-preflight")
    output.mkdir(parents=True, exist_ok=True)
    old = json.loads(mounted_file("colorcheck-tst100k-expanded-validation", "splits.json").read_text())
    audit = json.loads(mounted_file("colorcheck-tst100k-fresh-evaluation", "splits.json").read_text())
    final_rows = select_final_rows(fetch_manifest(), old["splits"], audit["rows"])
    payload = {"datasetRevision": old["datasetRevision"], "seed": FINAL_SEED, "rows": final_rows}
    manifest = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    (output / "final-holdout.json").write_text(json.dumps(payload, indent=2))
    checksum = hashlib.sha256(manifest.encode()).hexdigest()
    print(json.dumps({"finalTargets": len(final_rows), "manifestSha256": checksum}), flush=True)

    print(json.dumps({"stagedValidation": stage_images({"validation": old["splits"]["validation"]}, scratch)}), flush=True)
    strong = strong_edit_count(old["splits"]["validation"], scratch)
    result = {
        "finalTargets": len(final_rows),
        "finalSeed": FINAL_SEED,
        "manifestSha256": checksum,
        "validationTargets": len(old["splits"]["validation"]),
        "strongValidationTargets": strong,
        "strongEditThreshold": STRONG_EDIT_THRESHOLD,
        "ready": strong >= 20,
    }
    (output / "preflight.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result), flush=True)
    if not result["ready"]:
        raise RuntimeError("Fewer than 20 strong-edit validation targets; revise protocol before GPU training")


if __name__ == "__main__":
    main()

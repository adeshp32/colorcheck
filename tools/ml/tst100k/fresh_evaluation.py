"""Evaluate a frozen checkpoint on scenes absent from every prior split.

The training run's split manifest is the exclusion list. This script never
updates model weights or chooses a checkpoint from these fresh examples.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import torch
from torch.utils.data import DataLoader

from tools.ml.reference_matcher.model import ReferenceLutModel
from .data import TripletDataset, fetch_manifest, scene_id, stage_images
from .review import example_groups, find_source_file, render_group, score_test_rows
from .train import evaluate


def fresh_rows(records: list[dict[str, str]], old_splits: dict, count: int, seed: int) -> list[dict[str, str]]:
    """Keep both target and reference scenes outside all earlier partitions."""
    excluded = {
        scene_id(row[key])
        for split in old_splits.values()
        for row in split
        for key in ("content", "reference")
    }
    ranked = sorted(
        records,
        key=lambda row: hashlib.sha256(
            f"{seed}:{row['content']}:{row['reference']}:{row['gt']}".encode()
        ).digest(),
    )
    selected = []
    used_targets = set()
    for row in ranked:
        target, reference = scene_id(row["content"]), scene_id(row["reference"])
        if (
            target in excluded
            or reference in excluded
            or target == reference
            or target in used_targets
            or scene_id(row["gt"]) != target
        ):
            continue
        selected.append(row)
        used_targets.add(target)
        if len(selected) == count:
            break
    if len(selected) != count:
        raise ValueError(f"Requested {count} untouched targets; found {len(selected)}")
    return selected


def main() -> None:
    torch.set_num_threads(4)
    seed = 3091
    count = 160
    output = Path("/kaggle/working/colorcheck-tst100k-fresh-evaluation")
    scratch = Path("/kaggle/temp/colorcheck-tst100k-fresh-evaluation")
    output.mkdir(parents=True, exist_ok=True)
    old = json.loads(find_source_file("splits.json").read_text())
    rows = fresh_rows(fetch_manifest(), old["splits"], count, seed)
    (output / "splits.json").write_text(
        json.dumps({"seed": seed, "sourceSplitSeed": old["seed"], "rows": rows}, indent=2)
    )
    print(json.dumps({"freshTargets": len(rows), "excludedPriorScenes": len({
        scene_id(row[key]) for split in old["splits"].values()
        for row in split for key in ("content", "reference")
    })}), flush=True)
    print(json.dumps({"staged": stage_images({"test": rows}, scratch)}), flush=True)

    checkpoint = torch.load(find_source_file("best.pt"), map_location="cpu", weights_only=True)
    model = ReferenceLutModel()
    model.load_state_dict(checkpoint["state_dict"])
    loader = DataLoader(TripletDataset(rows, scratch, 128), batch_size=8, num_workers=2)
    metrics = evaluate(model, loader, torch.device("cpu"), seed)
    scores = score_test_rows(model, rows, scratch)
    groups = example_groups(scores)
    for name, scenes in groups.items():
        render_group(model, rows, scratch, scenes, output / f"{name}.png")
    result = {
        "checkpointEpoch": checkpoint["epoch"],
        "freshTargets": count,
        "worseThanCurrentCount": sum(row["gain"] < 0 for row in scores),
        "metrics": metrics,
        "groups": groups,
        "note": "Frozen-checkpoint, untouched-scene audit; not used for model selection.",
    }
    (output / "evaluation.json").write_text(json.dumps(result, indent=2))
    print(json.dumps({"freshTargets": count, "worseThanCurrentCount": result["worseThanCurrentCount"]}), flush=True)


if __name__ == "__main__":
    main()

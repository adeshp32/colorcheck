"""Generate the private Kaggle pilot directly from reviewed repository modules."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "kaggle" / "tst100k"
RUN_NAME = "colorcheck-tst100k-v2"
MODULES = {
    "tools/ml/reference_matcher": ("model.py", "losses.py", "dataset.py", "evaluation.py"),
    "tools/ml/tst100k": ("data.py", "train.py"),
}


def cell(kind: str, text: str) -> dict:
    result = {
        "cell_type": kind,
        "id": hashlib.sha1(f"{kind}:{text}".encode()).hexdigest()[:8],
        "metadata": {},
        "source": text.splitlines(True),
    }
    if kind == "code":
        result.update(execution_count=None, outputs=[])
    return result


def build() -> dict:
    cells = [
        cell(
            "markdown",
            "# ColorCheck TST100K reference matcher: expanded validation\n\n"
            "**Question:** does the correct reference improve a held-out target more "
            "than a wrong reference, an unchanged photo, and the editor's existing "
            "statistics matcher?\n\n"
            "This notebook trains original PyTorch weights on a larger, deterministic "
            "sample of [TST100K](https://huggingface.co/datasets/ToneStyle/TST100K). "
            "The dataset is restricted to non-commercial academic research. It is "
            "not copied into Git, and this run does not deploy a model."
        ),
        cell(
            "code",
            "import sys, torch\n"
            "from pathlib import Path\n"
            "assert torch.cuda.is_available(), 'Enable a Kaggle GPU first'\n"
            "for path in ('tools', 'tools/ml', 'tools/ml/reference_matcher', 'tools/ml/tst100k'):\n"
            "    target = Path('/kaggle/working') / path\n"
            "    target.mkdir(parents=True, exist_ok=True)\n"
            "    (target / '__init__.py').touch()\n"
            "print({'python':sys.version.split()[0], 'torch':torch.__version__, "
            "'gpu':torch.cuda.get_device_name(0)})\n"
        ),
    ]
    for directory, files in MODULES.items():
        for filename in files:
            source = (ROOT / directory / filename).read_text()
            cells.append(cell("markdown", f"## {directory}/{filename}\n\nSource of truth: repository module."))
            cells.append(cell("code", f"%%writefile /kaggle/working/{directory}/{filename}\n{source}"))
    cells.extend(
        [
            cell(
                "markdown",
                "## Controlled pilot\n\n"
                "The manifest is pinned to a dataset commit. Source and reference "
                "scene IDs must hash to the same split; ground truth shares the "
                "source scene. Images download only to `/kaggle/temp`, and outputs "
                "contain metrics, split paths, and one checkpoint. The best epoch "
                "is chosen by validation. Test metrics are computed once afterward."
            ),
            cell(
                "code",
                "import subprocess\n"
                "subprocess.run([sys.executable, '-m', 'tools.ml.tst100k.train',\n"
                "    '--train-pairs', '1024', '--validation-pairs', '160',\n"
                "    '--test-pairs', '320', '--epochs', '8', '--batch-size', '8',\n"
                "    '--workers', '2', '--size', '128', '--seed', '2027',\n"
                f"    '--output-dir', '/kaggle/working/{RUN_NAME}',\n"
                f"    '--scratch-dir', '/kaggle/temp/{RUN_NAME}'],\n"
                "    cwd='/kaggle/working', check=True)\n"
            ),
            cell(
                "code",
                "import json\n"
                "from pathlib import Path\n"
                f"summary = json.loads(Path('/kaggle/working/{RUN_NAME}/summary.json').read_text())\n"
                "print(json.dumps({'checkpointEpoch':summary['selectedCheckpointEpoch'], "
                "'gates':summary['gates'], 'test':summary['test']}, indent=2))\n"
            ),
        ]
    )
    return {
        "cells": cells,
        "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}},
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    run_directory = OUT / "expanded-validation"
    run_directory.mkdir(parents=True, exist_ok=True)
    path = run_directory / f"{RUN_NAME}.ipynb"
    path.write_text(json.dumps(build(), indent=1, ensure_ascii=True) + "\n")
    print(path)


if __name__ == "__main__":
    main()

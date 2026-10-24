"""Package the untouched-scene, CPU-only checkpoint evaluation for Kaggle."""

from __future__ import annotations

import json

from .build_kaggle_notebook import ROOT, cell
from .build_review_notebook import build as build_review


def build() -> dict:
    notebook = build_review()
    notebook["cells"][0] = cell(
        "markdown",
        "# TST100K fresh-scene evaluation\n\n"
        "Freeze the existing checkpoint. Exclude every target and reference "
        "scene from its previous train, validation, and test partitions. "
        "Evaluate model, wrong reference, unchanged source, and current "
        "matcher on 160 newly selected scenes. Contact sheets expose both "
        "strong and weak cases; this audit does not select training settings.",
    )
    source = (ROOT / "tools/ml/tst100k/fresh_evaluation.py").read_text()
    notebook["cells"][-1] = cell(
        "code", f"%%writefile /kaggle/working/tools/ml/tst100k/fresh_evaluation.py\n{source}"
    )
    notebook["cells"].append(cell(
        "code",
        "import subprocess, sys\n"
        "subprocess.run([sys.executable, '-m', 'tools.ml.tst100k.fresh_evaluation'], "
        "cwd='/kaggle/working', check=True)\n",
    ))
    return notebook


def main() -> None:
    destination = ROOT / "kaggle/tst100k/fresh-evaluation/colorcheck-tst100k-fresh-evaluation.ipynb"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(build(), indent=1, ensure_ascii=True) + "\n")
    print(destination)


if __name__ == "__main__":
    main()

"""Generate a private CPU-only Kaggle pilot from reviewed repository files."""

from __future__ import annotations

import json

from .build_kaggle_notebook import ROOT, cell


def build() -> dict:
    cells = [
        cell("markdown", "# ColorCheck adaptive deterministic matcher\n\n"
             "Fit palette and tone strengths from TST100K expert edits. The current "
             "browser matcher is the baseline; only preflight training and validation "
             "images are opened. The final partition stays sealed. This is a CPU pilot, "
             "not a deployment decision."),
        cell("code", "from pathlib import Path\nimport numpy, sklearn, torch\n"
             "for directory in ('tools', 'tools/ml', 'tools/ml/tst100k'):\n"
             "    path = Path('/kaggle/working') / directory\n"
             "    path.mkdir(parents=True, exist_ok=True)\n"
             "    (path / '__init__.py').touch()\n"
             "print({'numpy': numpy.__version__, 'sklearn': sklearn.__version__, "
             "'torch': torch.__version__})\n"),
    ]
    for name in ("data.py", "prepare_v4.py", "prepare_selector.py", "adaptive_rules_core.py", "train_adaptive_rules.py"):
        source = (ROOT / "tools/ml/tst100k" / name).read_text()
        cells.append(cell("code", f"%%writefile /kaggle/working/tools/ml/tst100k/{name}\n{source}"))
    cells.append(cell("code", "import subprocess, sys\n"
                      "subprocess.run([sys.executable, '-m', 'tools.ml.tst100k.train_adaptive_rules'], "
                      "cwd='/kaggle/working', check=True, timeout=5400)\n"))
    return {
        "cells": cells,
        "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}},
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def main() -> None:
    destination = ROOT / "kaggle/tst100k/adaptive-deterministic-matcher/colorcheck-adaptive-matcher.ipynb"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(build(), indent=1, ensure_ascii=True) + "\n")
    print(destination)


if __name__ == "__main__":
    main()

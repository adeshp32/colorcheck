"""Package the frozen, one-time final audit as a private Kaggle notebook."""

from __future__ import annotations

import json

from .build_kaggle_notebook import MODULES, ROOT, cell


def build() -> dict:
    cells = [
        cell("markdown", "# ColorCheck selector: sealed final audit\n\n"
             "The v3 LUT, selector coefficients, feature order, and 0.60 threshold "
             "were fixed before opening these 256 new photos. This notebook "
             "evaluates once; it does not train, choose a setting, or deploy."),
        cell("code", "from pathlib import Path\nimport torch\n"
             "assert torch.cuda.is_available(), 'Enable a Kaggle GPU'\n"
             "for directory in ('tools', 'tools/ml', 'tools/ml/reference_matcher', 'tools/ml/tst100k'):\n"
             "    path = Path('/kaggle/working') / directory\n"
             "    path.mkdir(parents=True, exist_ok=True)\n"
             "    (path / '__init__.py').touch()\n"
             "print({'torch': torch.__version__, 'gpu': torch.cuda.get_device_name(0)})\n"),
    ]
    for directory, names in MODULES.items():
        for name in names:
            source = (ROOT / directory / name).read_text()
            cells.append(cell("code", f"%%writefile /kaggle/working/{directory}/{name}\n{source}"))
    for name in ("prepare_v4.py", "prepare_selector.py", "selector.py", "train_selector.py",
                 "review.py", "final_selector.py"):
        source = (ROOT / "tools/ml/tst100k" / name).read_text()
        cells.append(cell("code", f"%%writefile /kaggle/working/tools/ml/tst100k/{name}\n{source}"))
    cells.append(cell("code", "import subprocess, sys\n"
                      "subprocess.run([sys.executable, '-m', 'tools.ml.tst100k.final_selector'], "
                      "cwd='/kaggle/working', check=True, timeout=9000)\n"))
    return {
        "cells": cells,
        "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}},
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def main() -> None:
    destination = ROOT / "kaggle/tst100k/selector-final/colorcheck-selector-final-audit.ipynb"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(build(), indent=1, ensure_ascii=True) + "\n")
    print(destination)


if __name__ == "__main__":
    main()

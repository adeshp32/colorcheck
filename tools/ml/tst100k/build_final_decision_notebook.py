"""Generate the frozen-candidate, validation-only risk-aware selector run."""

from __future__ import annotations

import json

from .build_kaggle_notebook import MODULES, ROOT, cell


def build() -> dict:
    cells = [
        cell("markdown", "# ColorCheck final selector decision\n\n"
             "Fit a risk-aware linear route using new training scenes and choose "
             "a setting on validation only. The final photo partition stays sealed."),
        cell("code", "from pathlib import Path\nimport torch, sklearn\n"
             "assert torch.cuda.is_available(), 'Enable a Kaggle GPU'\n"
             "for directory in ('tools', 'tools/ml', 'tools/ml/reference_matcher', 'tools/ml/tst100k'):\n"
             "    path = Path('/kaggle/working') / directory\n"
             "    path.mkdir(parents=True, exist_ok=True)\n"
             "    (path / '__init__.py').touch()\n"
             "print({'torch': torch.__version__, 'sklearn': sklearn.__version__, "
             "'gpu': torch.cuda.get_device_name(0)})\n"),
    ]
    for directory, names in MODULES.items():
        for name in names:
            source = (ROOT / directory / name).read_text()
            cells.append(cell("code", f"%%writefile /kaggle/working/{directory}/{name}\n{source}"))
    for name in ("prepare_v4.py", "prepare_selector.py", "selector.py", "train_selector.py",
                 "review.py", "final_selector.py", "train_final_decision.py"):
        source = (ROOT / "tools/ml/tst100k" / name).read_text()
        cells.append(cell("code", f"%%writefile /kaggle/working/tools/ml/tst100k/{name}\n{source}"))
    cells.append(cell("code", "import subprocess, sys\n"
                      "subprocess.run([sys.executable, '-m', 'tools.ml.tst100k.train_final_decision'], "
                      "cwd='/kaggle/working', check=True, timeout=9000)\n"))
    return {
        "cells": cells,
        "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}},
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def main() -> None:
    destination = ROOT / "kaggle/tst100k/final-decision-training/colorcheck-final-decision-training.ipynb"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(build(), indent=1, ensure_ascii=True) + "\n")
    print(destination)


if __name__ == "__main__":
    main()

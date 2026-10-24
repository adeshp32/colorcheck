"""Package the CPU-only visual audit as a private Kaggle notebook."""

from __future__ import annotations

import json
from pathlib import Path

from .build_kaggle_notebook import MODULES, ROOT, cell


def build() -> dict:
    cells = [
        cell(
            "markdown",
            "# TST100K held-out visual review\n\n"
            "This CPU-only audit mounts the previously trained checkpoint and test "
            "split. It compares the current ColorCheck matcher with the trained "
            "model and the dataset's expected edit. Worst, fixed-random, and best "
            "examples are all shown; none are used to choose training settings.",
        ),
        cell(
            "code",
            "from pathlib import Path\n"
            "for path in ('tools', 'tools/ml', 'tools/ml/reference_matcher', 'tools/ml/tst100k'):\n"
            "    target = Path('/kaggle/working') / path\n"
            "    target.mkdir(parents=True, exist_ok=True)\n"
            "    (target / '__init__.py').touch()\n"
            "print('Mounted checkpoint:', list(Path('/kaggle/input').rglob('best.pt')))\n",
        ),
    ]
    for directory, files in MODULES.items():
        for filename in files:
            source = (ROOT / directory / filename).read_text()
            cells.append(cell("code", f"%%writefile /kaggle/working/{directory}/{filename}\n{source}"))
    review_path = ROOT / "tools/ml/tst100k/review.py"
    cells.append(cell("code", f"%%writefile /kaggle/working/tools/ml/tst100k/review.py\n{review_path.read_text()}"))
    cells.append(
        cell(
            "code",
            "import subprocess, sys\n"
            "subprocess.run([sys.executable, '-m', 'tools.ml.tst100k.review'], "
            "cwd='/kaggle/working', check=True)\n",
        )
    )
    return {
        "cells": cells,
        "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}},
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def main() -> None:
    destination = ROOT / "kaggle/tst100k/visual-review/colorcheck-tst100k-visual-review.ipynb"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(build(), indent=1, ensure_ascii=True) + "\n")
    print(destination)


if __name__ == "__main__":
    main()

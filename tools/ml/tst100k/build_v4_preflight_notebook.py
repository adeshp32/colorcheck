"""Generate the private CPU notebook that freezes v4's evaluation contract."""

from __future__ import annotations

import json

from .build_kaggle_notebook import ROOT, cell


def build() -> dict:
    cells = [
        cell(
            "markdown",
            "# ColorCheck v4 preflight\n\n"
            "CPU only. Freeze a new 256-target final holdout whose target and "
            "reference scenes are absent from every earlier run. Verify that "
            "v3 validation contains at least 20 strong edits before GPU use.",
        ),
        cell(
            "code",
            "from pathlib import Path\n"
            "for directory in ('tools', 'tools/ml', 'tools/ml/tst100k'):\n"
            "    path = Path('/kaggle/working') / directory\n"
            "    path.mkdir(parents=True, exist_ok=True)\n"
            "    (path / '__init__.py').touch()\n",
        ),
    ]
    for filename in ("data.py", "prepare_v4.py"):
        source = (ROOT / "tools/ml/tst100k" / filename).read_text()
        cells.append(cell("code", f"%%writefile /kaggle/working/tools/ml/tst100k/{filename}\n{source}"))
    cells.append(
        cell(
            "code",
            "import subprocess, sys\n"
            "subprocess.run([sys.executable, '-m', 'tools.ml.tst100k.prepare_v4'], "
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
    destination = ROOT / "kaggle/tst100k/v4-preflight/colorcheck-tst100k-v4-preflight.ipynb"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(build(), indent=1, ensure_ascii=True) + "\n")
    print(destination)


if __name__ == "__main__":
    main()

"""Package the manifest-only selector preflight for a private Kaggle CPU run."""

from __future__ import annotations

import json

from .build_kaggle_notebook import ROOT, cell


def build() -> dict:
    cells = [
        cell("markdown", "# ColorCheck selector preflight\n\nCPU-only manifest audit. "
             "Reserve new scene-disjoint train, validation, and final sets "
             "without downloading or viewing any photographs."),
        cell("code", "from pathlib import Path\n"
             "for directory in ('tools', 'tools/ml', 'tools/ml/tst100k'):\n"
             "    path = Path('/kaggle/working') / directory\n"
             "    path.mkdir(parents=True, exist_ok=True)\n"
             "    (path / '__init__.py').touch()\n"),
    ]
    for filename in ("data.py", "prepare_v4.py", "prepare_selector.py"):
        source = (ROOT / "tools/ml/tst100k" / filename).read_text()
        cells.append(cell("code", f"%%writefile /kaggle/working/tools/ml/tst100k/{filename}\n{source}"))
    cells.append(cell("code", "import subprocess, sys\n"
                      "subprocess.run([sys.executable, '-m', 'tools.ml.tst100k.prepare_selector'], "
                      "cwd='/kaggle/working', check=True)\n"))
    return {
        "cells": cells,
        "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}},
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def main() -> None:
    destination = ROOT / "kaggle/tst100k/selector-preflight/colorcheck-selector-preflight.ipynb"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(build(), indent=1, ensure_ascii=True) + "\n")
    print(destination)


if __name__ == "__main__":
    main()

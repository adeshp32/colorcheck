"""Generate the private, validation-gated v4 GPU experiment notebook."""

from __future__ import annotations

import json

from .build_kaggle_notebook import ROOT, cell
from .build_review_notebook import build as build_review


def build() -> dict:
    notebook = build_review()
    notebook["cells"][0] = cell(
        "markdown",
        "# ColorCheck v4 strong-edit experiment\n\n"
        "Warm-start the v3 checkpoint on its original training data. Train "
        "with the predeclared strong-edit loss, choose a checkpoint only on "
        "validation, and compare against frozen v3. This notebook does not "
        "read the sealed final holdout or deploy a model. See "
        "docs/reference-matcher-v4-protocol.md in the GitHub repository.",
    )
    notebook["cells"][-1] = cell(
        "code",
        "%%writefile /kaggle/working/tools/ml/tst100k/prepare_v4.py\n"
        + (ROOT / "tools/ml/tst100k/prepare_v4.py").read_text(),
    )
    notebook["cells"].append(
        cell(
            "code",
            "%%writefile /kaggle/working/tools/ml/tst100k/train_v4.py\n"
            + (ROOT / "tools/ml/tst100k/train_v4.py").read_text(),
        )
    )
    notebook["cells"].append(
        cell(
            "code",
            "import subprocess, sys\n"
            "subprocess.run([sys.executable, '-m', 'tools.ml.tst100k.train_v4'], "
            "cwd='/kaggle/working', check=True)\n",
        )
    )
    return notebook


def main() -> None:
    destination = ROOT / "kaggle/tst100k/v4-training/colorcheck-tst100k-v4.ipynb"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(build(), indent=1, ensure_ascii=True) + "\n")
    print(destination)


if __name__ == "__main__":
    main()

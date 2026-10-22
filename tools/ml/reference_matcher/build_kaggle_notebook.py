"""Build the private Kaggle notebook from the repository's tested Python modules.

Kaggle kernels accept one notebook as their executable source. Rather than keep
a second handwritten copy of the model in that notebook, this builder embeds the
current repository modules into clearly labeled ``%%writefile`` cells. Rebuilding
the notebook therefore preserves one source of truth while keeping every line of
training code visible in Kaggle's interface.
"""

from __future__ import annotations

import json
import hashlib
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
OUTPUT_DIRECTORY = REPOSITORY_ROOT / "kaggle" / "reference-matcher"
NOTEBOOK_PATH = OUTPUT_DIRECTORY / "colorcheck-reference-matcher.ipynb"

MODULES = (
    "dataset.py",
    "model.py",
    "losses.py",
    "evaluation.py",
    "train.py",
    "render_comparisons.py",
)


def markdown_cell(text: str) -> dict:
    """Create a notebook explanation cell."""
    return {
        "cell_type": "markdown",
        "id": hashlib.sha1(f"markdown:{text}".encode()).hexdigest()[:8],
        "metadata": {},
        "source": text.splitlines(True),
    }


def code_cell(code: str) -> dict:
    """Create an unexecuted Python cell."""
    return {
        "cell_type": "code",
        "id": hashlib.sha1(f"code:{code}".encode()).hexdigest()[:8],
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": code.splitlines(True),
    }


def module_cell(filename: str) -> dict:
    """Embed one tested repository module in a visible Kaggle writefile cell."""
    source_path = Path(__file__).with_name(filename)
    destination = f"/kaggle/working/tools/ml/reference_matcher/{filename}"
    return code_cell(f"%%writefile {destination}\n{source_path.read_text()}")


def build_notebook() -> dict:
    """Assemble the documented smoke test and optional full experiment."""
    cells = [
        markdown_cell(
            "# ColorCheck Reference Matcher Training\n\n"
            "**Goal:** learn a compact 3D LUT from an unedited target and an edited "
            "reference, transferring visual treatment without generating or replacing "
            "image content.\n\n"
            "This private notebook trains original PyTorch weights on MIT-Adobe FiveK. "
            "It first runs a deliberately small end-to-end experiment, then a measured "
            "5,000-pair pilot. A full-dataset run remains disabled until both stages, "
            "their metrics, and their checkpoints are reviewed."
        ),
        markdown_cell(
            "## 1. Verify the Kaggle environment\n\n"
            "The attached dataset is discovered beneath read-only `/kaggle/input`. "
            "Kaggle may add owner and dataset-slug wrapper directories. Checkpoints and "
            "metrics are written to `/kaggle/working`, which Kaggle preserves as notebook "
            "output when the run completes."
        ),
        code_cell(
            "from pathlib import Path\n"
            "import subprocess\n"
            "import sys\n"
            "import torch\n\n"
            "DATASET_ROOT = Path('/kaggle/input')\n"
            "OUTPUT_ROOT = Path('/kaggle/working/colorcheck-reference-matcher')\n"
            "PACKAGE_ROOT = Path('/kaggle/working/tools/ml/reference_matcher')\n"
            "PACKAGE_ROOT.mkdir(parents=True, exist_ok=True)\n"
            "(PACKAGE_ROOT.parent / '__init__.py').touch()\n"
            "(PACKAGE_ROOT / '__init__.py').touch()\n\n"
            "assert DATASET_ROOT.exists(), f'Dataset was not mounted: {DATASET_ROOT}'\n"
            "assert torch.cuda.is_available(), 'Enable a GPU accelerator in notebook settings.'\n"
            "print({\n"
            "    'python': sys.version.split()[0],\n"
            "    'torch': torch.__version__,\n"
            "    'gpu': torch.cuda.get_device_name(0),\n"
            "    'dataset_root': str(DATASET_ROOT),\n"
            "})\n"
        ),
        markdown_cell(
            "## 2. Materialize the tested training package\n\n"
            "Each following cell is generated from the corresponding repository file. "
            "The code remains visible for study and review rather than being hidden in a "
            "downloaded binary."
        ),
    ]

    for filename in MODULES:
        cells.append(markdown_cell(f"### `{filename}`\n"))
        cells.append(module_cell(filename))

    cells.extend(
        [
            markdown_cell(
                "## 3. Run the smoke experiment\n\n"
                "This run uses real FiveK images and performs genuine gradient updates, "
                "but its small sample count is only a systems test. It is not evidence of "
                "product-quality improvement."
            ),
            code_cell(
                "smoke_command = [\n"
                "    sys.executable, '-m', 'tools.ml.reference_matcher.train',\n"
                "    '--dataset-root', str(DATASET_ROOT),\n"
                "    '--output-dir', str(OUTPUT_ROOT / 'smoke'),\n"
                "    '--epochs', '1',\n"
                "    '--batch-size', '32',\n"
                "    '--image-size', '128',\n"
                "    '--evaluation-image-size', '256',\n"
                "    '--workers', '2',\n"
                "    '--mixed-precision', 'auto',\n"
                "    '--max-train-pairs', '256',\n"
                "    '--max-validation-pairs', '64',\n"
                "    '--max-test-pairs', '64',\n"
                "]\n"
                "subprocess.run(smoke_command, cwd='/kaggle/working', check=True)\n"
            ),
            markdown_cell(
                "## 4. Review the measurements\n\n"
                "The identity baseline asks whether training improved upon leaving the "
                "source untouched. The shuffled-reference control asks whether the model "
                "actually responds to its reference rather than applying one generic look."
            ),
            code_cell(
                "import json\n\n"
                "summary_path = OUTPUT_ROOT / 'smoke' / 'summary.json'\n"
                "history_path = OUTPUT_ROOT / 'smoke' / 'history.json'\n"
                "print(json.dumps(json.loads(summary_path.read_text()), indent=2))\n"
                "print(json.dumps(json.loads(history_path.read_text()), indent=2))\n"
            ),
            code_cell(
                "comparison_command = [\n"
                "    sys.executable, '-m', 'tools.ml.reference_matcher.render_comparisons',\n"
                "    '--dataset-root', str(DATASET_ROOT),\n"
                "    '--checkpoint', str(OUTPUT_ROOT / 'smoke' / 'best.pt'),\n"
                "    '--splits', str(OUTPUT_ROOT / 'smoke' / 'splits.json'),\n"
                "    '--output', str(OUTPUT_ROOT / 'smoke' / 'held-out-comparisons.jpg'),\n"
                "    '--samples', '10',\n"
                "]\n"
                "subprocess.run(comparison_command, cwd='/kaggle/working', check=True)\n"
            ),
            markdown_cell(
                "## 5. Measured medium pilot\n\n"
                "The validated smoke run measured the complete systems path. This pilot "
                "uses 5,000 training pairs over three "
                "epochs and 500-pair validation/test controls, remaining well inside one "
                "GPU session. The best checkpoint remains separate from the latest."
            ),
            code_cell(
                "RUN_MEDIUM_PILOT = True\n\n"
                "if RUN_MEDIUM_PILOT:\n"
                "    pilot_command = [\n"
                "        sys.executable, '-m', 'tools.ml.reference_matcher.train',\n"
                "        '--dataset-root', str(DATASET_ROOT),\n"
                "        '--output-dir', str(OUTPUT_ROOT / 'pilot'),\n"
                "        '--epochs', '3',\n"
                "        '--batch-size', '32',\n"
                "        '--image-size', '128',\n"
                "        '--evaluation-image-size', '256',\n"
                "        '--workers', '4',\n"
                "        '--mixed-precision', 'auto',\n"
                "        '--patience', '2',\n"
                "        '--max-train-pairs', '5000',\n"
                "        '--max-validation-pairs', '500',\n"
                "        '--max-test-pairs', '500',\n"
                "    ]\n"
                "    subprocess.run(pilot_command, cwd='/kaggle/working', check=True)\n"
                "else:\n"
                "    print('Medium pilot is disabled.')\n"
            ),
        ]
    )

    return {
        "cells": cells,
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {"name": "python", "version": "3"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def main() -> None:
    OUTPUT_DIRECTORY.mkdir(parents=True, exist_ok=True)
    NOTEBOOK_PATH.write_text(json.dumps(build_notebook(), indent=1) + "\n")
    print(f"Built {NOTEBOOK_PATH}")


if __name__ == "__main__":
    main()

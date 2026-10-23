"""Build the private Kaggle notebook from the repository's tested Python modules.

Kaggle kernels accept one notebook as their executable source. Rather than keep
a second handwritten copy of the model in that notebook, this builder embeds the
current repository modules into clearly labeled ``%%writefile`` cells. Rebuilding
the notebook therefore preserves one source of truth while keeping every line of
training code visible in Kaggle's interface.
"""

from __future__ import annotations

import hashlib
import json
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
            "12,000-pair conditioning pilot. V11 improved general color accuracy and "
            "validation conditioning but did not clear the strict held-out real-reference "
            "gate. V12 adds compact tonal-distribution descriptors, perceptual reference "
            "ranking, more real supervision, and broader training coverage while keeping "
            "the deployed model small and deterministic."
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
                "    '--ranking-weight', '2.0',\n"
                "    '--perceptual-ranking-weight', '0.03',\n"
                "    '--exact-lut-weight', '0.75',\n"
                "    '--same-style-weight', '0.5',\n"
                "    '--style-classification-weight', '0.1',\n"
                "    '--synthetic-probability', '0.35',\n"
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
                "uses 12,000 training pairs over five "
                "epochs and 500-pair validation/test controls. Its decisive gate is whether "
                "the correct real reference beats a shuffled reference by a statistically "
                "confident, practically meaningful CIEDE2000 margin. The best checkpoint "
                "remains separate from the latest."
            ),
            code_cell(
                "RUN_MEDIUM_PILOT = True\n\n"
                "if RUN_MEDIUM_PILOT:\n"
                "    pilot_command = [\n"
                "        sys.executable, '-m', 'tools.ml.reference_matcher.train',\n"
                "        '--dataset-root', str(DATASET_ROOT),\n"
                "        '--output-dir', str(OUTPUT_ROOT / 'pilot'),\n"
                "        '--epochs', '5',\n"
                "        '--batch-size', '32',\n"
                "        '--image-size', '128',\n"
                "        '--evaluation-image-size', '256',\n"
                "        '--workers', '4',\n"
                "        '--mixed-precision', 'auto',\n"
                "        '--patience', '3',\n"
                "        '--max-train-pairs', '12000',\n"
                "        '--max-validation-pairs', '500',\n"
                "        '--max-test-pairs', '500',\n"
                "        '--ranking-weight', '2.0',\n"
                "        '--perceptual-ranking-weight', '0.03',\n"
                "        '--exact-lut-weight', '0.75',\n"
                "        '--same-style-weight', '0.5',\n"
                "        '--style-classification-weight', '0.1',\n"
                "        '--synthetic-probability', '0.35',\n"
                "    ]\n"
                "    subprocess.run(pilot_command, cwd='/kaggle/working', check=True)\n"
                "else:\n"
                "    print('Medium pilot is disabled.')\n"
            ),
            markdown_cell(
                "## 6. Review the conditioning pilot\n\n"
                "This report is the decision surface, not a victory lap. Both real and "
                "synthetic held-out gates must pass under scene-clustered confidence "
                "intervals and predeclared practical-effect thresholds before export."
            ),
            code_cell(
                "if RUN_MEDIUM_PILOT:\n"
                "    pilot_summary = json.loads((OUTPUT_ROOT / 'pilot' / 'summary.json').read_text())\n"
                "    pilot_history = json.loads((OUTPUT_ROOT / 'pilot' / 'history.json').read_text())\n"
                "    print(json.dumps(pilot_summary, indent=2))\n"
                "    print(json.dumps(pilot_history, indent=2))\n"
                "    pilot_comparison_command = [\n"
                "        sys.executable, '-m', 'tools.ml.reference_matcher.render_comparisons',\n"
                "        '--dataset-root', str(DATASET_ROOT),\n"
                "        '--checkpoint', str(OUTPUT_ROOT / 'pilot' / 'best.pt'),\n"
                "        '--splits', str(OUTPUT_ROOT / 'pilot' / 'splits.json'),\n"
                "        '--output', str(OUTPUT_ROOT / 'pilot' / 'held-out-comparisons.jpg'),\n"
                "        '--samples', '12',\n"
                "    ]\n"
                "    subprocess.run(pilot_comparison_command, cwd='/kaggle/working', check=True)\n"
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

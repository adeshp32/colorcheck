# TST100K Research Pilot

`data.py` selects scene-disjoint triplets from a pinned TST100K manifest and
downloads only the selected files to Kaggle scratch. `train.py` updates an
existing compact LUT predictor using direct source/reference/ground-truth
supervision. It records validation every epoch and evaluates the untouched test
split once after selecting the checkpoint.

The three test questions are whether the model beats an unchanged photo, beats
ColorCheck's existing statistics matcher, and improves when given the correct
reference rather than a mismatched one. A positive point estimate alone does not
pass: the 95% photo-level bootstrap interval must stay above zero. Model output
remains a research artifact until browser parity, quality review, performance,
and these evidence gates are checked.

Run `python -m tools.ml.tst100k.build_kaggle_notebook` to regenerate the notebook
from the documented modules. Push `kaggle/tst100k/` with the Kaggle CLI. The run
needs a GPU and internet, stages images only in `/kaggle/temp`, and writes only
the manifest, history, summary, and best checkpoint to `/kaggle/working`.

TST100K combines third-party research datasets and is restricted to
non-commercial academic research by its [dataset card](https://huggingface.co/datasets/ToneStyle/TST100K).
Its terms do not replace those of the underlying sources. No image or checkpoint
is distributed from this repository.

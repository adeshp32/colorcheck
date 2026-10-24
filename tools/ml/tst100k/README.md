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
from the documented modules. Push the selected notebook directory with the Kaggle CLI. The run
needs a GPU and internet, stages images only in `/kaggle/temp`, and writes only
the manifest, history, summary, and best checkpoint to `/kaggle/working`.

## First pilot (October 23, 2026)

The first private Kaggle run used 512 training, 96 validation, and 96 test
triplets. The selected epoch was 4. On the scene-disjoint test set, mean
Delta E 2000 was 9.97 for the model, 10.78 for unchanged images, and 10.89
for the current statistics matcher. The paired gain over the unchanged image
was 0.82 (95% bootstrap interval 0.57 to 1.06). The correct-reference gain
over a wrong reference was 0.68 (0.42 to 0.96). The paired gain over the
statistics matcher was 0.92, but its interval crossed zero (-0.22 to 2.10).
**That last gate failed**, so no checkpoint was promoted to the website.

The expanded-validation notebook uses a fresh seed, 1024/160/320 triplets,
and eight epochs. The first larger attempt stopped at an upstream HTTP 429
while fetching thousands of individual images; the revised fetcher spaces
requests, shares the host's retry delay across workers, and reports progress.
It also reports SSIM, edge error, and clipping so that
reduced color error cannot silently mask a structural or tonal regression.

`python -m tools.ml.tst100k.build_review_notebook` generates a separate
CPU-only Kaggle audit. It mounts the successful training run's output, scores
every held-out test image, and produces side-by-side sheets for weak, fixed-
random, and strong cases. The sheets are review artifacts, not training data.

TST100K combines third-party research datasets and is restricted to
non-commercial academic research by its [dataset card](https://huggingface.co/datasets/ToneStyle/TST100K).
Its terms do not replace those of the underlying sources. No image or checkpoint
is distributed from this repository.

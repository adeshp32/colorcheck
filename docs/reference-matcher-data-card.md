# Reference Matcher Data Card

## Source

Experiments use the MIT-Adobe FiveK collection as distributed through the
attached Kaggle dataset. Each of 5,000 scenes has one source photograph and five
independent expert edits. Dataset files are mounted read-only in Kaggle or read
from the user's removable archive; no photographs are stored in this repository.

Access to the photographs remains governed by the source dataset's terms. This
pipeline is configured for research and education. Any later commercial dataset
use or redistribution requires a fresh license review rather than an assumption
based on this experiment.

## Training Record

The loader accepts only scenes with all six required variants: raw plus experts
A through E. A seeded SHA-256 rank assigns complete scene identities to:

- 4,000 training scenes;
- 500 validation scenes; and
- 500 final test scenes.

All versions of one scene stay in one partition. The splits.json record stores
every filename, seed, and split method so an experiment can be reproduced and
audited.

## Pair Construction

For real supervision, the target is a raw scene, the expected output is one
expert's edit of that scene, and the reference is a different scene edited by the
same expert. During training, a second reference uses a third scene edited by the
same expert. Agreement between their predicted LUTs discourages the model from
mistaking scene content for treatment. Validation, testing, and product inference
still consume one reference.

For exact synthetic supervision, one deterministic bounded recipe transforms
two unrelated raw scenes. One transformed scene is the reference and the other
is the expected target. Its style identifier is unique to the recipe, allowing a
known-wrong reference to be selected for pairwise ranking. Training also applies
the same recipe to the alternate reference scene, giving an exact same-style
consistency example.

## Transform Boundaries

Synthetic recipes currently cover exposure, contrast, gamma, RGB channel gains,
saturation, shadows, highlights, and black level. They are deterministic from a
recorded seed and stay in display RGB between zero and one. They do not synthesize
objects, faces, text, geometry, or scene content.

## Leakage Controls

- Split assignment happens before target/reference pairing.
- References are selected only from scenes in the same current partition.
- Validation and test transformations are deterministic.
- Checkpoint selection uses validation only.
- The test split runs once after selecting the best checkpoint.
- Quantization calibration uses validation, never test.

## Limitations

Expert edits are subjective and correlated by editor. The collection may not
represent all cameras, demographics, locations, genres, or accessibility needs.
Exact synthetic pairs test declared global controls but cannot prove subjective
quality. Results must therefore be reported separately for real and synthetic
supervision, with visual review and failure cases retained.

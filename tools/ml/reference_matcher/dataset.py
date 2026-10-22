"""Load Adobe FiveK without leaking the same scene across data splits.

The training code supports a ZIP archive for local experiments and an extracted
directory for Kaggle. Both layouts contain ``raw`` originals and the five expert
edits in directories ``a`` through ``e``.
"""

from __future__ import annotations

import hashlib
import io
import json
import random
import zipfile
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import torch
from PIL import Image
from torch.utils.data import Dataset
from torchvision.transforms import functional as TF

# Adobe FiveK provides five independent professional edits for each photograph.
EXPERTS = ("a", "b", "c", "d", "e")
REQUIRED_DIRECTORIES = ("raw", *EXPERTS)


def apply_synthetic_style(image: torch.Tensor, seed: int) -> torch.Tensor:
    """Apply one deterministic, photograph-safe global editing recipe.

    The same seed gives two unrelated raw scenes the same treatment. Using one
    transformed scene as the reference and the other as the expected target
    creates exact supervision for arbitrary reference matching. This complements
    FiveK's real expert edits, whose intent is valuable but not parameterized.
    """
    generator = torch.Generator().manual_seed(seed)
    values = torch.rand(10, generator=generator, dtype=image.dtype)
    exposure = 2 ** float(values[0] * 2 - 1)
    contrast = float(0.72 + values[1] * 0.66)
    gamma = float(0.82 + values[2] * 0.38)
    saturation = float(0.65 + values[3] * 0.75)
    channel_gains = 0.86 + values[4:7, None, None] * 0.28
    shadow_lift = float(values[7] * 0.20 - 0.10)
    highlight_lift = float(values[8] * 0.20 - 0.10)
    black_lift = float(values[9] * 0.06 - 0.03)

    styled = image * channel_gains * exposure
    luminance = (
        styled * styled.new_tensor([0.2126, 0.7152, 0.0722])[:, None, None]
    ).sum(0, keepdim=True)
    styled = luminance + (styled - luminance) * saturation
    styled = (styled - 0.5) * contrast + 0.5
    lift = (
        shadow_lift * (1 - luminance.clamp(0, 1)).square()
        + highlight_lift * luminance.clamp(0, 1).square()
        + black_lift * (1 - luminance.clamp(0, 1)).pow(4)
    )
    styled = (styled + lift).clamp(0, 1).pow(gamma)
    return styled.clamp(0, 1)


def synthetic_style_lut(size: int, seed: int) -> torch.Tensor:
    """Materialize the exact 3D LUT implied by one synthetic editing recipe.

    Supervising the complete color cube teaches colors absent from a particular
    training crop and matches the artifact deployed in the browser. Axis order
    is channel, blue, green, red, the same contract used by apply_lut.
    """
    values = torch.linspace(0, 1, size)
    blue, green, red = torch.meshgrid(values, values, values, indexing="ij")
    identity = torch.stack((red, green, blue))
    styled = apply_synthetic_style(identity.reshape(3, size * size, size), seed)
    return styled.reshape(3, size, size, size)


@dataclass(frozen=True)
class SplitManifest:
    """Scene names assigned to training, validation, and final testing.

    Splitting by scene is essential: all six versions of one photograph must
    remain together, or evaluation would contain images already seen in training.
    """

    train: tuple[str, ...]
    validation: tuple[str, ...]
    test: tuple[str, ...]

    def save(self, path: Path) -> None:
        """Save the exact split so later runs evaluate the same photographs."""
        payload = {
            "version": 1,
            "method": "sha256(seed + scene filename), sorted by digest",
            "train": list(self.train),
            "validation": list(self.validation),
            "test": list(self.test),
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2) + "\n")


def _contains_fivek_folders(path: Path) -> bool:
    """Return whether a directory directly contains raw and all expert folders."""
    return path.is_dir() and all(
        (path / name).is_dir() for name in REQUIRED_DIRECTORIES
    )


def find_dataset_root(path: Path) -> Path:
    """Find the FiveK folder inside a Kaggle dataset mount.

    Kaggle mounts datasets under a slug such as
    ``/kaggle/input/adobe-fivek``. This function also tolerates one or more
    wrapper directories so the notebook does not depend on an accidental path.
    """
    path = Path(path)
    if _contains_fivek_folders(path):
        return path

    candidates: list[Path] = []
    if path.is_dir():
        for raw_directory in path.rglob("raw"):
            if _contains_fivek_folders(raw_directory.parent):
                candidates.append(raw_directory.parent.resolve())

    unique = sorted(set(candidates))
    if len(unique) == 1:
        return unique[0]
    if not unique:
        raise ValueError(
            f"Could not find raw/a/b/c/d/e folders beneath dataset path: {path}"
        )
    raise ValueError(
        "More than one FiveK layout was found. Pass the exact directory with "
        f"--dataset-root. Candidates: {', '.join(map(str, unique))}"
    )


def inspect_dataset(dataset_path: Path) -> tuple[str, ...]:
    """Return scene filenames that have an original and all five expert edits."""
    dataset_path = Path(dataset_path)
    if dataset_path.is_file():
        if not zipfile.is_zipfile(dataset_path):
            raise ValueError(f"Dataset file is not a readable ZIP: {dataset_path}")
        with zipfile.ZipFile(dataset_path) as bundle:
            members = {
                name.replace("\\", "/")
                for name in bundle.namelist()
                if not name.endswith("/")
            }
        source_names = sorted(
            name.removeprefix("raw/") for name in members if name.startswith("raw/")
        )
        complete = [
            name
            for name in source_names
            if all(f"{expert}/{name}" in members for expert in EXPERTS)
        ]
    else:
        root = find_dataset_root(dataset_path)
        source_names = sorted(
            str(file.relative_to(root / "raw")).replace("\\", "/")
            for file in (root / "raw").rglob("*")
            if file.is_file()
        )
        complete = [
            name
            for name in source_names
            if all((root / expert / name).is_file() for expert in EXPERTS)
        ]

    missing_count = len(source_names) - len(complete)
    if missing_count:
        raise ValueError(
            f"Dataset has {missing_count} source scenes missing expert edits"
        )
    if not complete:
        raise ValueError("No complete raw/A-E scenes found in the dataset")
    return tuple(complete)


def inspect_archive(archive: Path) -> tuple[str, ...]:
    """Keep the original public function name for older local commands."""
    return inspect_dataset(archive)


def create_splits(
    scenes: tuple[str, ...],
    seed: int = 42,
    validation_size: int = 500,
    test_size: int = 500,
) -> SplitManifest:
    """Create deterministic, scene-level train/validation/test partitions."""
    if validation_size + test_size >= len(scenes):
        raise ValueError("Validation and test splits leave no training scenes")

    # Hash ranking makes the split independent of filesystem ordering while the
    # seed lets a future experiment deliberately choose a different partition.
    ranked = sorted(
        scenes,
        key=lambda name: hashlib.sha256(f"{seed}:{name}".encode()).digest(),
    )
    test = tuple(ranked[:test_size])
    validation = tuple(ranked[test_size : test_size + validation_size])
    train = tuple(ranked[test_size + validation_size :])
    return SplitManifest(train=train, validation=validation, test=test)


class FiveKReferenceDataset(Dataset):
    """Produce supervised examples for reference-conditioned color matching.

    Every sample contains:

    * ``source``: an unedited photograph that ColorCheck must transform;
    * ``reference``: a different scene edited by one particular expert; and
    * ``expected``: that expert's edit of the source photograph.

    Using a different reference scene prevents the network from copying scene
    content and instead asks it to infer the expert's visual treatment.
    """

    def __init__(
        self,
        dataset_path: Path,
        scenes: tuple[str, ...],
        image_size: int = 256,
        training: bool = False,
        seed: int = 42,
        synthetic_probability: float = 0.0,
        lut_size: int = 33,
        include_lut_supervision: bool = False,
        include_alternate_reference: bool = False,
    ) -> None:
        if len(scenes) < 2:
            raise ValueError("At least two scenes are required for reference pairing")
        self.dataset_path = Path(dataset_path)
        self.dataset_root = (
            None
            if self.dataset_path.is_file()
            else find_dataset_root(self.dataset_path)
        )
        self.scenes = scenes
        self.image_size = image_size
        self.training = training
        self.seed = seed
        if not 0 <= synthetic_probability <= 1:
            raise ValueError("Synthetic probability must be between zero and one")
        self.synthetic_probability = synthetic_probability
        self.lut_size = lut_size
        self.include_lut_supervision = include_lut_supervision
        self.include_alternate_reference = include_alternate_reference
        # ZIP handles cannot be shared safely by DataLoader worker processes.
        self._bundle: zipfile.ZipFile | None = None

    def __getstate__(self):
        """Remove an open ZIP handle before DataLoader copies this object."""
        state = self.__dict__.copy()
        state["_bundle"] = None
        return state

    def __len__(self) -> int:
        """Expose every scene once for each of the five expert styles."""
        return len(self.scenes) * len(EXPERTS)

    @property
    def bundle(self) -> zipfile.ZipFile:
        """Open the archive lazily inside the process that will read it."""
        if self._bundle is None:
            self._bundle = zipfile.ZipFile(self.dataset_path)
        return self._bundle

    def _prepare_image(self, image: Image.Image) -> torch.Tensor:
        """Convert one image into the consistent tensor format used by PyTorch."""
        image = image.convert("RGB")
        image = TF.resize(
            image,
            [self.image_size, self.image_size],
            interpolation=TF.InterpolationMode.BICUBIC,
            antialias=True,
        )
        # PIL uses height-width-channel integers in [0, 255]. ``to_tensor``
        # returns channel-height-width float values normalized to [0, 1].
        return TF.to_tensor(image)

    @lru_cache(maxsize=384)
    def _read(self, member: str) -> torch.Tensor:
        """Decode and cache a bounded working-size image inside each loader worker.

        FiveK reuses every raw scene across five expert samples and may reuse an
        expert image as another sample's reference. Caching the resized tensor
        avoids repeated JPEG decoding while keeping memory bounded. Returned
        tensors are never modified in place.
        """
        if self.dataset_root is None:
            with self.bundle.open(member) as stream:
                with Image.open(io.BytesIO(stream.read())) as image:
                    return self._prepare_image(image)
        with Image.open(self.dataset_root / member) as image:
            return self._prepare_image(image)

    def __getitem__(self, index: int):
        """Map a flat DataLoader index to a scene, expert, and reference scene."""
        scene_index, expert_index = divmod(index, len(EXPERTS))
        scene = self.scenes[scene_index]
        expert = EXPERTS[expert_index]

        # A stable hash selects a repeatable reference that can never equal the
        # source scene. Repeatability is especially important for validation.
        offset_seed = int.from_bytes(
            hashlib.sha256(f"{self.seed}:{scene}:{expert}".encode()).digest()[:8], "big"
        )
        reference_index = (
            scene_index + 1 + offset_seed % (len(self.scenes) - 1)
        ) % len(self.scenes)
        reference_scene = self.scenes[reference_index]

        # Training may request a second, same-style reference from another scene.
        # Agreement across two unrelated photographs teaches the model to retain
        # the edit treatment while discarding reference-scene content. Validation
        # and browser inference still require only one reference image.
        alternate_reference_scene = None
        if self.include_alternate_reference:
            alternate_seed = int.from_bytes(
                hashlib.sha256(
                    f"alternate:{self.seed}:{scene}:{expert}".encode()
                ).digest()[:8],
                "big",
            )
            alternate_index = (
                scene_index + 1 + alternate_seed % (len(self.scenes) - 1)
            ) % len(self.scenes)
            if len(self.scenes) > 2:
                while alternate_index in (scene_index, reference_index):
                    alternate_index = (alternate_index + 1) % len(self.scenes)
            alternate_reference_scene = self.scenes[alternate_index]

        source = self._read(f"raw/{scene}")
        # Deterministically mix exact synthetic supervision with real edits.
        # Five expert-indexed samples per scene provide five distinct seeds.
        style_seed = int.from_bytes(
            hashlib.sha256(f"style:{self.seed}:{scene}:{expert}".encode()).digest()[:8],
            "big",
        )
        synthetic = (style_seed % 10_000) / 10_000 < self.synthetic_probability
        if synthetic:
            reference = apply_synthetic_style(
                self._read(f"raw/{reference_scene}"), style_seed
            )
            expected = apply_synthetic_style(source, style_seed)
            if alternate_reference_scene is not None:
                alternate_reference = apply_synthetic_style(
                    self._read(f"raw/{alternate_reference_scene}"), style_seed
                )
        else:
            reference = self._read(f"{expert}/{reference_scene}")
            expected = self._read(f"{expert}/{scene}")
            if alternate_reference_scene is not None:
                alternate_reference = self._read(
                    f"{expert}/{alternate_reference_scene}"
                )

        # Flip source and expected together. This adds compositional variety
        # without changing the color relationship that the network must learn.
        if self.training and random.random() < 0.5:
            source = source.flip(-1)
            expected = expected.flip(-1)

        sample = {
            "source": source,
            "reference": reference,
            "expected": expected,
            "scene": scene,
            "reference_scene": reference_scene,
            "expert": expert_index,
            "supervision": "synthetic" if synthetic else "fivekExpert",
            # A style identifier supports the training-time wrong-reference
            # control. Synthetic recipes are unique; real edits share an expert.
            "style_id": f"synthetic:{style_seed}" if synthetic else f"expert:{expert}",
        }
        if self.include_lut_supervision:
            sample["expected_lut"] = (
                synthetic_style_lut(self.lut_size, style_seed)
                if synthetic
                else torch.zeros(3, self.lut_size, self.lut_size, self.lut_size)
            )
            sample["has_exact_lut"] = synthetic
        if alternate_reference_scene is not None:
            sample["alternate_reference"] = alternate_reference
            sample["alternate_reference_scene"] = alternate_reference_scene
        return sample

import tempfile
import unittest
import zipfile
from pathlib import Path

import torch
from PIL import Image

from tools.ml.reference_matcher.dataset import (
    EXPERTS,
    FiveKReferenceDataset,
    apply_synthetic_style,
    create_splits,
    inspect_dataset,
    synthetic_style_lut,
)
from tools.ml.reference_matcher.evaluation import (
    MINIMUM_PRACTICAL_EFFECTS,
    MetricStore,
    ciede2000,
    deployment_evidence_gates,
    metric_samples,
    mismatch_references,
    paired_improvement,
    statistics_match,
)
from tools.ml.reference_matcher.export_onnx import (
    browser_probe_inputs,
    deployment_decision,
)
from tools.ml.reference_matcher.losses import (
    exact_lut_supervision_loss,
    expert_style_classification_loss,
    reference_ranking_loss,
    same_style_consistency_loss,
)
from tools.ml.reference_matcher.model import (
    ExpertStyleClassifier,
    ReferenceLutModel,
    apply_lut,
    identity_lut,
    initial_lut_bases,
)
from tools.ml.reference_matcher.render_comparisons import sample_indices
from tools.ml.reference_matcher.train import checkpoint_selection_score


class ReferenceMatcherTests(unittest.TestCase):
    def test_browser_probe_inputs_are_repeatable_bounded_and_distinct(self):
        first = browser_probe_inputs(16)
        second = browser_probe_inputs(16)
        self.assertEqual(first["source"].shape, (1, 3, 16, 16))
        self.assertTrue((first["source"] >= 0).all() and (first["source"] <= 1).all())
        self.assertFalse((first["source"] == first["reference"]).all())
        self.assertTrue((first["source"] == second["source"]).all())

    def test_exact_synthetic_lut_matches_the_recipe_on_grid_colors(self):
        lut = synthetic_style_lut(17, 123).unsqueeze(0)
        grid = identity_lut(17).reshape(1, 3, 17 * 17, 17)
        expected = apply_synthetic_style(grid[0], 123).unsqueeze(0)
        torch.testing.assert_close(apply_lut(grid, lut), expected, atol=2e-6, rtol=0)

    def test_exact_lut_loss_ignores_real_pairs_without_transform_labels(self):
        predicted = torch.ones(2, 3, 3, 3, 3)
        expected = torch.zeros_like(predicted)
        available = torch.tensor([True, False])
        self.assertEqual(
            exact_lut_supervision_loss(predicted, expected, available).item(), 1.0
        )
        self.assertEqual(
            exact_lut_supervision_loss(predicted, expected, torch.zeros(2)).item(), 0.0
        )

    def test_initial_lut_bases_are_distinct_but_average_near_neutral(self):
        bases = initial_lut_bases(17, 8)
        neutral = identity_lut(17)
        self.assertGreater((bases[0] - bases[1]).abs().mean().item(), 0.02)
        self.assertLess((bases.mean(0) - neutral).abs().mean().item(), 0.015)
        self.assertTrue(torch.all((bases >= 0) & (bases <= 1)))

    def test_visual_review_sampling_is_reproducible_and_spans_dataset(self):
        self.assertEqual(sample_indices(101, 5), [0, 25, 50, 75, 100])
        self.assertEqual(sample_indices(3, 10), [0, 1, 2])
        with self.assertRaises(ValueError):
            sample_indices(10, 0)

    def test_reference_ranking_rewards_the_correct_style(self):
        expected = torch.zeros(2, 3, 4, 4)
        correct = torch.zeros_like(expected)
        wrong = torch.full_like(expected, 0.2)
        self.assertEqual(reference_ranking_loss(correct, wrong, expected).item(), 0.0)
        self.assertAlmostEqual(
            reference_ranking_loss(correct, correct, expected).item(), 0.01, places=6
        )

    def test_same_style_consistency_and_auxiliary_classifier_are_training_only(self):
        first = torch.zeros(2, 3, 3, 3, 3)
        second = first.clone()
        self.assertEqual(same_style_consistency_loss(first, second).item(), 0.0)
        self.assertGreater(
            same_style_consistency_loss(first, torch.ones_like(first)).item(), 0.1
        )

        classifier = ExpertStyleClassifier(feature_size=96, expert_count=len(EXPERTS))
        logits = classifier(torch.rand(4, 96))
        self.assertEqual(logits.shape, (4, len(EXPERTS)))
        labels = torch.tensor([0, 1, 2, 3])
        self.assertGreater(
            expert_style_classification_loss(
                logits, labels, torch.tensor([True, True, False, False])
            ).item(),
            0,
        )
        self.assertEqual(
            expert_style_classification_loss(
                logits, labels, torch.zeros(4, dtype=torch.bool)
            ).item(),
            0,
        )

    def test_deployment_requires_matching_quality_and_quantization_evidence(self):
        checkpoint = {"epoch": 4}
        summary = {"bestEpoch": 4, "allDeploymentEvidenceGatesPass": True}
        self.assertTrue(
            deployment_decision(checkpoint, summary, True)["deploymentReady"]
        )
        self.assertFalse(
            deployment_decision(checkpoint, summary, False)["deploymentReady"]
        )
        summary["bestEpoch"] = 3
        self.assertFalse(
            deployment_decision(checkpoint, summary, True)["deploymentReady"]
        )

    def test_checkpoint_selection_balances_real_and_synthetic_validation(self):
        real = {"delta_e76": 8.0}
        synthetic = {"delta_e76": 12.0}
        self.assertEqual(checkpoint_selection_score(real, synthetic), 10.0)
        shuffled = {"delta_e76": 8.5}
        self.assertEqual(checkpoint_selection_score(real, synthetic, shuffled), 9.5)
        shuffled["delta_e76"] = 7.5
        self.assertEqual(checkpoint_selection_score(real, synthetic, shuffled), 10.5)

    def test_scene_splits_are_deterministic_exhaustive_and_disjoint(self):
        scenes = tuple(f"scene-{index:04d}.jpg" for index in range(5000))
        first = create_splits(scenes, seed=42)
        second = create_splits(tuple(reversed(scenes)), seed=42)
        self.assertEqual(first, second)
        self.assertEqual(
            (len(first.train), len(first.validation), len(first.test)),
            (4000, 500, 500),
        )
        partitions = [set(first.train), set(first.validation), set(first.test)]
        self.assertEqual(set.union(*partitions), set(scenes))
        self.assertFalse(partitions[0] & partitions[1])
        self.assertFalse(partitions[0] & partitions[2])
        self.assertFalse(partitions[1] & partitions[2])

    def test_identity_lut_preserves_pixels(self):
        image = torch.rand(2, 3, 13, 17)
        lut = identity_lut(17).unsqueeze(0).repeat(2, 1, 1, 1, 1)
        torch.testing.assert_close(apply_lut(image, lut), image, atol=2e-6, rtol=0)

    def test_model_shapes_and_convex_coefficients(self):
        model = ReferenceLutModel(basis_count=3, lut_size=17).eval()
        image = torch.rand(2, 3, 64, 64)
        with torch.no_grad():
            lut, coefficients = model(image, image.flip(-1))
        self.assertEqual(lut.shape, (2, 3, 17, 17, 17))
        self.assertEqual(coefficients.shape, (2, 3))
        torch.testing.assert_close(coefficients.sum(1), torch.ones(2))

    def test_lut_accepts_mixed_precision_interpolation_weights(self):
        """CUDA autocast LUTs must work with the loader's float32 image tensors."""
        image = torch.rand(1, 3, 8, 8)
        lut = identity_lut(17).unsqueeze(0).to(torch.bfloat16)
        output = apply_lut(image, lut)
        self.assertEqual(output.dtype, torch.bfloat16)
        torch.testing.assert_close(output.float(), image, atol=0.01, rtol=0)

    def test_ciede2000_matches_published_reference_pair(self):
        """The first Sharma test pair has a known CIEDE2000 value of 2.0425."""
        first = torch.tensor([50.0, 2.6772, -79.7751]).reshape(1, 3, 1, 1)
        second = torch.tensor([50.0, 0.0, -82.7485]).reshape(1, 3, 1, 1)
        self.assertAlmostEqual(ciede2000(first, second).item(), 2.0425, places=4)
        self.assertLess(ciede2000(first, first).item(), 1e-4)

    def test_quality_metrics_reward_an_identical_image(self):
        image = torch.rand(2, 3, 32, 32)
        metrics = metric_samples(image, image)
        torch.testing.assert_close(metrics["mae"], torch.zeros(2))
        torch.testing.assert_close(metrics["ssim"], torch.ones(2), atol=1e-5, rtol=0)
        self.assertTrue(torch.all(metrics["psnrDb"] >= 99))

    def test_metric_confidence_intervals_resample_source_scenes(self):
        """Repeated expert edits count as observations, not independent scenes."""
        model = MetricStore()
        baseline = MetricStore()
        scenes = ["scene-a", "scene-a", "scene-b", "scene-b"]
        experts = torch.tensor([0, 1, 0, 1])
        model.add({"deltaE2000": torch.tensor([1.0, 3.0, 5.0, 7.0])}, experts, scenes)
        baseline.add(
            {"deltaE2000": torch.tensor([2.0, 4.0, 8.0, 10.0])}, experts, scenes
        )

        summary = model.summary()["overall"]["deltaE2000"]
        self.assertEqual(summary["sceneCount"], 2)
        self.assertEqual(summary["observationCount"], 4)
        self.assertEqual(summary["mean"], 4.0)
        gain = paired_improvement(model, baseline)["deltaE2000"]
        self.assertEqual(gain["sceneCount"], 2)
        self.assertEqual(gain["observationCount"], 4)
        self.assertEqual(gain["mean"], 2.0)

    def test_deployment_rejects_statistically_positive_but_trivial_effects(self):
        """A tiny positive CI is evidence of direction, not useful product impact."""

        def result(mean, lower=0.001):
            return {"mean": mean, "ci95Lower": lower, "ci95Upper": mean + 0.1}

        identity = {
            "deltaE2000": result(MINIMUM_PRACTICAL_EFFECTS["identityDeltaE2000"]),
            "ssim": result(MINIMUM_PRACTICAL_EFFECTS["identitySsim"]),
            "clippingPercent": result(0.0, lower=0.0),
        }
        statistics = {
            "deltaE2000": result(MINIMUM_PRACTICAL_EFFECTS["statisticsDeltaE2000"])
        }
        correct_reference = {
            "deltaE2000": result(
                MINIMUM_PRACTICAL_EFFECTS["correctReferenceDeltaE2000"]
            )
        }
        mixture = {"meanBasisWeights": [0.5, 0.5], "dominantBasisFraction": 0.6}
        passing = deployment_evidence_gates(
            identity,
            statistics,
            correct_reference,
            MINIMUM_PRACTICAL_EFFECTS["referenceSensitivityMae"],
            mixture,
        )
        self.assertTrue(all(passing.values()))

        identity["deltaE2000"] = result(
            MINIMUM_PRACTICAL_EFFECTS["identityDeltaE2000"] - 1e-6
        )
        failing = deployment_evidence_gates(
            identity,
            statistics,
            correct_reference,
            MINIMUM_PRACTICAL_EFFECTS["referenceSensitivityMae"],
            mixture,
        )
        self.assertFalse(failing["beatsIdentityDeltaE2000"])

    def test_statistics_match_reaches_reference_channel_statistics(self):
        source = torch.rand(2, 3, 32, 32) * 0.2 + 0.2
        reference = torch.rand(2, 3, 32, 32) * 0.15 + 0.45
        matched = statistics_match(source, reference)
        torch.testing.assert_close(
            matched.mean((2, 3)), reference.mean((2, 3)), atol=2e-5, rtol=0
        )

    def test_synthetic_style_is_repeatable_and_changes_the_image(self):
        image = torch.rand(3, 24, 24)
        first = apply_synthetic_style(image, 1234)
        second = apply_synthetic_style(image, 1234)
        other = apply_synthetic_style(image, 5678)
        torch.testing.assert_close(first, second)
        self.assertGreater((first - other).abs().mean().item(), 0.01)
        self.assertTrue(torch.all((first >= 0) & (first <= 1)))

    def test_wrong_reference_control_always_changes_style_when_possible(self):
        reference = torch.arange(12).reshape(4, 3, 1, 1).float()
        experts = torch.tensor([0, 1, 1, 2])
        mismatched, indices = mismatch_references(reference, experts)
        self.assertTrue(torch.all(experts[indices] != experts))
        torch.testing.assert_close(mismatched, reference[indices])

    def test_wrong_reference_control_supports_string_style_ids(self):
        reference = torch.arange(12).reshape(4, 3, 1, 1).float()
        styles = ["synthetic:1", "synthetic:2", "expert:a", "expert:a"]
        mismatched, indices = mismatch_references(reference, styles)
        self.assertTrue(
            all(styles[index] != styles[indices[index]] for index in range(4))
        )
        torch.testing.assert_close(mismatched, reference[indices])

    def test_directory_and_zip_load_the_same_fivek_layout(self):
        """Both local and Kaggle storage paths must produce identical tensors."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "fivek"
            scenes = tuple(f"scene-{index}.jpg" for index in range(1, 7))
            for directory in ("raw", *EXPERTS):
                (root / directory).mkdir(parents=True)
                for index, scene in enumerate(scenes):
                    color = (20 + index * 10, 40 + index * 10, 60 + index * 10)
                    Image.new("RGB", (12, 8), color).save(root / directory / scene)

            self.assertEqual(inspect_dataset(root), scenes)
            split = create_splits(scenes, validation_size=1, test_size=1)
            directory_dataset = FiveKReferenceDataset(root, split.train, image_size=16)

            archive = Path(temporary_directory) / "fivek.zip"
            with zipfile.ZipFile(archive, "w") as bundle:
                for file in root.rglob("*.jpg"):
                    bundle.write(file, file.relative_to(root))
            self.assertEqual(inspect_dataset(archive), scenes)
            archive_dataset = FiveKReferenceDataset(archive, split.train, image_size=16)

            directory_sample = directory_dataset[0]
            archive_sample = archive_dataset[0]
            self.assertNotEqual(
                directory_sample["scene"], directory_sample["reference_scene"]
            )
            torch.testing.assert_close(
                directory_sample["source"], archive_sample["source"]
            )
            self.assertNotIn("expected_lut", directory_sample)
            torch.testing.assert_close(
                directory_sample["reference"], archive_sample["reference"]
            )
            torch.testing.assert_close(
                directory_sample["expected"], archive_sample["expected"]
            )
            supervised_dataset = FiveKReferenceDataset(
                root,
                split.train,
                image_size=16,
                synthetic_probability=1.0,
                include_lut_supervision=True,
                include_alternate_reference=True,
            )
            supervised_sample = supervised_dataset[0]
            self.assertEqual(supervised_sample["expected_lut"].shape, (3, 33, 33, 33))
            self.assertTrue(supervised_sample["has_exact_lut"])
            self.assertNotEqual(
                supervised_sample["scene"],
                supervised_sample["alternate_reference_scene"],
            )
            self.assertNotEqual(
                supervised_sample["reference_scene"],
                supervised_sample["alternate_reference_scene"],
            )
            self.assertEqual(
                supervised_sample["alternate_reference"].shape, (3, 16, 16)
            )


if __name__ == "__main__":
    unittest.main()

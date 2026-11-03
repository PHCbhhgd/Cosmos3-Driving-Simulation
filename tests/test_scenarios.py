"""Check geometric stress cases and temporal alignment without model weights."""

import json
from pathlib import Path
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from prepare_business_scene import centerline, pose, scenario_state  # noqa: E402
from prepare_temporal_requests import chunk_ranges  # noqa: E402
from evaluate_actor_support import box_range_bounds, near_box  # noqa: E402


class ScenarioTests(unittest.TestCase):
    def test_weather_and_conflict_share_exact_turn_geometry(self):
        cases = json.loads((ROOT / "configs/robustness-cases.json").read_text())["cases"]
        selected = [
            c
            for c in cases
            if c["id"] in ["clear_turn", "rain_turn", "snow_turn", "contradictory_turn"]
        ]
        self.assertEqual(len(selected), 4)
        states = [scenario_state(c["geometry"], np.arange(64) / 30) for c in selected]
        for state in states[1:]:
            np.testing.assert_array_equal(states[0][0], state[0])
            self.assertEqual(states[0][2], state[2])
        ego = states[0][0]
        self.assertAlmostEqual(np.arctan2(ego[60, 1, 0], ego[60, 0, 0]), 12 / 22)

    def test_extended_turn_continues_tangentially(self):
        # A long test must not loop around a circular road or reverse at the arc end.
        s = np.array([0.0, 22 * np.pi / 2, 22 * np.pi / 2 + 10])
        points = centerline(s, curved=True)
        np.testing.assert_allclose(points[0], [0, 0, 0], atol=1e-10)
        np.testing.assert_allclose(points[1:], [[22, 22, 0], [22, 32, 0]], atol=1e-10)

    def test_long_following_keeps_lead_ahead_without_prescribed_contact(self):
        times = np.arange(800) / 30
        ego, lead, _ = scenario_state("left_turn", times, lead_speed=6)
        # Same arc-length speed and a 24 m lead; Euclidean gap shortens on the turn.
        distances = np.linalg.norm(lead[:, :2, 3] - ego[:, :2, 3], axis=1)
        self.assertGreater(distances.min(), 22)
        np.testing.assert_allclose(distances[times > 6], 24)
        for speed in [-1, float("nan")]:
            with self.assertRaises(ValueError):
                scenario_state("left_turn", times, lead_speed=speed)

    def test_pedestrian_really_starts_behind_occluder(self):
        ego, _, actors = scenario_state("occluded_pedestrian", np.array([0.0, 1.6]))
        # Check camera-to-person sight line crosses the van's axis-aligned footprint.
        # Pinned Hyperion8 front-wide optical center, metres in vehicle FLU.
        camera = np.array([1.7494261264801025, 0.002694224938750267, 1.4474546909332275])
        for idx, blocked in [(0, True), (1, False)]:
            origin = ego[idx, :3, 3] + camera
            target = np.array(actors[idx]["crossing_person"]["object_to_world"])[:3, 3]
            van = actors[idx]["occluding_van"]
            center = np.array(van["object_to_world"])[:3, 3]
            half = np.array(van["object_lwh"]) / 2
            ray = origin + np.linspace(0, 1, 1001)[:, None] * (target - origin)
            intersects = np.any(np.all(np.abs(ray - center) < half, axis=1))
            self.assertEqual(bool(intersects), blocked)

    def test_contact_occurs_at_declared_time(self):
        _, _, actors = scenario_state("adjacent_collision", np.array([0.0, 1.1]))
        for i, expected_gap in [(0, 5.5), (1, 0.0)]:
            left = actors[i]["impacting_car"]
            right = actors[i]["stopped_adjacent_car"]
            gap = right["object_to_world"][0][3] - left["object_to_world"][0][3] - 4.5
            self.assertAlmostEqual(gap, expected_gap)


class TemporalAlignmentTests(unittest.TestCase):
    def test_continuation_control_starts_at_feedback_frame(self):
        self.assertEqual(chunk_ranges(397, 2), [(0, 400), (396, 796)])
        # The first decoded chunk ends at control frame 396; the second starts there.
        ranges = chunk_ranges(397, 3)
        for previous, current in zip(ranges, ranges[1:]):
            self.assertEqual(previous[0] + 396, current[0])

    def test_reject_invalid_alignment(self):
        for frames, chunks, feedback in [(400, 1, 1), (397, 0, 1), (397, 2, 397)]:
            with self.assertRaises(ValueError):
                chunk_ranges(frames, chunks, feedback)


class ActorSupportTests(unittest.TestCase):
    def test_box_range_bounds_distinguish_near_field_blind_region(self):
        actor = dict(object_lwh=[2, 2, 2], object_to_world=pose(10, 0, 0).tolist())
        nearest, farthest = box_range_bounds(np.zeros(3), actor)
        self.assertAlmostEqual(nearest, 9)
        self.assertAlmostEqual(farthest, np.sqrt(123))
        nearest, farthest = box_range_bounds(np.array([10, 0, 0]), actor)
        self.assertEqual(nearest, 0)
        self.assertAlmostEqual(farthest, np.sqrt(3))

    def test_rotated_translated_box_and_deep_interior(self):
        transform = pose(12, 3, 1, np.pi / 2)
        actor = dict(object_lwh=[4, 2, 2], object_to_world=transform.tolist())
        local = np.array([[2, 0, 0], [0, 1.2, 0], [0, 0, 0], [3, 0, 0]])
        world = local @ transform[:3, :3].T + transform[:3, 3]
        np.testing.assert_array_equal(near_box(world, actor), [True, True, False, False])


if __name__ == "__main__":
    unittest.main()

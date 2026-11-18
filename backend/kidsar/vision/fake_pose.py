"""FakePose: N walking stick figures (deterministic), so the UI and tests need no model."""

from __future__ import annotations

import math

import numpy as np

from ..protocol import NUM_KEYPOINTS, KEYPOINT_NAMES, Keypoint, Person

_IDX = {n: i for i, n in enumerate(KEYPOINT_NAMES)}


def _skeleton(cx: float, base_y: float, size: float, phase: float) -> list[Keypoint]:
    """COCO-17 stick figure centered at cx, feet at base_y, height `size` (normalized)."""
    pts = [Keypoint(cx, base_y, 0.0)] * NUM_KEYPOINTS
    pts = list(pts)

    def put(name: str, dx: float, dy: float, c: float = 0.95) -> None:
        pts[_IDX[name]] = Keypoint(cx + dx * size, base_y - dy * size, c)

    sway = 0.04 * math.sin(phase)
    put("nose", sway, 0.90)
    put("left_eye", sway - 0.015, 0.92); put("right_eye", sway + 0.015, 0.92)
    put("left_ear", sway - 0.03, 0.90); put("right_ear", sway + 0.03, 0.90)
    put("left_shoulder", -0.10, 0.78); put("right_shoulder", 0.10, 0.78)
    swing = 0.06 * math.sin(phase * 2)
    put("left_elbow", -0.14, 0.62 + swing); put("right_elbow", 0.14, 0.62 - swing)
    put("left_wrist", -0.15, 0.48 + swing * 2); put("right_wrist", 0.15, 0.48 - swing * 2)
    put("left_hip", -0.07, 0.50); put("right_hip", 0.07, 0.50)
    put("left_knee", -0.08, 0.26 + swing); put("right_knee", 0.08, 0.26 - swing)
    put("left_ankle", -0.08, 0.0); put("right_ankle", 0.08, 0.0)
    return pts


class FakePose:
    def __init__(self, n_people: int = 2):
        self.n = n_people

    def estimate(self, image: np.ndarray, t: float) -> list[Person]:
        people: list[Person] = []
        for i in range(self.n):
            cx = 0.5 + (i - (self.n - 1) / 2) * 0.28 + 0.06 * math.sin(t * 0.7 + i)
            size = 0.55 - 0.08 * i  # different heights, like kids of different ages
            kps = _skeleton(cx, 0.95, size, t * 2 + i)
            xs = [k.x for k in kps]; ys = [k.y for k in kps]
            people.append(Person(id=i + 1, score=0.9, bbox=(min(xs), min(ys), max(xs), max(ys)), keypoints=kps))
        return people

"""PoseEstimator boundary."""

from __future__ import annotations

from typing import Protocol

import numpy as np

from ..protocol import Person


class PoseEstimator(Protocol):
    def estimate(self, image: np.ndarray, t: float) -> list[Person]:
        """People in `image` with normalized keypoints. `t` is seconds (monotonic)."""
        ...

"""Synthetic camera: test-pattern video plus no real people. Runs anywhere, no hardware."""

from __future__ import annotations

import time
from typing import Optional

import numpy as np

from .base import Frame


class SyntheticCamera:
    def __init__(self, width: int = 1280, height: int = 720, fps: int = 30):
        self.width, self.height, self.fps = width, height, fps
        self._t0 = 0.0
        self._last_idx = -1
        # Static gradient background, built once.
        xs = np.linspace(0, 255, width, dtype=np.uint8)[None, :]
        ys = np.linspace(0, 255, height, dtype=np.uint8)[:, None]
        bg = np.zeros((height, width, 3), np.uint8)
        bg[..., 0] = xs // 2 + 40
        bg[..., 1] = ys // 2 + 40
        bg[..., 2] = 110
        self._bg = bg

    def start(self) -> None:
        self._t0 = time.monotonic()
        self._last_idx = -1

    def stop(self) -> None:
        pass

    def latest(self) -> Optional[Frame]:
        t = time.monotonic() - self._t0
        idx = int(t * self.fps)
        if idx == self._last_idx:
            return None  # nothing new yet
        self._last_idx = idx
        img = self._bg.copy()
        # A moving block makes motion/latency visible.
        x = int((np.sin(t * 1.5) * 0.4 + 0.5) * (self.width - 80))
        img[self.height - 60 : self.height - 20, x : x + 80] = (255, 255, 255)
        return Frame(image=img, t_capture_ms=int(time.time() * 1000), camera_id="synthetic")

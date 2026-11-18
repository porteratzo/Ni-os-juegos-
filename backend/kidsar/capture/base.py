"""FrameSource boundary: everything that produces camera frames implements this."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol

import numpy as np


@dataclass
class Frame:
    image: np.ndarray  # HxWx3 uint8 RGB
    t_capture_ms: int
    camera_id: str = "camera"
    offline: bool = False  # True when the camera service sent a fallback frame


class FrameSource(Protocol):
    def start(self) -> None: ...

    def latest(self) -> Optional[Frame]:
        """Newest frame, or None if nothing new since the last call. Never a backlog."""
        ...

    def stop(self) -> None: ...

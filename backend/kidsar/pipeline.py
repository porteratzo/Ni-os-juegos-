"""capture -> estimate -> encode loop. Latest-frame-wins: never queues, never replays."""

from __future__ import annotations

import io
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

from PIL import Image

from .capture.base import Frame, FrameSource
from .protocol import FrameHeader, encode_message
from .vision.base import PoseEstimator


@dataclass
class Metrics:
    frames: int = 0
    fps: float = 0.0
    last_timing_ms: dict | None = None
    camera_offline: bool = False


class Pipeline:
    def __init__(self, source: FrameSource, pose: PoseEstimator, jpeg_quality: int = 80,
                 stale_after_s: float = 1.0):
        self.source, self.pose = source, pose
        self.jpeg_quality = jpeg_quality
        self.stale_after_s = stale_after_s
        self.metrics = Metrics()
        self._lock = threading.Lock()
        self._latest: Optional[tuple[int, bytes]] = None  # (frame_id, message)
        self._cond = threading.Condition(self._lock)
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._frame_id = 0
        self._last_frame_at = 0.0
        self._fps_window: list[float] = []

    # --- lifecycle
    def start(self) -> None:
        self.source.start()
        self._last_frame_at = time.monotonic()
        self._thread = threading.Thread(target=self._run, name="pipeline", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        with self._cond:
            self._cond.notify_all()
        if self._thread:
            self._thread.join(timeout=2)
        self.source.stop()

    # --- consumers
    def wait_newer(self, last_id: int, timeout: float = 1.0) -> Optional[tuple[int, bytes]]:
        """Block until a frame newer than last_id exists; returns only the NEWEST one."""
        with self._cond:
            self._cond.wait_for(lambda: self._stop.is_set() or (self._latest and self._latest[0] > last_id),
                                timeout=timeout)
            if self._latest and self._latest[0] > last_id:
                return self._latest
            return None

    # --- loop
    def _encode_jpeg(self, frame: Frame) -> bytes:
        buf = io.BytesIO()
        Image.fromarray(frame.image).save(buf, format="JPEG", quality=self.jpeg_quality)
        return buf.getvalue()

    def _publish(self, msg: bytes) -> None:
        with self._cond:
            self._latest = (self._frame_id, msg)
            self._cond.notify_all()

    def _offline_message(self) -> bytes:
        self._frame_id += 1
        h = FrameHeader(self._frame_id, int(time.time() * 1000), 0, 0, camera_offline=True)
        return encode_message(h, b"")

    def _run(self) -> None:
        while not self._stop.is_set():
            frame = self.source.latest()
            now = time.monotonic()
            if frame is None:
                if now - self._last_frame_at > self.stale_after_s:
                    self.metrics.camera_offline = True
                    self._publish(self._offline_message())
                    self._last_frame_at = now  # re-announce once per stale window
                time.sleep(0.002)
                continue
            self._last_frame_at = now
            self.metrics.camera_offline = frame.offline
            t0 = time.perf_counter()
            if frame.offline:
                self._publish(self._offline_message())
                continue
            people = self.pose.estimate(frame.image, now)
            t1 = time.perf_counter()
            jpeg = self._encode_jpeg(frame)
            t2 = time.perf_counter()
            self._frame_id += 1
            h, w = frame.image.shape[:2]
            timing = {"pose": (t1 - t0) * 1000, "encode": (t2 - t1) * 1000,
                      "age_at_publish": time.time() * 1000 - frame.t_capture_ms}
            self.metrics.last_timing_ms = timing
            self._publish(encode_message(FrameHeader(self._frame_id, frame.t_capture_ms, w, h,
                                                     people=people, timing_ms=timing), jpeg))
            self._tick_fps(now)

    def _tick_fps(self, now: float) -> None:
        self.metrics.frames += 1
        self._fps_window.append(now)
        self._fps_window = [t for t in self._fps_window if now - t <= 2.0]
        if len(self._fps_window) > 1:
            self.metrics.fps = (len(self._fps_window) - 1) / (self._fps_window[-1] - self._fps_window[0])

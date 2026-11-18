"""Settings, overridable by environment variables (KIDSAR_*)."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _env(name: str, default: str) -> str:
    return os.environ.get(f"KIDSAR_{name}", default)


@dataclass(frozen=True)
class Settings:
    source: str = "synthetic"  # synthetic | redis (redis arrives in M1a)
    host: str = "127.0.0.1"  # LAN bind is an explicit choice (privacy, D6)
    port: int = 8000
    fps: int = 30
    width: int = 1280
    height: int = 720
    jpeg_quality: int = 80
    # Placeholders for the camera stream (ARCHITECTURE.md 2.3); used from M1a.
    redis_url: str = "redis://localhost:6379/0"
    camera_stream: str = "camera_frames"
    camera_id: str = "camera_1"
    camera_output: str = "preview"
    stale_after_s: float = 1.0

    @classmethod
    def from_env(cls) -> "Settings":
        d = cls()
        return cls(
            source=_env("SOURCE", d.source),
            host=_env("HOST", d.host),
            port=int(_env("PORT", str(d.port))),
            fps=int(_env("FPS", str(d.fps))),
            width=int(_env("WIDTH", str(d.width))),
            height=int(_env("HEIGHT", str(d.height))),
            jpeg_quality=int(_env("JPEG_QUALITY", str(d.jpeg_quality))),
            redis_url=_env("REDIS_URL", d.redis_url),
            camera_stream=_env("CAMERA_STREAM", d.camera_stream),
            camera_id=_env("CAMERA_ID", d.camera_id),
            camera_output=_env("CAMERA_OUTPUT", d.camera_output),
            stale_after_s=float(_env("STALE_AFTER_S", str(d.stale_after_s))),
        )

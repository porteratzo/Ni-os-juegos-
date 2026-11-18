"""Wire protocol between the vision service and the browser (single source of truth).

Binary WebSocket message: [4-byte big-endian header length][JSON header][JPEG bytes].
Keypoints use COCO-17 order; frontend/shared/keypoints.js mirrors KEYPOINT_NAMES.
"""

from __future__ import annotations

import json
import struct
from dataclasses import dataclass, field
from typing import Any

PROTOCOL_VERSION = 1

KEYPOINT_NAMES = (
    "nose", "left_eye", "right_eye", "left_ear", "right_ear",
    "left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
    "left_wrist", "right_wrist", "left_hip", "right_hip",
    "left_knee", "right_knee", "left_ankle", "right_ankle",
)
NUM_KEYPOINTS = len(KEYPOINT_NAMES)


@dataclass
class Keypoint:
    x: float  # normalized 0..1
    y: float
    c: float  # confidence 0..1


@dataclass
class Person:
    id: int
    score: float
    bbox: tuple[float, float, float, float]  # normalized x0, y0, x1, y1
    keypoints: list[Keypoint]


@dataclass
class FrameHeader:
    frame_id: int
    t_capture_ms: int
    width: int
    height: int
    people: list[Person] = field(default_factory=list)
    camera_offline: bool = False
    timing_ms: dict[str, float] = field(default_factory=dict)
    v: int = PROTOCOL_VERSION


def _round(x: float) -> float:
    return round(float(x), 4)


def header_to_dict(h: FrameHeader) -> dict[str, Any]:
    return {
        "v": h.v,
        "frame_id": h.frame_id,
        "t_capture_ms": h.t_capture_ms,
        "width": h.width,
        "height": h.height,
        "camera_offline": h.camera_offline,
        "people": [
            {
                "id": p.id,
                "score": _round(p.score),
                "bbox": [_round(v) for v in p.bbox],
                "keypoints": [{"x": _round(k.x), "y": _round(k.y), "c": _round(k.c)} for k in p.keypoints],
            }
            for p in h.people
        ],
        "timing_ms": {k: round(float(v), 2) for k, v in h.timing_ms.items()},
    }


def header_from_dict(d: dict[str, Any]) -> FrameHeader:
    if d.get("v") != PROTOCOL_VERSION:
        raise ValueError(f"unsupported protocol version: {d.get('v')!r}")
    people = [
        Person(
            id=p["id"],
            score=p["score"],
            bbox=tuple(p["bbox"]),  # type: ignore[arg-type]
            keypoints=[Keypoint(k["x"], k["y"], k["c"]) for k in p["keypoints"]],
        )
        for p in d["people"]
    ]
    return FrameHeader(
        frame_id=d["frame_id"],
        t_capture_ms=d["t_capture_ms"],
        width=d["width"],
        height=d["height"],
        people=people,
        camera_offline=d.get("camera_offline", False),
        timing_ms=d.get("timing_ms", {}),
    )


def encode_message(header: FrameHeader, jpeg: bytes) -> bytes:
    raw = json.dumps(header_to_dict(header), separators=(",", ":")).encode()
    return struct.pack(">I", len(raw)) + raw + jpeg


def decode_message(data: bytes) -> tuple[FrameHeader, bytes]:
    if len(data) < 4:
        raise ValueError("message too short")
    (n,) = struct.unpack(">I", data[:4])
    if len(data) < 4 + n:
        raise ValueError("truncated header")
    header = header_from_dict(json.loads(data[4 : 4 + n]))
    return header, data[4 + n :]

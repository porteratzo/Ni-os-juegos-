"""The ONE place that knows the camera service's Redis message format.

PLACEHOLDER: the real schema lives in `shared.core.camera_stream`, which is being
decoupled (ARCHITECTURE.md 2.3). Field names below come from the my_depthai README and are
UNVERIFIED against the real encoder. When the decoupled library exists, either call its
decoder here or keep this one and rely on tests/test_codec.py (fixture produced by the library).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Mapping, Optional, Union

Raw = Union[bytes, str]

# TODO(shared-lib): confirm names, add a schema-version field, add the device capture timestamp.
FIELD_CAMERA_ID = "camera_id"
FIELD_OUTPUT_TYPE = "output_type"
FIELD_WIDTH = "width"
FIELD_HEIGHT = "height"
FIELD_FORMAT = "format"
FIELD_DATA = "data"
FIELD_TIMESTAMP = "timestamp"
FIELD_IS_FALLBACK = "is_fallback"
FIELD_CAPTURE_TS = "t_capture"  # TODO(shared-lib): not published today (finding F4)


@dataclass
class CameraFrameMessage:
    camera_id: str
    output_type: str
    width: int
    height: int
    jpeg: bytes
    t_publish: datetime
    t_capture: Optional[datetime]  # None until the camera service publishes it
    is_fallback: bool


def _s(v: Raw) -> str:
    return v.decode() if isinstance(v, bytes) else str(v)


def _norm(fields: Mapping[Raw, Raw]) -> dict[str, Raw]:
    return {_s(k): v for k, v in fields.items()}


def _truthy(v: Optional[Raw]) -> bool:
    return v is not None and _s(v).strip().lower() in {"1", "true", "yes"}


def decode(fields: Mapping[Raw, Raw]) -> CameraFrameMessage:
    f = _norm(fields)
    missing = [k for k in (FIELD_CAMERA_ID, FIELD_OUTPUT_TYPE, FIELD_DATA, FIELD_TIMESTAMP) if k not in f]
    if missing:
        raise ValueError(f"camera message missing fields: {missing}")
    fmt = _s(f.get(FIELD_FORMAT, "jpeg")).lower()
    if fmt not in ("jpeg", "jpg"):
        raise ValueError(f"unsupported camera frame format: {fmt!r}")
    data = f[FIELD_DATA]
    if isinstance(data, str):
        raise ValueError("frame data must be bytes")
    cap = f.get(FIELD_CAPTURE_TS)
    return CameraFrameMessage(
        camera_id=_s(f[FIELD_CAMERA_ID]),
        output_type=_s(f[FIELD_OUTPUT_TYPE]),
        width=int(_s(f.get(FIELD_WIDTH, 0))),
        height=int(_s(f.get(FIELD_HEIGHT, 0))),
        jpeg=data,
        t_publish=datetime.fromisoformat(_s(f[FIELD_TIMESTAMP])),
        t_capture=datetime.fromisoformat(_s(cap)) if cap is not None else None,
        is_fallback=_truthy(f.get(FIELD_IS_FALLBACK)),
    )

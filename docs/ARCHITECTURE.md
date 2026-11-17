# Niños Juegos: AR party game architecture (v2, camera service integrated)

A NUC plugged into a TV and a camera. The camera sees the kids, the NUC detects their bodies, and the TV shows the live video with AR costumes (Mario-style caps, capes, superhero masks) drawn on top.

## 1. Goals and non-goals

**Goals**
- Live video on the TV with effects that follow the kids' bodies, at a smooth 30 fps and under ~150 ms end to end.
- Works offline on a single NUC. No cloud, no accounts.
- A parent or kid can pick the costume or game from a phone or tablet.
- Adding a new costume should be a small, self-contained folder (art plus a few lines of config), not a change to the core.
- Safe for kids: video never leaves the house, nothing is stored.

**Non-goals (for v1)**
- Multiplayer over the internet, recording or sharing clips, accounts.
- Photorealistic 3D cloth simulation.

## 2. Confirmed inputs

1. **Camera:** Luxonis OAK, run by the existing **`my_depthai` camera service** (DepthAI v3, see §2.1). It is already connected. We consume it as a black box over Redis and do not modify it for v1.
2. **NUC:** Intel NUC, Ubuntu 24.04, HDMI to the TV.
3. **Players:** 2 to 4 kids of mixed ages, so multi-person tracking with stable IDs is required from the start.
4. **Controls v1:** keyboard on the NUC. The phone remote is **decided: later** (after M4); the control WebSocket stays in the design so it is cheap to add.
5. **Art:** I generate simple original placeholder costumes. You can swap in your own images later by replacing files in an effect folder.

### 2.1 What the camera service actually provides (read from `my_depthai`)

| Fact | Detail | Consequence for this project |
|------|--------|------------------------------|
| Transport | `camera_broker.py` encodes each frame as JPEG and `XADD`s it to the Redis stream `camera_frames` (`MAXLEN ~ 100`). | Our `FrameSource` is a Redis consumer. No DepthAI code in this repo. |
| Message fields (provisional, see §2.3) | `camera_id`, `timestamp` (ISO string), `camera_type`, `output_type`, `width`, `height`, `format=jpeg`, `data`, plus an `is_fallback` flag (exact encoding lives in `shared.core.camera_stream.encode_frame_message`, being decoupled). | We filter by `camera_id` + `output_type`, and treat `is_fallback=true` as "camera offline". |
| Outputs | `preview` (NV12, default 300x300), `video` (BGR888p), `fullvideo` (NV12, 4K), `still` (trigger only; the broker skips it). Only `dai.node.Camera`: **no depth, no stereo, no on-device NN** today. | Pose runs on the NUC for v1. Depth and on-device pose become *camera service* features (M5), not assumptions. |
| Rate | Broker loop is rate-limited to `--fps` (default 5; the shipped config uses 3 fps at 4K for inspection). One loop publishes every camera and output serially. | **Must be reconfigured for games**: 1280x720 `video` at 30 fps, `--fps 30`, `--max-stream-length 10`. Needs a benchmark (§7), not an assumption; mind PoE bandwidth (§2.2 F1). |
| Resilience | Health monitor, reconnect with backoff, Redis reconnect, fallback "CAMERA OFFLINE" frames, management UI on `127.0.0.1:5002`. | We do not re-implement reconnect. We only react to `is_fallback` and to a stalled stream. |
| Timestamps | `timestamp` is stamped by the broker at publish time. Device capture time exists in per-frame metadata inside the library but is **not published**. | Latency measured from this field excludes camera exposure and USB time. Adding the device timestamp is a small camera-service change worth making (M1). |
| Stack | `depthai>=3,<4`, Python, Redis. **Confirmed PoE** (gigabit Ethernet, ~940 Mbit/s usable; config uses an IP address). | The link, not the NUC, may be the first bottleneck. See §2.2 bandwidth math. |

**Integration decision (D7): consume over Redis rather than import `CameraManager` directly.**
Redis already isolates the camera's flaky USB/PoE and XLink behaviour in its own process (the benchmark notes show a second XLink connection in one process fails and DepthAI can segfault), so a camera crash cannot take down the game. Cost: one extra copy, one JPEG encode and one decode per frame, roughly 5 to 10 ms at 720p. Fallback if the benchmark says that cost is too high: a `DirectOakCamera` adapter that imports `CameraManager` in-process, behind the same `FrameSource` interface. Nothing else changes.

**Change policy: `my_depthai` is frozen for now.** Nothing below is started. This document assumes these changes will be made once the go-ahead is given, and the design is written so nothing in this repo depends on them landing first.

Requested camera-service changes (all **pending approval**, in priority order):
1. Config only: a game profile with a 720p/30 output and broker flags `--fps 30 --max-stream-length 10`. See §2.2 for which output type to use over PoE.
2. Small code change: read the newest queued frame instead of the oldest (see §2.2, finding F2).
3. Small code change: publish the device capture timestamp in the message.
4. Later: an optional second stream `camera_depth` (aligned depth) and on-device pose.

**Redis consumption contract (our side)**
- Reader uses `XREAD BLOCK` starting from `$` (new messages only) and **always keeps only the newest message in a batch**, discarding older ones. It never replays the backlog. This implements "always show the newest frame".
- If no message arrives for 1.0 s, or `is_fallback` is set, the display shows the "reconnecting" screen. Recovery is automatic.
- Redis binds to localhost only, no password needed for v1 (privacy rule D6).

### 2.2 Suitability assessment of `my_depthai` for this application

**Verdict: suitable as the camera layer, with three gaps to close before it can drive a 30 fps game. Not suitable as-is for the game's frame rate.** It was built for slow manufacturing inspection, and its strengths (robustness, isolation) matter more to us than its weaknesses, which are all configuration or small changes.

**Strengths for us**
- Self-healing: health monitor, reconnect with backoff, Redis reconnect, "CAMERA OFFLINE" fallback frames. A kids' appliance must recover without a keyboard.
- Process isolation through Redis (the repo's own notes say a second XLink connection in one process fails and DepthAI can segfault).
- Already has the right queue policy: non-blocking device queues of depth 4 that drop the oldest frame.
- Full camera control (exposure, ISO, focus, regions) which we need to lock exposure indoors. Management UI is loopback-only and token-protected.
- Broad test suite (21 test files, hardware-free mocks) and a benchmark script that runs each resolution in its own subprocess.
- DepthAI v3, which supports depth and on-device NN for later.

**Gaps and findings**

| # | Finding | Impact | Fix (pending approval) |
|---|---------|--------|------------------------|
| F1 | **PoE bandwidth.** The `video` output is requested as BGR888p (3 bytes/px). 1280x720x3x30 = ~83 MB/s = **~664 Mbit/s**, about 70% of gigabit and risky next to other traffic. 1080p30 BGR (~1.5 Gbit/s) is impossible. The `preview` output is NV12 (1.5 bytes/px): 720p30 = ~332 Mbit/s. | Wrong output type or size would silently cap fps. | Use `preview` at 1280x720 NV12 (size is configurable), or add an NV12 `video` variant. Confirm with `benchmark.py`/`benchmark_nv12.py`. Keep the camera on a dedicated NIC/switch port. |
| F2 | **Oldest-first read creates standing latency.** `run()` sleeps one frame interval and *then* does work, and only restarts the timer after the work (`last_frame_time` is set at the end). The effective rate is therefore below the camera fps, the depth-4 device queue fills, and `tryGet()` returns the *oldest* of 4 frames: up to ~4 frames (~130 ms at 30 fps) of added, constant delay. This alone would eat the whole latency budget. | Costumes would trail the kids by a visible margin. | Drain the queue and keep the newest frame (small change in `camera_manager`/`base_module`), and fix the timer to be start-to-start. |
| F3 | **Single serial loop.** One thread polls, converts (NV12 to BGR), JPEG-encodes and `XADD`s every camera and output in turn. Fine for one camera at 30 fps (~5-10 ms of work per frame at 720p); a second camera or output would cut the rate. | Limits us to one camera, one output for v1. | Accept for v1. If needed, one publisher thread per camera/output. |
| F4 | **Timestamp is publish time, not capture time.** Device metadata exists in memory but is not published. | We cannot measure or correct true latency. | Add the device capture timestamp to the message. |
| F5 | **Two JPEG hops** (JPEG in the broker, JPEG again in our WebSocket) cost ~10 ms and some quality. | Small. | v1: decode, run pose, re-encode. If the benchmark says it matters, forward the broker JPEG bytes unchanged when no server-side drawing is needed (the browser draws the effects, so this is likely possible). |
| F6 | **No depth, no NN, no pose** in the service (only `dai.node.Camera`). | Pose runs on the NUC. | Expected; later stream `camera_depth` / on-device pose (M5). |
| F7 | **Inspection-oriented defaults** (4K at 3 fps in the shipped config, 3-5 fps broker default). | Wrong out of the box. | Dedicated game profile (config only). |
| F8 | **Coupled to a monorepo `shared` package** (`ConfigLoader`, stream codec). | Not installable standalone today. | Being decoupled by you; see §2.3. |

**Net latency budget implication:** with F2 fixed, the camera-side cost is about one frame interval (33 ms) plus transport. With F2 unfixed, add ~130 ms, so F2 is the single most important change.

### 2.3 Placeholder: camera stream contract (shared library being decoupled)

The `shared` library that defines the Redis message is being decoupled and its final shape is unknown. We assume it will exist as a small standalone package, and keep everything uncertain behind one seam so only one file changes when it lands.

- **Seam:** `backend/kidsar/capture/camera_stream_codec.py` with a single function `decode(fields: Mapping[bytes, bytes]) -> CameraFrameMessage`. Nothing else in this repo reads raw Redis fields.
- **`CameraFrameMessage` (our own dataclass, fixed):** `camera_id: str`, `output_type: str`, `width: int`, `height: int`, `jpeg: bytes`, `t_publish: datetime`, `t_capture: datetime | None` (None until F4 lands), `is_fallback: bool`.
- **Provisional field mapping (TODO, replace when the decoupled library is defined):** `camera_id`, `timestamp` (ISO) to `t_publish`, `output_type`, `width`, `height`, `format` (must equal `jpeg`), `data` to `jpeg`, `is_fallback`. Field names come from the current README and are **unverified against the real encoder**.
- **Stream and tuning names:** stream name `camera_frames`, camera id and output type are settings in our `config.py` (`CAMERA_STREAM`, `CAMERA_ID`, `CAMERA_OUTPUT`), not constants.
- **When the library lands:** either import its decoder inside `camera_stream_codec.py`, or keep our own decoder and add a contract test that decodes a fixture message produced by the library's encoder. A recorded fixture message is committed now so the test exists from M0.
- **Open placeholders:** package name and version pin, schema version field, any change of transport (stream vs pub/sub), and whether the device timestamp field has a name yet.

## 3. System overview

```
 Luxonis OAK camera (PoE, DepthAI v3)
     │
     ▼
┌─────────────────────────── NUC (one machine) ───────────────────────────┐
│  Camera service  (my_depthai, existing, separate process)               │
│  camera_broker.py ──JPEG──▶ Redis stream "camera_frames" (localhost)    │
│                                  │                                      │
│                                  ▼                                      │
│  Vision service (Python, this repo)                                     │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────┐  ┌────────────┐   │
│  │ RedisCamera │─▶│ Pose / person│─▶│ Tracker       │─▶│ Publisher  │   │
│  │ (FrameSource│  │ model (ONNX) │  │ (stable IDs,  │  │ (WebSocket)│   │
│  │  newest only│  └──────────────┘  │  smoothing)   │  └─────┬──────┘   │
│  └─────────────┘                    └───────────────┘        │          │
│                          frame JPEG + people JSON, same msg  │          │
│                                                              ▼          │
│  Display app (Chromium kiosk, fullscreen on the TV)  ◀───────┘          │
│  ┌──────────────────────────────────────────────────────────────┐       │
│  │ Canvas/WebGL: draw video, then run the active Effect on the  │       │
│  │ tracked people (hat on head, cape on shoulders, ...)         │       │
│  └──────────────────────────────────────────────────────────────┘       │
│                                                                         │
│  Control app (web page, opened from phone/tablet)  ──▶ same server      │
└─────────────────────────────────────────────────────────────────────────┘
        │ HDMI
        ▼
       TV
```

Four processes, one machine: the **camera service** (`my_depthai`, owns the device), the **vision service**, the **display app** (a web page shown fullscreen), and the **control app** (another web page, used from a phone). Redis is the only link between camera and vision.

## 4. Key decisions

| # | Decision | Why | Alternative rejected |
|---|----------|-----|----------------------|
| D1 | **Split perception (Python) from rendering (browser).** | Python has the best model runtimes (OpenVINO/ONNX) for the NUC's Intel GPU. The browser has the best tools for fast 2D/3D drawing, and art people already know them. A clean JSON boundary lets us swap either side. | All-in-one browser app with MediaPipe JS: simpler, but weak on multi-person tracking, harder to tune on a NUC, and locks us to one model stack. |
| D2 | **Video frame and body data travel in the same WebSocket message.** | The effect is always drawn on the exact frame it was computed from, so costumes never lag or drift against the video. | Sending video via WebRTC and landmarks separately: needs sync logic and adds complexity for no gain on localhost. |
| D3 | **Effects are plugins** (a folder with `manifest.json`, art, and an optional `effect.js`). | Kids' favourites come and go. Most costumes are just "attach this image to that body point", which needs no code. | Hard-coding each costume. |
| D4 | **Pose model: MediaPipe Pose or MoveNet, exported to ONNX/OpenVINO, behind a `PoseEstimator` interface.** | Both are small and fast on CPU/iGPU. The interface lets us benchmark and swap. | A heavy model (e.g. YOLO pose large): more accurate but risks missing the frame budget on a NUC. |
| D5 | **Pose first, segmentation later.** | Costumes (hats, capes, masks) only need keypoints. Background replacement and "player cut-out" games need a person mask, which we add as an optional second model. | Starting with segmentation: more costly, not needed for the first fun result. |
| D6 | **Local only, no persistence.** | Child privacy. The server binds to the LAN only and stores no frames. | n/a |
| D7 | **Consume the camera over Redis (existing `my_depthai` broker).** See §2.1. | Reuses a tested, self-healing service; process isolation from DepthAI crashes; zero changes to start. | Importing `CameraManager` in-process: ~5-10 ms faster, but a camera fault can crash the game. Kept as a documented fallback adapter. |
| D8 | **Latest-frame-wins everywhere**: Redis reader, pipeline and WebSocket all drop stale frames. | Latency stays bounded when any stage is slow; a laggy costume is worse than a skipped frame. | Queues with back-pressure: smoother in theory, unbounded delay in practice. |

## 5. Components

### 5.1 Vision service (`backend/`, Python 3.12, FastAPI + uvicorn)

Runs a loop in a worker thread and exposes a small server.

| Module | Responsibility |
|--------|----------------|
| `capture/` | `FrameSource` interface: `latest() -> Frame(image, t_capture, camera_id, offline: bool)`. Implementations: **`RedisCamera`** (primary; consumes the `my_depthai` stream, §2.1), `DirectOakCamera` (fallback, imports `CameraManager`; only if the benchmark requires it), `UvcCamera` (generic webcam), `VideoFile` (replay a clip), `Synthetic` (moving dummy skeleton, so the UI can be built with no camera). |
| `vision/` | `PoseEstimator` interface returning per-person keypoints. Implementations: `OnnxPose` (real), `FakePose` (tests). Optional `Segmenter` later. |
| `tracking/` | Assigns a stable ID to each kid across frames, smooths keypoints (One-Euro filter) to stop jitter, drops people who leave. |
| `pipeline.py` | Runs capture → estimate → track; drops frames if inference falls behind (always show the newest frame, never queue). Reports timing per stage. |
| `server.py` | Serves the web apps, the WebSocket endpoints and a health/metrics endpoint. Holds shared state (active effect, settings). |
| `protocol.py` | Typed message schemas (single source of truth, see §6). |

### 5.2 Display app (`frontend/display/`, plain ES modules, no build step at first)

- Opens the WebSocket, decodes each frame (`createImageBitmap`), draws it mirrored, then calls the active effect's `draw()`.
- Fullscreen in Chromium kiosk mode; hides the cursor; shows a small "no camera / reconnecting" screen instead of crashing.
- Optional corner overlay with fps/latency for debugging (hidden by default).

### 5.3 Control app (`frontend/control/`)

- Mobile-friendly page: big buttons for costume choice, a "random" button, mirror on/off, quit game.
- Talks to the same server. No login; only reachable on the home network.

### 5.4 Effects (`frontend/effects/<name>/`)

```
effects/mario-cap/
  manifest.json   # name, thumbnail, anchors
  cap.png
  effect.js       # optional, for custom behaviour (sparkles, jump coins, ...)
```

A declarative `manifest.json` handles the common case: "attach `cap.png` to the head, scale by head size, rotate with shoulder tilt". Anything fancier exports `{ init(ctx), draw(ctx, people, t), dispose() }`.

Planned effect types, in build order:
1. **Attachments:** caps, masks, capes, capes tied to shoulders (sprite anchored to keypoints).
2. **Reactive effects:** coins when a kid jumps, power-up glow when both arms go up, fire when they punch.
3. **Games:** pop balloons with your hands, "floor is lava" (needs segmentation), dance-pose matching.

## 6. Interface contract (vision service ⇄ browser)

WebSocket `/ws/stream` binary message: `[4-byte big-endian header length][JSON header][JPEG bytes]`.

```jsonc
// header
{
  "v": 1,
  "frame_id": 1042,
  "t_capture_ms": 1731880000123,
  "width": 1280, "height": 720,
  "people": [
    {
      "id": 3,                       // stable track ID
      "score": 0.91,
      "bbox": [0.31, 0.10, 0.52, 0.95],         // normalized x0,y0,x1,y1
      "keypoints": [ { "x": 0.42, "y": 0.18, "c": 0.97 } /* ...17 or 33 points, normalized */ ]
    }
  ],
  "camera_offline": false,           // true when the broker sent a fallback frame; no people then
  "timing_ms": { "redis_decode": 6, "pose": 14, "track": 1, "age_at_publish": 55 }
}
```

Keypoints use one fixed topology (COCO-17 as the common subset), with named indices exported to the frontend so effects say `K.NOSE`, `K.LEFT_SHOULDER` instead of numbers.

WebSocket `/ws/control` JSON messages: `set_effect`, `set_setting`, `state` (server → all clients, so phone and TV stay in sync).

Other endpoints: `GET /` (display), `GET /control`, `GET /health`, `GET /metrics`.

## 7. Performance budget (target 30 fps, ≤150 ms glass-to-glass)

| Stage | Budget |
|-------|--------|
| Camera exposure + transport to NUC | ~40 ms (largely fixed by the camera) |
| Broker JPEG encode + Redis hop + our decode | ≤ 10 ms (720p; to be measured) |
| Pose inference (720p downscaled to model size) | ≤ 20 ms |
| Tracking + smoothing | ≤ 2 ms |
| JPEG encode + WebSocket (localhost) | ≤ 8 ms |
| Browser decode + draw effects | ≤ 10 ms |
| TV display | ~20–50 ms (turn on "Game Mode" on the TV) |

Rules to keep this: capture at 720p, run the model on a smaller copy; always process the latest frame and drop the rest; inference on OpenVINO (Intel iGPU) if CPU is not enough; measure every stage and expose it in `/metrics`. **First task of M1 is a benchmark of the camera service at 720p/30** (reusing `benchmark.py` for the camera side, plus a Redis round-trip script here): achieved fps, stream-to-consumer latency, JPEG quality vs. size. Its result decides D7 (Redis vs direct) and the model choice.

## 8. Repository layout (proposed)

```
.
├── README.md
├── docs/
│   ├── ARCHITECTURE.md
│   └── ADDING_AN_EFFECT.md        (later)
├── backend/
│   ├── pyproject.toml
│   ├── kidsar/
│   │   ├── capture/  (redis_camera.py, synthetic.py, ...)  vision/  tracking/
│   │   ├── pipeline.py  server.py  protocol.py  config.py
│   └── tests/
├── frontend/
│   ├── display/        # TV page
│   ├── control/        # phone page
│   ├── shared/         # protocol decoding, keypoint names, drawing helpers
│   └── effects/        # one folder per costume/game
├── models/             # downloaded model files (git-ignored, fetched by a script)
├── deploy/
│   ├── camera-broker.service   # systemd: runs my_depthai broker (+ redis-server dependency)
│   ├── kidsar.service          # systemd: vision service, After=camera-broker.service
│   └── kiosk.sh                # launch Chromium fullscreen on the TV
└── scripts/            # setup-nuc.sh, download-models.sh, benchmark.py
```

## 9. Deployment on the NUC

- Ubuntu 24.04, Python venv, install with one `scripts/setup-nuc.sh`. It installs `redis-server` (bound to 127.0.0.1), the Movidius udev rule, and `my_depthai` (pinned git ref, `pip install -e`).
- Start order: `redis-server` → `camera-broker` → `kidsar` (vision) → kiosk. Each unit restarts on failure; the vision service tolerates the camera being absent.
- `systemd` unit starts the vision service on boot; autologin + `kiosk.sh` opens Chromium fullscreen at `http://localhost:8000/` on the TV output.
- The phone opens `http://<nuc-name>.local:8000/control`.
- Updates: `git pull && systemctl restart kidsar`.

## 10. Testing strategy

- **No hardware needed:** `Synthetic` camera + `FakePose` run the entire stack on any laptop and in CI.
- **Unit tests:** tracker (ID stability, smoothing), protocol encode/decode, effect manifest validation.
- **Recorded clips:** a few short videos of the kids (kept local, never committed) replayed through `VideoFile` to tune models and effects reproducibly.
- **On-device benchmark:** `scripts/benchmark.py` prints per-stage latency on the actual NUC.

## 11. Risks

| Risk | Mitigation |
|------|------------|
| Pose model misses small kids, kids close together, or partial bodies | Test with the real kids early; keep the `PoseEstimator` swappable; effects fall back gracefully when a keypoint is missing. |
| Jitter makes costumes shake | One-Euro filter in the tracker, tunable per effect. |
| Latency feels laggy on the TV | Measure each stage, TV Game Mode, always drop stale frames. |
| Camera service tuned for inspection (3-5 fps, 4K) rather than games | Dedicated game config (720p/30), benchmark first (§7); keep `DirectOakCamera` as fallback. |
| Redis stream backlog makes video lag | Reader jumps to newest message, `MAXLEN` ~10, alert via `age_at_publish` in `/metrics`. |
| Broker publishes cameras serially in one loop, so a second camera could cut fps | One camera for v1; revisit before supporting two. |
| Camera auto-exposure/auto-framing fights us | Lock exposure and framing in camera settings; document the recommended setup. |
| Privacy | Local only, no recording, bind to LAN, no outbound calls. |

## 12. Proposed milestones

1. **M0, skeleton:** repo layout, protocol, `Synthetic` camera, display page drawing a fake skeleton with one hat. Runs anywhere, no Redis.
2. **M1a, camera link + benchmark:** (needs the approved camera-service changes of §2.1, or runs degraded without them) `RedisCamera` against the live broker, raw video on the TV via the display page, measured fps and latency. Decides D7 and the model budget.
3. **M1b, pose + tracking:** pose model, tracker, hat follows a real kid on the TV.
4. **M2, costume system:** manifest-driven attachments, keyboard switching, 4-5 costumes (cap, cape, mask, ...). No control page yet.
5. **M3, NUC appliance:** systemd units (§9), kiosk, boots straight into the game.
6. **M4, games:** reactive effects, then segmentation-based games.
7. **M5, phone remote:** control page and `/ws/control` from a phone.
8. **M6, camera-side upgrades (in `my_depthai`):** aligned depth stream, device timestamps, optional on-device pose.

## 13. Open questions (remaining)

1. Exact OAK model (RVC2 vs RVC4) and its PoE switch/NIC setup. This sizes M6 on-device pose and depth.
2. Go-ahead for the camera-service changes in §2.1 / §2.2 (nothing is touched until then).
3. The decoupled stream library: name, schema, device-timestamp field (placeholders in §2.3).

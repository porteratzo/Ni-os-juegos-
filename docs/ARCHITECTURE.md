# Niños Juegos: AR party game architecture (DRAFT for review)

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

1. **Camera:** Luxonis OAK (DepthAI). Not a plain webcam. It can run neural networks on the camera itself and provides stereo depth. Capture and (optionally) pose inference therefore move behind a `FrameSource` / `PoseEstimator` boundary that the OAK adapter implements. The OAK integration may come from another of your repos (see "Pending: OAK repo link" below).
2. **NUC:** Intel NUC, Ubuntu 24.04, HDMI to the TV.
3. **Players:** 2 to 4 kids of mixed ages, so multi-person tracking with stable IDs is required from the start.
4. **Controls v1:** keyboard on the NUC. The phone remote moves to a later milestone (the control WebSocket stays in the design so it is cheap to add).
5. **Art:** I generate simple original placeholder costumes. You can swap in your own images later by replacing files in an effect folder.

### Pending: OAK repo link

Before implementing M1, the existing OAK repo decides these points, which I have left open on purpose:
- Does it already produce frames and/or pose keypoints (on-device pipeline), and in what format?
- Should this repo depend on it (git submodule / pip package) or copy its capture code?
- Which OAK model (RVC2 vs RVC4) and DepthAI version, since the pose model and the API differ.

**Impact of OAK on the design**
- Pose can run **on the camera**, freeing the NUC CPU/iGPU and cutting latency. OpenVINO on the NUC stays as a fallback `PoseEstimator`.
- **Depth is free**, so person cut-outs ("floor is lava", background swap) and distance-based effects become practical earlier than planned (D5 gets easier).
- Frames and RGB-aligned depth come from the same device clock, which helps keep video and keypoints in sync (D2).

## 3. System overview

```
 Luxonis OAK camera
     │ USB3 (RGB + depth, optional on-device pose)
     ▼
┌─────────────────────────── NUC (one machine) ───────────────────────────┐
│                                                                         │
│  Vision service (Python)                                                │
│  ┌─────────┐   ┌──────────────┐   ┌───────────────┐   ┌─────────────┐   │
│  │ Capture │──▶│ Pose / person│──▶│ Tracker       │──▶│ Publisher   │   │
│  │ (OpenCV)│   │ model (ONNX) │   │ (stable IDs,  │   │ (WebSocket) │   │
│  └─────────┘   └──────────────┘   │  smoothing)   │   └──────┬──────┘   │
│                                   └───────────────┘          │          │
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

Three processes, one machine: the **vision service**, the **display app** (a web page shown fullscreen), and the **control app** (another web page, used from a phone).

## 4. Key decisions

| # | Decision | Why | Alternative rejected |
|---|----------|-----|----------------------|
| D1 | **Split perception (Python) from rendering (browser).** | Python has the best model runtimes (OpenVINO/ONNX) for the NUC's Intel GPU. The browser has the best tools for fast 2D/3D drawing, and art people already know them. A clean JSON boundary lets us swap either side. | All-in-one browser app with MediaPipe JS: simpler, but weak on multi-person tracking, harder to tune on a NUC, and locks us to one model stack. |
| D2 | **Video frame and body data travel in the same WebSocket message.** | The effect is always drawn on the exact frame it was computed from, so costumes never lag or drift against the video. | Sending video via WebRTC and landmarks separately: needs sync logic and adds complexity for no gain on localhost. |
| D3 | **Effects are plugins** (a folder with `manifest.json`, art, and an optional `effect.js`). | Kids' favourites come and go. Most costumes are just "attach this image to that body point", which needs no code. | Hard-coding each costume. |
| D4 | **Pose model: MediaPipe Pose or MoveNet, exported to ONNX/OpenVINO, behind a `PoseEstimator` interface.** | Both are small and fast on CPU/iGPU. The interface lets us benchmark and swap. | A heavy model (e.g. YOLO pose large): more accurate but risks missing the frame budget on a NUC. |
| D5 | **Pose first, segmentation later.** | Costumes (hats, capes, masks) only need keypoints. Background replacement and "player cut-out" games need a person mask, which we add as an optional second model. | Starting with segmentation: more costly, not needed for the first fun result. |
| D6 | **Local only, no persistence.** | Child privacy. The server binds to the LAN only and stores no frames. | n/a |

## 5. Components

### 5.1 Vision service (`backend/`, Python 3.12, FastAPI + uvicorn)

Runs a loop in a worker thread and exposes a small server.

| Module | Responsibility |
|--------|----------------|
| `capture/` | `FrameSource` interface. Implementations: `OakCamera` (DepthAI; frames, optional depth and on-device keypoints), `UvcCamera` (generic webcam fallback), `VideoFile` (replay a clip for development), `Synthetic` (moving dummy skeleton, so the UI can be built with no camera). |
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
  "timing_ms": { "capture": 3, "pose": 14, "track": 1 }
}
```

Keypoints use one fixed topology (COCO-17 as the common subset), with named indices exported to the frontend so effects say `K.NOSE`, `K.LEFT_SHOULDER` instead of numbers.

WebSocket `/ws/control` JSON messages: `set_effect`, `set_setting`, `state` (server → all clients, so phone and TV stay in sync).

Other endpoints: `GET /` (display), `GET /control`, `GET /health`, `GET /metrics`.

## 7. Performance budget (target 30 fps, ≤150 ms glass-to-glass)

| Stage | Budget |
|-------|--------|
| Camera exposure + USB | ~40 ms (largely fixed by the camera) |
| Pose inference (720p downscaled to model size) | ≤ 20 ms |
| Tracking + smoothing | ≤ 2 ms |
| JPEG encode + WebSocket (localhost) | ≤ 8 ms |
| Browser decode + draw effects | ≤ 10 ms |
| TV display | ~20–50 ms (turn on "Game Mode" on the TV) |

Rules to keep this: capture at 720p, run the model on a smaller copy; always process the latest frame and drop the rest; inference on OpenVINO (Intel iGPU) if CPU is not enough; measure every stage and expose it in `/metrics`. We benchmark the chosen camera and NUC before committing to a model.

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
│   │   ├── capture/  vision/  tracking/
│   │   ├── pipeline.py  server.py  protocol.py  config.py
│   └── tests/
├── frontend/
│   ├── display/        # TV page
│   ├── control/        # phone page
│   ├── shared/         # protocol decoding, keypoint names, drawing helpers
│   └── effects/        # one folder per costume/game
├── models/             # downloaded model files (git-ignored, fetched by a script)
├── deploy/
│   ├── kidsar.service          # systemd: start vision service on boot
│   └── kiosk.sh                # launch Chromium fullscreen on the TV
└── scripts/            # setup-nuc.sh, download-models.sh, benchmark.py
```

## 9. Deployment on the NUC

- Ubuntu 24.04, Python venv, install with one `scripts/setup-nuc.sh`.
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
| Camera auto-exposure/auto-framing fights us | Lock exposure and framing in camera settings; document the recommended setup. |
| Privacy | Local only, no recording, bind to LAN, no outbound calls. |

## 12. Proposed milestones

1. **M0, skeleton:** repo layout, protocol, `Synthetic` camera, display page drawing a fake skeleton with one hat. Runs anywhere.
2. **M1, real camera + pose:** OAK capture, real pose model, tracker, hat follows a real kid on the TV.
3. **M2, costume system:** manifest-driven attachments, control page, 4–5 costumes (cap, cape, mask, ...).
4. **M3, NUC appliance:** systemd + kiosk, boots straight into the game.
5. **M4, games:** reactive effects, then segmentation-based games.

## 13. Open questions (remaining)

1. OAK repo details (see "Pending: OAK repo link" in section 2).
2. Exact OAK model, so I can size the on-device pose model.
3. Whether the phone remote should stay in M2 or move later (currently after the keyboard-only v1).

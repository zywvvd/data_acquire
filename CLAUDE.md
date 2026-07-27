# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`data_acquire/camera/` is a small set of **standalone Python scripts** that grab JPEG frames from a Hikvision (海康) IP camera at `192.168.2.2` to collect calibration images. There is no package, build system, or test suite — each file is run directly with `python3`. The reusable capture logic lives in `sdk_grabber.py` (`HikGrabber`); the other files are demos, probes, and a batch CLI built on top of it.

The reference design doc these scripts implement is **`../camera-cali/海康相机取图方式总览.md`** ("Hikvision image-acquisition overview"). `data_acquire/camera/` is the refactored, reusable distillation of the older acquisition code that still lives in `../camera-cali/capture/` (which has its own git repo + README + `core/`).

## Running the scripts

Use the **anaconda `python3`** (`/home/vvd/anaconda3/bin/python3`) — it has `requests`, `opencv-python`, etc. The machine also has a bare `python3.14` (uv-managed, no deps) that VSCode's Python Environments extension auto-selects by default; running from VSCode without setting the env to anaconda will fail with `ModuleNotFoundError`. From a terminal, plain `python3` is correct.

The SDK-based scripts (`sdk_grabber.py`, `grab_via_sdk.py`, `batch_capture.py`, `compare_jpeg_quality.py`) load `libhcnetsdk.so` via ctypes and need the SDK's shared libraries on the linker path:

```bash
export LD_LIBRARY_PATH=/home/vvd/Projects/code-shop/camera-cali/EN-HCNetSDKV6.1.9.4_build20220412_linux64/lib
python3 camera/batch_capture.py -n 20 -i 1.0          # auto: 20 frames, 1s apart
python3 camera/batch_capture.py -n 10 --interactive    # press Enter before each (manual board placement)
python3 camera/batch_capture.py -n 30 -i 2 -o data     # custom output root
```

The HTTP/ISAPI and OpenCV/RTSP scripts (`grab_via_http.py`, `grab_via_opencv.py`, `verify_ports_auth.py`) need **no** `LD_LIBRARY_PATH` — only `requests` / `cv2`.

`batch_capture.py` must be run such that it can `import sdk_grabber` (it inserts its own directory into `sys.path`, so `python3 camera/batch_capture.py …` or `cd camera && python3 batch_capture.py …` both work).

## Architecture: the three acquisition layers

The scripts exist to compare three independent ways to get a frame out of the same camera. Each has different latency, JPEG provenance, and dependencies — pick deliberately:

| Layer | Script | Encoding | Depends on |
|---|---|---|---|
| **SDK** (ctypes → `libhcnetsdk.so`) | `grab_via_sdk.py`, `sdk_grabber.py` | device-side JPEG (`NET_DVR_CaptureJPEGPicture`) | HCNetSDK libs + `LD_LIBRARY_PATH` |
| **HTTP / ISAPI** | `grab_via_http.py` | device-side JPEG (`GET /ISAPI/Streaming/channels/{ch}/picture`, HTTP Digest) | `requests` only |
| **RTSP via OpenCV** | `grab_via_opencv.py` | host-side re-encode by ffmpeg/OpenCV (`IMWRITE_JPEG_QUALITY=95`) | `opencv-python` + ffmpeg backend |

For **calibration, prefer the SDK or ISAPI layer** — both yield device-encoded JPEGs (the RTSP path decodes and re-encodes on the host, which can soften the image). `compare_jpeg_quality.py` exists to quantify the SDK quality-level (`wPicQuality` 0/1/2) vs ISAPI size difference in one login session.

**Channel numbering differs by layer and is a common bug source:** logical device channel `1` for the SDK (`NET_DVR_CaptureJPEGPicture`) vs RTSP/ISAPI stream id `101` (main) / `102` (sub). Calibration uses the **main stream (101)** only; `102` is for comparison.

### `HikGrabber` (the one reusable piece)

`sdk_grabber.py` wraps the SDK into a context manager that logs in once and captures many frames — the per-frame path that matters for batch collection:

```python
with HikGrabber() as g:        # loads SDK, sets component/ssl paths, inits, logs in
    g.capture("a.jpg")         # returns latency in ms; raises RuntimeError on failure
```

It hides the boilerplate repeated in `grab_via_sdk.py` (struct definitions, `NET_DVR_SetSDKInitCfg` for `HCNetSDKCom`/`libcrypto`/`libssl` paths, login, logout, cleanup). When touching SDK call sequences, update `HikGrabber` and keep the standalone `grab_via_sdk.py` demo in sync — they intentionally mirror each other.

## Conventions & gotchas

- **Output layout** (`batch_capture.py`): each run makes a per-second folder under the output root, each frame named to the microsecond — `captures/YYYYMMDD_HHMMSS/YYYYMMDD_HHMMSS_ffffff.jpg`. Both are sortable and unique within a batch.
- **Hardcoded absolute SDK path** in every SDK script: `camera-cali/EN-HCNetSDKV6.1.9.4_build20220412_linux64/lib`. The SDK dir is a sibling of this module's parent; moving either breaks the import. The `lib/` dir must contain `libhcnetsdk.so`, `HCNetSDKCom/`, `libcrypto.so.1.1`, `libssl.so.1.1`, `libPlayCtrl.so`.
- **Camera credentials are hardcoded** in each script (host `192.168.2.2:8000`, user `admin`, password `b@light2.`). When changing one, change all of them — there is no shared config module. (Note the password contains `@`; the RTSP URL in `grab_via_opencv.py` URL-encodes it as `%40`.)
- Latency is measured with `time.monotonic()` (not wall clock) — keep that when adding instrumented paths.

## Workspace context

This module sits inside `/home/vvd/Projects/code-shop`, a meta-workspace whose **git repo tracks only documentation/planning artifacts** (`.planning/codebase/*` maps the broader `boeye_alg` / `bolight_alg` systems; `docs/projects-show/` holds PPT content for several projects). The project subdirectories around this one — `camera-cali`, `boeye_alg`, `bolight_alg`, `ADC`, `JS6000`, `Nozzle`, etc. — are **independent working trees**, several with their own nested git repos, and are untracked by the parent repo. `data_acquire/` itself is currently untracked. Treat each subdirectory as its own project; don't assume cross-directory tooling.

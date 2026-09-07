# Project status

Where the INA700 build stands, what is blocked on what, and which numbers are
still placeholders. Updated as work lands.

Author: Suraj Karki
Course: INA700 - AI-based pick and place

**Last updated:** 7 September 2026

---

## Summary

The software is complete and tested. The dataset is shot. Nothing is trained
yet, and every number that needs the robot is still a placeholder.

| Phase | State |
|---|---|
| Architecture and code | **Done** — 59 modules, 59 tests green |
| Robot programs | **Done** — proven on hardware for the minimal exercise |
| Camera and marker calibration (A1–A5) | **Done**, but the marker needs remounting |
| Dataset capture (Part B) | **Done** — 345 photos |
| Labelling (Part C) | **Done** — 271 images, 560 boxes, 43 hard negatives |
| Training (Part D) | **Done** — mAP50-95 0.826 on 55 held-out images |
| Robot measurements (A6–A11) | Not started — needs robot time ← *now the critical path* |
| Integration and demo | Blocked by both of the above |

---

## Done

### Software

Layered architecture — `domain` → `ports` → `application` → `adapters` →
`infrastructure`, dependencies pointing inward only, wired by a `Container`
composition root that reads `config.yaml`. Swapping the mock detector for the
trained one is a config edit, not a code change.

- **Vision.** `YoloDetector`, `HarmonicOrientationEstimator`, `HsvColourClassifier`.
- **Orientation** by the N-th harmonic of the radial outline rather than
  `minAreaRect`, whose 90° ambiguity fits a square and nothing else. Verified
  to 0.1° on analytic shapes, and to 1.5° median on real photos where
  `|Z| ≥ 0.10` (`tools/orientation_probe.py`).
- **Coordinates.** ArUco four-corner homography, refreshed every frame, so a
  nudged camera corrects itself rather than silently reporting stale positions.
- **Threading.** Capture / inference / connection / cycle workers with bounded
  queues; Tkinter on the main thread; shared state behind an `RLock` handing out
  immutable snapshots.
- **Protocol.** `move <shape> <x> <y> <angle>#` → `DONE: <shape>#`, length-guarded
  against the 80-character RAPID `string` limit.

### Robot

`StationData.mod` (taught values) and `MainModule.mod` (logic), both proven on
real hardware for the minimal exercise. Two work objects, five `robtarget`s plus
approach and home, yellow-button start, vacuum on a digital output. The picking
fence derives from one measured A3 corner, so re-teaching `wobj1` costs two
numbers instead of four.

### Calibration

Camera found and fixed manually: Basler acA2440-75uc, exposure 3000 µs, gain 0.
Marker detected in 15/15 frames at **3.638 px/mm, jitter 0.0010** — well inside
the 0.02 gate. Field of view 673 × 563 mm.

### Model

Trained on 216 images, validated on 55 held out:

| Class | Instances | P | R | mAP50 | mAP50-95 |
|---|---|---|---|---|---|
| all | 114 | 0.962 | 0.905 | 0.985 | **0.826** |
| circle | 31 | 1.000 | 0.943 | 0.995 | 0.828 |
| square | 32 | 1.000 | 0.792 | 0.983 | 0.819 |
| star | 51 | 0.886 | 0.980 | 0.977 | 0.831 |

Square misses about one in five; star over-fires about one in nine. Detection
confidence sits at 0.6 rather than 0.5 because a forbidden shape reaching the
robot is worse than a missed pick.

### Dataset

345 photos: circle 74, square 38, star 54, hexagon 55, triangle 52, mixed 72.
271 of them labelled: 560 boxes and 43 empty hard negatives.
The 72 mixed scenes carry 6–8 objects each with all five shapes together, which
is what teaches the model to ignore hexagon and triangle. Two lighting
conditions are represented.

Label set built and waiting: **280 images** at 1280 px in
`model/dataset/label/images/`, with 42 empty hard negatives sampled across the
brightness range.

### Tooling

| Tool | Does |
|---|---|
| `tools/preflight.py` | Packages, camera, config, marker, lighting — one gate before any session |
| `tools/capture_gui.py` | Live preview, per-scene capture, resumable numbering |
| `tools/build_label_set.py` | Assembles the label set with a hard-negative budget |
| `tools/split_dataset.py` | Validates labels, then a stratified train/val split |
| `tools/orientation_probe.py` | Angle accuracy on real photos, no labels needed |
| `calibration/aruco_check.py` | Live px/mm and jitter |
| `calibration/slot_angles.py` | Measures the placing slot angles |
| `model/train_yolo.ipynb` | Colab training and NCNN export |

---

## Not done

### Critical path — labelling, then training

Nothing downstream can start until the 280 images are labelled. About 3 hours;
the mixed scenes are the slow ones. `PROCEDURE.md` Part C has the steps, and
`split_dataset.py` is the gate that catches a bad export before it wastes a
training run.

### Numbers still at placeholder values

| Value | Where | Needs |
|---|---|---|
| `SHEET_ORIGIN_X / Y` | `robot/StationData.mod` | Jog to the A3 corner (A6) |
| `PICK_SURFACE_Z_MM` | `robot/StationData.mod` | Teach one pick point (A11) |
| `marker_centre_xy_mm` | `pi/config/config.yaml` | Jog to the marker centre (A6) |
| `marker_angle_deg` | `pi/config/config.yaml` | Measure if not square to `wobj1` |
| `place_slot_angles_deg` | `pi/config/config.yaml` | `slot_angles.py` (A10) |
| `verify_tolerance_mm` | `pi/config/config.yaml` | Set 10–15 for the lab |

### Config still on the offline profile

`detector.kind: mock` and `robot.transport: loopback`. Both switch when the
trained weights and the robot are available.

---

## Open risks

**The marker is a printed paper sheet, not the 100 mm rubber one.** It is
wrinkled and lying in the middle of the A3, where objects land. It eats picking
area, and a curling edge is what makes px/mm drift between sessions. Every
robot-side number inherits this, so remount before booking robot time.

**Lighting is uncontrolled.** Sheet brightness ranged 67–162 across sessions at
fixed exposure. `preflight.py` now reports it and gates on 180–210; reproduce
the bright condition at demo time.

**Square is under-represented** at 38 photos, because two colours are missing.
Watch its recall in the confusion matrix — it will degrade first.

**Nothing is under version control.** A `git init` would make the next
refactor reversible.

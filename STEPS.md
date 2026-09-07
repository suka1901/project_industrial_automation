# Steps

Everything practical, in order. Each part says what to run, what you should see,
and what to do when you do not see it.

`README.md` explains why the system is built the way it is. This file is for
sitting at the desk or standing at the station.

Author: Suraj Karki
Course: INA700 — AI-based pick and place

**Contents**

1. [Testing with no hardware](#1-testing-with-no-hardware)
2. [Camera and marker calibration](#2-camera-and-marker-calibration)
3. [Robot measurements](#3-robot-measurements)
4. [Running on the Raspberry Pi](#4-running-on-the-raspberry-pi)
5. [Rebuilding the dataset and model](#5-rebuilding-the-dataset-and-model)
6. [Lab plan — the order, and the gate for each session](#6-lab-plan)

---

# 1. Testing with no hardware

Everything here runs from saved photos on any machine. Do all of it before
touching the station — a failure here is far cheaper to find.

## 1.1 Setup

VS Code's status bar must say **opencv_env**.

```powershell
conda activate opencv_env
pip install -r pi/requirements.txt
```

## 1.2 Unit tests

```bash
cd pi
python -m unittest discover -s tests
```

**Expect:** `Ran 68 tests` and `OK`. These need no camera, no model, no robot.

| Problem | Fix |
|---|---|
| `No module named cv2` | Wrong interpreter selected in VS Code |
| `opencv ... has no aruco` | You have plain `opencv-python`; install `opencv-contrib-python` |

## 1.3 Mock end to end

**Run and Debug → `6 - Smoke test (mock, no model)`**

**Expect:** two cycles reporting SUCCESS with synthetic detections. This proves
the threading, the selectors, the protocol and the cycle controller without
involving the model at all.

## 1.4 The trained model against saved photos

**Run and Debug → `7 - Smoke test (trained model, saved photos)`**

**Expect:**

```
cycle 1: SUCCESS in 1 attempt(s) -> CIRCLE GREEN x=355.6 y=228.2 rz=0.0
  move circle 355.56 228.16 0.0#   (30 chars, RAPID limit 80)
```

The first inference takes **20–30 seconds** while the model loads, then settles
near 120 ms. That is not a hang.

**A FAILED cycle here is usually not a fault.** The replay walks the photos in
name order, and 9 of the 55 are hard negatives — hexagon and triangle only. Land
on those and the model correctly reports nothing, so the cycle has nothing to
pick. The printed reason says which:

```
cycle 2: FAILED in 3 attempt(s)   [no object matched the request]
```

`no object matched the request` on those photos is the hard negatives working.
Judge detection quality with §1.5, not with two cycles of a replay.

| Problem | Fix |
|---|---|
| `capture crashed: No device is available` | You ran the **lab** profile. Add `--config config/profiles/offline.yaml` — the default expects a camera |
| `No module named ultralytics` | `pip install ultralytics` |
| `FileNotFoundError: ../model/best.pt` | Unpack the trained model into `model/` |
| FAILED, 0 detections | Still loading — the wait is capped at 120 s |
| `Frame directory not found` | Run `python tools/split_dataset.py` first |

Running it without `--config` uses `config.yaml`, the **lab** profile: real
camera, real robot. That is deliberate — the profile that runs the station
should be the default. Every offline command in this file passes `--config`.

## 1.5 Score the whole pipeline — the one worth reading

**Run and Debug → `8 - Offline check (whole pipeline vs labels)`**

Ultralytics only grades the detector. This grades what the robot is actually
told: shape, colour, and whether the angle was measurable.

**Expect, on the current model:**

```
objects   matched 99   missed 15   spurious 2   of 114 labelled
recall 0.868   precision 0.980
whole photo exactly right: 41/55

colour: {GREEN 9, WHITE 29, BLACK 18, BLUE 30, RED 15}

angle confidence |Z|, gate at 0.1:
  CIRCLE  n= 25  median 0.000  (no orientation to measure)
  SQUARE  n= 23  median 0.145  below gate: 1
  STAR    n= 53  median 0.210  below gate: 5
```

| What to watch | Why it matters |
|---|---|
| Any `UNKNOWN` colour | Every object should get a name |
| `spurious` climbing | Shapes reported that are not there — raise `detector.confidence` |
| Many below the gate | Outlines too weak — light, focus or glare |
| `recall` falling | Lower `detector.confidence`, accepting more spurious reports |

`config/profiles/offline.yaml` differs from the lab profile in exactly three ways:
photos instead of a camera, the identity mapper because most saved photos have
no marker in frame, and a loopback robot that always answers DONE. The detector,
orientation estimator and colour classifier are the real ones.

---

# 2. Camera and marker calibration

Allow about two hours the first time. Steps 2.1–2.5 need no robot.

## 2.1 Mount the marker

1. Fix the **100 mm rubber marker** flat, well inside the frame and **clear of
   where objects land**.
2. **Shim it so its face is level with the top of the objects.** They are all
   the same thickness, so one shim does it.
3. Press every edge down. No lifted corners, no curl.
4. Put objects on the sheet and confirm none can cover it.

**Why the shim.** The homography maps onto the plane the marker lies in, and the
camera sees the objects' *top* faces. Calibrate on the board and every object is
reported outward by about `r·h/H` — roughly 2 mm for 10 mm objects 150 mm off
centre under a camera 800 mm up. Worst at the corners, and it looks like lens
distortion except that it points outward.

| Problem | Fix |
|---|---|
| Marker near the frame edge | Move it inward — distortion is worst at the edges |
| A corner lifts | Tape or re-seat it, or the calibration jitters |
| Objects land on it | Re-site it, or mark a keep-clear zone |

## 2.2 Aim and focus

Point the camera so the **whole A3 sheet plus the marker** are in frame with a
margin. Focus on an **object's top surface**, not the bare table. Tighten every
clamp.

**Expect:** objects at all four corners in frame and sharp; tapping the bench
does not shift the image.

> After this, **do not move the camera.** If you must, redo from 2.5.

## 2.3 Exposure

In Pylon Viewer: **auto-exposure off**, **auto-gain off**. Set exposure so the
sheet is bright without blowing out. Keep gain low. Write both numbers down.

`preflight.py` reports this as `lighting`: the 95th percentile of the frame,
which is the sheet. **Target 180–210**, nothing clipped. Below 150 the objects
sit in too little range and their edges soften.

## 2.4 Write the config

In `pi/config/config.yaml`: `camera.exposure_us`, `camera.gain`,
`aruco.marker_length_mm: 100.0`, `coordinates.mapper: aruco`.

## 2.5 The calibration gate

```bash
cd pi
python tools/preflight.py
python calibration/aruco_check.py --length 100 --camera basler
```

Watch the jitter for a **full minute**.

**Expect:** ID `0` in every frame, **jitter below 0.02 px/mm**.

| Problem | Fix |
|---|---|
| Not detected | Wrong dictionary, or cut off at the frame edge. Confirm DICT_5X5_100 |
| Drops frames | Not enough light, or motion blur from a vibrating mount |
| Jitter above 0.02 | In order: kill glare, refocus, add light |
| Fine, then spikes | Something intermittently shadows it — usually the operator leaning in |

**Do not book robot time until this passes.** Everything after inherits it.

---

# 3. Robot measurements

## 3.1 (A6) Locate the marker in `wobj1`

Keep the work object you have; just tell the vision system where the marker sits
inside it.

1. Jog the tool tip to the **marker centre**.
2. Read work-object **X** and **Y** off the pendant.
3. Put them in `aruco.marker_centre_xy_mm`.
4. If the marker is not square to `wobj1`'s X axis, measure that angle into
   `aruco.marker_angle_deg`.

| Problem | Fix |
|---|---|
| Hard to touch the centre precisely | Get close — an error here is a uniform shift, which 3.2 catches |
| Tempted to re-teach `wobj1` at the marker | Then it is `[0, 0]`, but moving `wobj1` also shifts `Papproach`, `PICK_SURFACE_Z_MM` and the sheet origin. Not worth it against a proven work object |

## 3.2 (A7) Verify the mapping — the gate

Put one object down, read X and Y from the GUI, jog there and compare. Repeat at
**three well-separated spots, including a corner**.

**Expect:** agreement within **1–2 mm everywhere**.

| What you see | What it means |
|---|---|
| Centre good, corners out | Lens distortion — move the marker more central |
| All off by the same amount | `marker_centre_xy_mm` is wrong — fix those two numbers |
| All off by the same *percentage* | `marker_length_mm` is wrong |
| Error grows outward | The marker is not at object-top height — go back to 2.1 |
| X and Y swapped or rotated | `marker_angle_deg` is wrong |
| Y has the wrong sign | Go to 3.3 |

## 3.3 (A8) Resolve `y_axis_flipped`

Place an object clearly off-centre in **+Y** and check the sign the GUI reports.
If negative, set `aruco.y_axis_flipped: true` and re-check.

## 3.4 (A9) Resolve `angle_sign`

Place a **square** deliberately at about 45°, send one pick, watch how it seats.

| What you see | Fix |
|---|---|
| Rotated the wrong way by twice the error | Flip `coordinates.angle_sign` |
| Close but off by a fixed amount | The slot angle is wrong — do 3.5 |
| Circle fine, everything else wrong | Almost always `angle_sign` |

## 3.5 (A10) Teach `wobj2` and the slot angles

Teach the placing work object at the jig and confirm `p10`–`p60` still land in
their slots. Then for each shape: seat it **in its slot**, lift it **straight
out without turning it**, set it on the picking sheet, and read it with:

```bash
python calibration/slot_angles.py --camera basler
```

`1`–`5` picks the shape, `SPACE` records, `s` saves.

**Expect:** each reading settles below **0.5° spread** before it lets you
record. Paste the saved block into `coordinates.place_slot_angles_deg`.

| Problem | Fix |
|---|---|
| Will not settle | Same causes as 2.5 — glare, focus, light. A star is the most sensitive |
| Star reads wildly | Thin points eroded by thresholding — raise the light, check `padding_px` |
| Circle refuses an angle | Correct. A circle has no orientation; it records 0 |

## 3.6 (A11) The remaining numbers

In `robot/StationData.mod`:

- `SHEET_ORIGIN_X` / `SHEET_ORIGIN_Y` — jog to the corner of the A3 sheet
  nearest `wobj1`'s origin and read X and Y. The four `PICK_AREA_*` bounds derive
  from these.
- `SHEET_SPAN_X` / `SHEET_SPAN_Y` — swap the two if the long edge runs along Y.
- `PICK_SURFACE_Z_MM` — teach one pick point with an object under the cup, read Z.

In `pi/config/config.yaml`: `robot.verify_tolerance_mm: 15.0`.

---

# 4. Running on the Raspberry Pi

The Pi is set up in the lab, so this is a normal deployment.

## 4.1 Benchmark first

```bash
cd INA700/pi
python3 tools/benchmark.py --config config/profiles/pi.yaml
```

**No camera, no robot** — saved photos only. Two minutes, and it answers the one
question that can sink the demo.

```
model load and warm-up: 18.4 s
per frame   median 780 ms   worst 910 ms   budget 3000 ms
PASS - worst case is under 1800 ms, comfortably inside budget
```

| Result | Do |
|---|---|
| PASS | Carry on |
| TIGHT | Usable; re-export at 480 for headroom when convenient |
| FAIL | Re-export NCNN at 480. The input size is fixed **at export**, so editing `image_size` alone does nothing |

Write down the warm-up figure — the system really is unavailable that long at
start-up. **Re-run this after every retrain.**

## 4.2 Camera

```bash
python3 tools/preflight.py --config config/profiles/pi.yaml
```

| Problem | Fix |
|---|---|
| `no Basler camera detected` | USB3 port and cable — the Pi's USB2 ports will not carry this camera |
| `pypylon not installed` | Pylon SDK for **ARM64**, then the pypylon wheel |
| `No module named 'ncnn'` | `pip install ncnn` — the Pi profile needs it, a laptop using `best.pt` does not |
| `tkinter` fails | `sudo apt install python3-tk` |

## 4.3 Network and run

Set `robot.host` in `config/profiles/pi.yaml` to the Pi's own address on the robot
network, and confirm the robot reaches it.

```bash
python3 main.py --config config/profiles/pi.yaml
```

The GUI needs a display — the station monitor, or VNC.

## 4.4 Watching it work

`main.py` shows a live view beside the numbers: the newest frame with a box and
a confidence round every detection, refreshed as fast as inference produces
frames. Use it to confirm at a glance what the numbers cannot tell you —
whether a hexagon is being boxed, whether an object near the sheet edge is
being missed, whether the marker is in view.

The frame and the boxes are published as one value, so the panel can never
draw one frame's boxes over another frame's image.

To watch it with no camera, run the offline profile: the same view replays the
saved photos.

```bash
python main.py --config config/profiles/offline.yaml
```

## 4.5 Fallback

If the Pi fails, the same code runs on the laptop with
`python main.py --config config/config.yaml`. The profiles differ only in
`model_path` and `transport`. Keep the laptop tested so the option stays real.

---

# 5. Rebuilding the dataset and model

Only needed if you reshoot photos or change the classes.

## 5.1 Capture

```bash
cd pi
python tools/capture_gui.py
```

Scenes are the five shapes plus **Mixed**. Full-resolution frames land in
`model/dataset/raw/<scene>/`, numbered and resuming across sessions.

Shoot **200–300** photos, varying position across the whole sheet, rotation
through a full circle, spacing, company, and lighting across at least two
sessions. Crucially, put the **two forbidden shapes in the photos** and leave
them unlabelled — that is what teaches the model to ignore them.

## 5.2 Build the label set

```bash
python tools/build_label_set.py
```

Writes 1280 px JPEGs into `model/dataset/label/images/` with a hard-negative
budget, and `manifest.csv` beside them. It downscales because the camera's
frames are 6 MB each and the network trains at 640 anyway.

**This rebuilds the folder from scratch, so it refuses to run once labels
exist** — pass `--rebuild` if you really mean it. Even then, every photo that
already has a label is kept, and `excluded.txt` lists photos deliberately left
out so a rebuild cannot reinstate them. Labels and annotations are never
touched, and neither is the model.

## 5.3 Label

```powershell
pip install label-studio
$env:LABEL_STUDIO_LOCAL_FILES_SERVING_ENABLED = "true"
$env:LABEL_STUDIO_LOCAL_FILES_DOCUMENT_ROOT = "C:\Users\suraj\Desktop\INA700\model\dataset\label"
label-studio start
```

Both variables must be set **before** Label Studio starts, in the same shell.

1. **Create Project** → `INA700`.
2. **Settings → Labeling Interface → Code** → paste `model/label_config.xml`.
3. **Settings → Cloud Storage → Add Source Storage → Local files**: path
   `...\label\images`, regex `.*\.jpg`, **Treat every bucket object as a source
   file ON**. Sync.
4. **Settings → Cloud Storage → Add Target Storage → Local files**: path
   `...\label\annotations`. This writes annotations to disk as you work.

Then **Label All Tasks**. Pick the label first (`1` `2` `3`), then drag. Submit
with `Ctrl+Enter`.

| Rule | Why |
|---|---|
| **Submit, never Skip** | Skip records a cancelled annotation that does not export — a skipped negative teaches nothing |
| Box the whole star, points included | A clipped box trains a smaller object than the model will meet |
| Box tight, no surrounding paper | The orientation estimator thresholds inside this box |
| Never box a hexagon or triangle | This is the entire hard-negative strategy |
| Submit empty photos with no boxes | The empty label file is the signal |

| Problem | Fix |
|---|---|
| Import stops at 100 | Browser upload caps there — use local storage, above |
| Sync gives 1 task | "Treat every bucket object as a source file" was off |
| Tasks exist, no image | Local files serving was not enabled when the server started |
| Predictions not visible | **Settings → Annotation** — the project's model version must match the predictions' |

## 5.4 Export and split — the gate

```bash
python tools/labels_from_export.py
python tools/split_dataset.py
```

**Expect** a class table and the path to `data.yaml`. Anything else is a problem
list, and it exits without writing.

| It says | What happened |
|---|---|
| `class order mismatch` | `classes.txt` disagrees with `detector.class_map`. Training would succeed with every shape mislabelled and nothing would crash |
| `boxes N and M overlap at IoU 1.00` | One object boxed twice — a double-drag |
| `missing` | A photo was never submitted. An empty one still must be |
| `coordinates not normalised` | Wrong export format — YOLO, not COCO |

## 5.5 Train

Zip `model/dataset/yolo`, open `model/train_yolo.ipynb`, set **Runtime → T4
GPU**, upload, work down the cells.

**Stop at the cell that draws the boxes and look at them.** A box in the wrong
place there is a labelling error, and no amount of training repairs it.

| Look at | Want |
|---|---|
| `mAP50-95` | The honest number. `mAP50` saturates near 0.98 and cannot discriminate |
| Confusion matrix, `background` column | Hexagons and triangles should land here |
| Per-class recall | Square degrades first — it has the fewest photos |

Unpack the download into `model/`, then re-run §1.5 and §4.1.

## 5.6 Pre-annotate the rest (optional)

With a model trained on part of the set, `python tools/prelabel.py` proposes
boxes for the unlabelled photos and writes Label Studio **predictions** — never
annotations, so a guess cannot pass itself off as your work.

---

# 6. Lab plan

Each session ends on a **gate**: a measurable condition. If it does not pass,
the session is not finished, and the next one would build on sand.

## Session 1 — Foundation

Bench and Pi. Steps 2.1–2.5 and 4.1.

**Gate:** ID 0 in every frame with **jitter below 0.02 px/mm** held for a full
minute, and `benchmark.py` reporting PASS or TIGHT.

> Do not book robot time before this passes.

## Session 2 — The work object

Robot needed. Steps 3.1, 3.2, 3.6.

**Gate:** agreement within **1–2 mm at three well-separated spots, including a
corner**. Error growing outward means the marker is not at object-top height —
go back to 2.1 rather than accepting it.

## Session 3 — Signs and angles

Robot needed. Steps 3.3, 3.4, 3.5.

**Gate:** a square deliberately placed at 45° seats cleanly in its slot.

## Session 4 — Full rehearsal

Everything connected, on the Pi, exactly as at the exam.

- `profiles/pi.yaml`, `verify_tolerance_mm` 10–15
- Six objects on the sheet, hexagons and triangles among them
- Two complete cycles, all three shapes each, chosen by operator input
- Inference time printed each cycle, under 3 s
- A hexagon or triangle is **never** picked

**Gate:** two cycles, six objects, at least five placed with the correct
orientation — the Grade Level III criterion, met without intervention.

### Placing the objects so the angle can be measured

Two things make an outline unreadable, and both are avoidable at the bench:

| Do | Why |
|---|---|
| Keep objects **well inside the sheet**, not near its edge | The dark table gets into the detection box and the thresholding merges object and table into one blob. Three of the six refusals on the held-out set were this |
| Prefer **coloured objects over white** where you have the choice | A white object on white paper has no boundary to find; the mask latches onto internal shading and breaks into facets |
| Light so the object casts a **visible shadow edge** | For a pale object that shadow is the only boundary there is |

An object marked **NO ANGLE** is still picked and placed, just not turned, and
a banner names it. That is the default because the assignment requires every
object to be picked in each cycle and allows one of six to be misoriented.

If placement accuracy matters more on the day, set
`orientation.on_low_angle_confidence: skip` and it will be left on the board
instead.

## Afterwards

1. Re-shoot the underexposed photos — roughly half the set has the sheet at
   67–86 where it should read 180–210. Retrain and compare `mAP50-95`.
2. Re-run §1.5 and §4.1 after any retrain.
3. **Pack-and-Go** from the station, for the ZIP.
4. Rehearse the presentation: why the angle comes from a harmonic rather than
   `minAreaRect`, and why the Pi and laptop profiles differ by two lines.

## What to record every session

- `preflight.py` output in full
- `aruco_check.py` px/mm and jitter
- `benchmark.py` result
- Every number written into a file, and where it came from
- Anything that surprised you

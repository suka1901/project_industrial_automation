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
inside it. Do not try to touch the centre directly — touch the four corners and
average them. The averaging cancels the sighting error, and the same four
readings check the marker size and squareness for free.

### Set the pendant up so the readout IS the config value

Manual mode, then **ABB menu → Jogging**, and set all three:

| Setting | Value |
|---|---|
| Coordinate System | `WorkObject` |
| Work Object | `wobj1` |
| Tool | `vac` |
| Motion mode | Linear |

The Position display now reads the cup's TCP in `wobj1` millimetres, so the
numbers go straight into config with no arithmetic.

> Confirm `Tool` says `vac` and not `tool0`. With `tool0` you are reading the
> flange, which is about 90 mm out in X and 178 mm in Z. Every reading still
> looks plausible and every one of them is wrong.

### Touch the four corners

Touch the **outer corners of the black square** — that is what the detector
reports, and it must be the same square `marker_length_mm` describes. Measure
that black edge with a ruler first and confirm it really is the 100 mm, not the
rubber tile it is printed on.

For each corner: jog above it, come down to **1–2 mm above the surface**, then
sight **straight down the cup axis** with your eye over it, not off to one side.
Use small increments for the last millimetre. Record X and Y.

| Corner | X | Y |
|---|---|---|
| 1 | | |
| 2 | | |
| 3 | | |
| 4 | | |

`marker_centre_xy_mm` is the average of the four X values and the average of the
four Y values.

Do not press the cup onto the surface. The rubber deforms, the arm settles, and
the reading moves — hovering is both safer and more accurate.

### Check before you trust it

| Check | Expect | If not |
|---|---|---|
| Each side, corner to corner | ≈ `marker_length_mm` | Consistently larger means you are sighting the outside of the border; consistently different means `marker_length_mm` is wrong |
| Each diagonal | ≈ 1.414 × the side | One diagonal off means a corner reading is bad — retake it |
| Two edges at constant Y, two at constant X | marker is square to `wobj1` | Straighten the marker and re-read rather than measuring `marker_angle_deg`; a zero there is one less thing to get wrong |

### Then let the camera correct you

This is what actually gets you under a millimetre, and it means the touching
only has to be roughly right. Run 3.2, and where the error is the **same at
every spot**:

```
new marker_centre = old marker_centre + (jogged − reported)
```

component-wise, because the mapping is a pure translation. One iteration
converges. If the error instead grows toward the corners, that is marker height,
not centre — see 3.2's table.

| Problem | Fix |
|---|---|
| Tempted to re-teach `wobj1` at the marker | Then it is `[0, 0]`, but moving `wobj1` also shifts `Papproach`, `PICK_SURFACE_Z_MM` and the sheet origin. Not worth it against a proven work object |
| Readings drift between corners | The arm is not settling. Pause a moment after each jog before reading |

Write down the raw corner readings, not just the averages. If 3.2 disagrees, the
raw numbers tell you whether it was the touching or the marker.

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
their slots.

**Position the jig so it is in the camera frame.** Then the angles are read
where the objects already lie, and nothing has to be lifted.

Seat every object in its own slot, then:

```bash
python calibration/slot_angles.py --camera basler
```

For each shape: press `1`–`5` to pick it, press `R` and **drag a box round that
slot**, wait for the reading to settle, press `SPACE`.

Then **lift the object out, seat it again, and press `SPACE` again — three
times at least.** A shape-matched slot still has play in it, and the spread
across seatings is the only honest measure of how much. The `0.5°` settle is
frame-to-frame camera noise; it says nothing about whether the slot repeats.

The tool refuses `SPACE` until it has seen the slot **empty** since the last
seating, and the readout says `LIFT THE OBJECT OUT` until then. Without that
it is easy to record one seating many times over: the reading re-settles to
the same value, and a `play` near 0.00° looks like a flawless slot while
meaning nothing.

`C` clears a shape to start it over. `S` saves.

**Expect:** `n=3` or more per shape, and `play` well under a tenth of that
shape's symmetry period. Paste the saved block into
`coordinates.place_slot_angles_deg`.

> The box matters. Without it the tool measures the biggest thing in frame,
> which is usually the jig plate itself or an object still lying on the sheet.
> The **blue** box is the region you drew; the **green** one is what was found
> and measured. If the green box is round the jig rather than the object, the
> reading will look perfectly steady and be the jig's angle.

| Problem | Fix |
|---|---|
| "no object in view" with the slot boxed | The box is on bare plate, or the object is not seated. An empty region is rejected rather than measured |
| Marked **LOOSE** | The play exceeds 10% of the symmetry period. Not fatal — that slack is also what forgives a sloppy arrival angle — but the placement has to tolerate it |
| Only `n=1` or `n=2` | Not enough seatings to judge the play at all. Seat it again |
| `play` of 0.00–0.02° | Not a perfect slot — a re-seat almost certainly did not happen. A hand-seated object cannot repeat to a hundredth of a degree; that is about 0.02 px at the object's edge |
| Will not settle | Same causes as 2.5 — glare, focus, light. A star is the most sensitive |
| Star reads wildly | Thin points eroded by thresholding — raise the light, check `padding_px` |
| Circle refuses an angle | Correct. A circle has no orientation; it records 0 |
| Window too big for the screen | Fixed — it fits to 908×760. `--display-width` to change it |

**If the jig cannot be brought into frame:** lift each object straight out of
its slot *without turning it*, set it on the picking sheet, and box it there.
Same tool, same keys. But your hand is now between the slot and the number —
any twist during the lift becomes a permanent error in a value every placement
of that shape depends on, and you will never see it, because the reading will
look perfectly steady.

The jig does not have to be in frame during a picking cycle — only while
measuring these angles.

## 3.6 (A11) The remaining numbers

In `robot/StationData.mod`:

- `SHEET_ORIGIN_X` / `SHEET_ORIGIN_Y` — **already 0, nothing to measure**, because
  `wobj1` was defined with its origin on the A3 corner. That makes the four
  `PICK_AREA_*` bounds exact rather than inherited from a jogged reading. Only
  if `wobj1` is ever re-taught somewhere else do these need measuring: jog to
  the sheet corner nearest the origin and read X and Y, pendant set up as in 3.1.
  1–2 mm is plenty there — the fence carries a 15 mm margin.
- `SHEET_SPAN_X` / `SHEET_SPAN_Y` — swap the two if the long edge runs along Y.
- `PICK_SURFACE_Z_MM` — teach one pick point with an object under the cup, read Z.

In `pi/config/config.yaml`: `robot.verify_tolerance_mm: 15.0`.

---

# 4. Running on the Raspberry Pi

The Pi is set up in the lab, so this is a normal deployment.

## 4.0 Getting the code across

There is no git remote, and the weights are gitignored anyway, so this is a
file copy. Copy the *bundle*, not the folder: the dataset is 2.6 GB and the Pi
needs 19 MB of it.

| The Pi needs | Why |
|---|---|
| `pi/` | the code, and `config.yaml` with every measured value in it |
| `model/best_ncnn_model/` | the detector. 2–3x faster than `best.pt` on ARM |
| `model/dataset/yolo/val/images/` | 55 photos, only so 4.1 can run without a camera |

| It does not need | |
|---|---|
| `model/dataset/raw/` and `label/` | 2.5 GB of training photos |
| `model/best.pt` | the Pi profile uses NCNN |
| `robot/`, `docs/` | the controller's files, and the diagrams |

On the PC, from the project root:

```bash
tar -czf ina700-pi.tar.gz \
  --exclude='__pycache__' --exclude='*.pyc' --exclude='pi/logs/*.log' \
  pi model/best_ncnn_model model/dataset/yolo/val/images
```

Then to the Pi, by network or on a stick. **Both of these run on the PC** —
the second hands its quoted string to the Pi's shell, so `&&` executes where
it is understood. Windows PowerShell 5.1 does not accept `&&` itself, and
pasting a Pi command into it fails to parse the whole block, so nothing runs
at all, including the line above it.

```powershell
scp ina700-pi.tar.gz pi@<pi-address>:~/
ssh pi@<pi-address> "mkdir -p ~/INA700 && tar -xzf ~/ina700-pi.tar.gz -C ~/INA700"
```

> **Rebuild the bundle after any change to `config.yaml`.** Every measured
> value travels inside it — marker centre, slot angles, exposure. A stale
> bundle is a Pi running yesterday's calibration, and nothing about it looks
> wrong.

Then log in and install what the Pi needs. **From here on every command runs
on the Pi**, not on the PC:

```bash
ssh pi@<pi-address>
sudo apt install python3-tk
pip install ncnn pyyaml opencv-python numpy pillow
# pypylon needs the ARM64 Pylon SDK first - see 4.2
```

**No ultralytics and no torch on the Pi.** `profiles/pi.yaml` uses
`detector.kind: ncnn`, which runs the exported model on the 12 MB ncnn runtime
directly. `kind: yolo` would load through ultralytics, and ultralytics needs
torch — whose aarch64 wheel bundles roughly 2 GB of NVIDIA CUDA libraries for
a board with no GPU. It fills the Pi's disk before it finishes.

> **The NCNN export must match the installed ncnn.** They are versioned by
> date and the exporter is bundled with ultralytics, so a model exported by an
> older ultralytics builds the wrong graph: `Concat` joins on the wrong axis
> and the run segfaults in `Slice`, two layers before the output, reporting
> nothing at all. Re-export on the PC whenever ncnn is upgraded:
>
> ```powershell
> python -c "from ultralytics import YOLO; YOLO('model/best.pt').export(format='ncnn', imgsz=640)"
> ```
>
> Then check `pip show ncnn` on the Pi matches the `NCNN 1.0.YYYYMMDD` line the
> export printed.

The Pi's admin address and its robot-network address are usually different
interfaces - wifi for logging in, ethernet for the robot. Only the second has
to be `192.168.125.201`; see 4.3.

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

`NcnnDetector` does by hand what ultralytics used to do around the model —
letterboxing in, then decoding, thresholding and non-maximum suppression out.
Measured against the labels on the 55 held-out photos:

| `detector.confidence` | recall | precision |
|---|---|---|
| 0.50 (the Pi default) | 92.1% | 96.3% |
| 0.60 (the PC default) | 88.6% | 97.1% |

Mean IoU of matched boxes is 0.907, which is the number that says the
letterbox transform is undone correctly — a wrong one shows up as boxes
offset or scaled, not as boxes missing.

## 4.2 Camera

```bash
python3 tools/preflight.py --config config/profiles/pi.yaml
```

| Problem | Fix |
|---|---|
| `no Basler camera detected` | USB3 port and cable — the Pi's USB2 ports will not carry this camera |
| `pypylon not installed` | Pylon SDK for **ARM64**, then the pypylon wheel |
| `No module named 'ncnn'` | `pip install ncnn` — the Pi profile needs it, a laptop using `best.pt` does not |
| `No module named 'ultralytics'` | The Pi should not need it. Check `detector.kind` is `ncnn`, not `yolo` |
| Segfault, or the run dies with no message | The NCNN export does not match the installed ncnn. Re-export — see 4.0 |
| `tkinter` fails | `sudo apt install python3-tk` |

## 4.3 Network and run

`robot.host` is `0.0.0.0`, so the server listens on every interface and needs no
editing when it moves from the PC to the Pi.

What does need checking is the other direction. The robot **dials in** to a
fixed address written in `ServerCommuncatio.sys` line 52:

```rapid
SocketConnect robotClient, "192.168.125.201", 5000;
```

So whichever machine runs the server has to *hold* that address. The rule for
this cell: **the machine running the server takes 192.168.125.201** — the PC
during development, the Pi at the exam. One number, in one file, and nothing
to edit on the day.

```bash
ip addr        # Linux / Pi
ipconfig       # Windows
```

| What you see | What it means |
|---|---|
| The robot-network adapter shows `192.168.125.201` | Correct. Run it |
| A different `192.168.125.x` | Set that adapter static to `.201`, or change line 52 to match. Do not leave them disagreeing |
| No `192.168.125.x` at all | The cable is out, or the adapter is on DHCP with no server. An adapter that is down has no address at all |
| `WinError 10049` / `EADDRNOTAVAIL` on start | Only happens if `robot.host` was pinned to an address this machine lacks. `0.0.0.0` cannot produce it |

```bash
python3 main.py --config config/profiles/pi.yaml
```

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

Measured on the 271 labelled photos: of 404 objects lying on the sheet, 43
(10.6%) fell below the `|Z| >= 0.10` gate. The causes are not what they look
like, so the rules below come from the numbers rather than from intuition.

| Do | Why |
|---|---|
| **Never let two objects touch.** Leave a visible gap | This is the one cause that is both dominant and free to avoid. All 16 overlapping objects failed the gate; of the 58 with even a small gap, **none** did. Two touching objects merge into a single outline, so the signature belongs to the blob and not to the shape |
| Prefer **coloured objects over white** where you have the choice | A white object on white paper has no boundary to find; the mask latches onto internal shading and breaks into facets. This is most of what remains after the touching cases |
| Light so the object casts a **visible shadow edge** | For a pale object that shadow is the only boundary there is |

Two things that sound like they should matter and **do not**, so do not spend
lab time on them:

- **Distance from the sheet edge.** Restricting the crop to the sheet was
  tested directly: it recovered 1 object and broke 5. The dark table in the
  crop is not what breaks the outline.
- **Resolution.** The failure rate is 10.7% at 640 px and 10.9% at 1280 px, so
  the full 2440 px camera frame will not improve it either.

An object marked **WEAK** is still picked and placed, just not turned, and a
flashing banner names it. That is the default because the assignment requires
every object to be picked in each cycle and allows one of six to be
misoriented.

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

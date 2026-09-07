# Bench procedure

Do-this-then-that steps for calibrating the camera and shooting the dataset.
Every step says what you should see, and what to do when you don't.

The reasoning behind each check is in `CALIBRATION.md`. This file is for
standing at the station.

Author: Suraj Karki
Course: INA700 - AI-based pick and place

---

## Before you start — 5 minutes, at your desk

```bash
cd pi
python tools/preflight.py
```

**Expect:** every line `ok`, except `config: camera` and `config: mapper`, which
say `skip` until step A4.

| If it says | Do |
|---|---|
| `opencv ... has no aruco` | You have plain `opencv-python`. `pip uninstall -y opencv-python opencv-python-headless opencv-contrib-python opencv-contrib-python-headless` then `pip install opencv-contrib-python` |
| `pypylon not installed` | Install the Basler Pylon SDK first, then `pip install pypylon` |
| `no Basler camera detected` | Open Pylon Viewer. If it can't see the camera either, it's the cable or the SDK — not Python |
| `tkinter` fails | Windows: reinstall Python with tcl/tk. Pi: `sudo apt install python3-tk` |

Open **Pylon Viewer** and confirm a live image before going further.

---

# Part A — Camera and marker calibration

Allow about 2 hours the first time. Steps **A6 onward need the robot**.

## A1. Mount the marker

1. Fix the 100 mm rubber marker flat on the picking board — well inside the
   frame, and **clear of where objects land**.
2. **Shim it so its face is level with the top of the objects.** All your
   objects are the same thickness, so one shim does it.
3. Press every edge down. No lifted corners, no curl.
4. Put a few objects on the board and confirm none of them can cover it.

**Expect:** flat, square to the board, at object-top height, and fully visible
with objects present.

| Problem | Fix |
|---|---|
| Marker near the frame edge | Move it inward. Lens distortion is worst at the edges and the mapping inherits it |
| A corner lifts | Tape or re-seat it. A curled corner moves in the image and the calibration jitters |
| Objects land on top of it | Re-site the marker, or mark a keep-clear zone on the board |
| No shim available | Carry on, but expect A7 to show an outward error growing toward the corners |

**Why the shim.** The homography maps the image onto *the plane the marker lies
in*, and the camera sees the objects' **top** faces. Calibrate on the board and
every object is reported displaced outward by about `r·h/H` — roughly 2 mm for
10 mm objects 150 mm off centre under a camera 800 mm up. Systematic, worst at
the corners, and it looks like lens distortion except that it points outward.

## A2. Aim and focus

1. Point the camera so the **whole A3 sheet plus the marker** are in frame, with
   a margin. The sheet is the work object — nothing is picked off it.
2. Put an object on the board and focus **on the object's top surface**, not the
   bare table.
3. Tighten every clamp on the mount.

**Expect:** objects at all four corners are in frame and sharp. Tapping the bench
does not shift the image.

| Problem | Fix |
|---|---|
| Corners soft, centre sharp | Stop the lens down (higher f-number) and raise the light to compensate |
| Image shifts when you nudge the bench | The mount is not rigid. Fix this now — it invalidates everything downstream |
| Board doesn't fit in frame | Raise the camera, or use a wider lens. Do not crop the working area |

> After this step **do not move the camera again.** If you have to, redo from A5.

## A3. Fix exposure and gain

In **Pylon Viewer**:

1. Turn **auto-exposure off** and **auto-gain off**.
2. Set exposure so the A3 sheet is bright but nothing is blown out.
3. Keep gain as low as the light allows.
4. **Write both numbers down.**

`python tools/preflight.py` reports this as `lighting`: the 95th percentile of
the frame, which is the sheet. **Target 180-210**, with nothing clipped. Below
150 the objects sit in too little range and their edges soften.

| Problem | Fix |
|---|---|
| Image too dark at low gain | Add light. Raising gain adds noise, which softens edges and hurts the angle measurement |
| Highlights blown white on the objects | Lower exposure, or diffuse the lamp. Saturated pixels destroy the colour classification |
| Colours look different than yesterday | Auto-exposure crept back on. Check it is off |

## A4. Write the config

In `pi/config/config.yaml`:

```yaml
camera:
  kind: basler
  exposure_us: <your value>
  gain: <your value>

aruco:
  marker_length_mm: 100.0
  marker_id: 0
  marker_centre_xy_mm: [0.0, 0.0]   # placeholder; measured at A6

coordinates:
  mapper: aruco
```

**Expect:** `python smoke_test.py` still runs and prints an inference time.

## A5. Verify detection and stability — the gate

```bash
python tools/preflight.py --length 100
python calibration/aruco_check.py --length 100 --camera basler
```

Watch the jitter figure for a **full minute**.

**Expect:** ID `0` detected in every frame, **jitter below 0.02 px/mm**.

| Problem | Fix |
|---|---|
| Not detected at all | Wrong dictionary, or the marker is cut off at the frame edge. Confirm it is DICT_5X5_100 |
| Detected, drops some frames | Not enough light, or motion blur from a vibrating mount |
| Jitter above 0.02 | In order: kill glare across the marker, then refocus, then add light |
| Jitter fine, then spikes | Something intermittently shadows the marker — usually the operator leaning in |

**Do not book robot time until this passes.** Everything after inherits this number.

## A6. Locate the marker in wobj1 — needs the robot

Keep the work object you already have. You only need to tell the vision system
where the marker sits inside it.

1. Jog the tool tip to the **marker centre**.
2. Read work-object **X** and **Y** off the pendant.
3. Put them in `marker_centre_xy_mm` in `config.yaml`.
4. If the marker is not square to `wobj1`'s X axis, measure that angle and put
   it in `marker_angle_deg`.

**Expect:** two numbers written down. A7 confirms them.

| Problem | Fix |
|---|---|
| Hard to touch the marker centre precisely | Get close. An error here is a uniform shift, which A7 catches and you fix by editing the same two numbers |
| Wondering whether to re-teach wobj1 at the marker | You can, and then it is `[0, 0]` — but moving wobj1 also shifts `Papproach`, `PICK_SURFACE_Z_MM` and the four `PICK_AREA_*` bounds. Not worth it against a work object already proven on hardware |
| Marker not square to the board | Fine. Measure `marker_angle_deg` rather than re-mounting |

## A7. Verify the mapping

1. Put one object on the board. Read X and Y from the GUI.
2. Jog the robot there and compare.
3. Repeat at **three well-separated spots, including one corner**.

**Expect:** agreement within **1–2 mm everywhere**, corners included.

| What you see | What it means |
|---|---|
| Centre good, corners out by several mm | Lens distortion. Move the marker more central, or add intrinsic calibration |
| Everything off by the same amount | `marker_centre_xy_mm` is off. Correct those two numbers — no re-teaching needed |
| Everything off by the same *percentage* | `marker_length_mm` is wrong |
| Error grows outward toward the corners | The marker is not at object-top height. Shim it (A1) |
| X and Y swapped, or rotated | `marker_angle_deg` is wrong |
| Y has the wrong sign | Go to A8 |

## A8. Resolve `y_axis_flipped`

1. Place an object clearly off-centre in **+Y**.
2. Check the sign the GUI reports.
3. If it is negative, set `y_axis_flipped: true` in `config.yaml` and re-check.

**Expect:** the reported sign matches the direction you moved the object.

## A9. Resolve `angle_sign`

1. Place a **square** deliberately at about 45°.
2. Send one pick.
3. Watch how it seats.

**Expect:** the square drops cleanly into its slot.

| What you see | Fix |
|---|---|
| It arrives rotated the wrong way by twice the error | Flip `angle_sign` in `config.yaml` |
| It arrives close but consistently off by a fixed amount | The slot angle is wrong. Do A10 |
| Circle fine, everything else wrong | Almost always `angle_sign` |

## A10. Teach wobj2 and the slot angles

1. Teach the **placing** work object at the jig.
2. Confirm `p10`–`p60` still land in their slots (manual jog).
3. For each shape, in turn:
   - seat the object **in its slot**,
   - lift it **straight out without turning it**,
   - set it on the picking board,
   - read it with:

```bash
python calibration/slot_angles.py --camera basler
```

Press `1`–`5` to pick the shape, `SPACE` to record, `s` to save.

**Expect:** each reading settles below **0.5° spread** before it lets you record.
Paste the saved block into `place_slot_angles_deg` in `config.yaml`.

| Problem | Fix |
|---|---|
| Reading won't settle | Same causes as A5 — glare, focus, light. A star is the most sensitive |
| Star reads wildly different each time | Its thin points are being eroded by the thresholding. Raise the light and check `padding_px` |
| Circle refuses to record an angle | Correct. A circle has no orientation; it records 0 |

## A11. Set the remaining numbers

In `robot/StationData.mod`:

- `PICK_SURFACE_Z_MM` — teach one pick point with an object under the cup, read Z
- `SHEET_ORIGIN_X / SHEET_ORIGIN_Y` — jog to the corner of the A3 sheet nearest
  `wobj1`'s origin and read X and Y off the pendant. The four `PICK_AREA_*`
  bounds derive from these, so nothing else needs editing
- `SHEET_SPAN_X / SHEET_SPAN_Y` — swap the two if the sheet's long edge runs
  along `wobj1` Y

In `config.yaml`, for the lab: `verify_tolerance_mm: 15.0`

---

# Part B — Taking the dataset

Needs only the camera. **Do this whenever the robot is busy** — it is the long
pole, at 2–3 hours.

## B1. Set up

```bash
cd pi
python tools/capture_gui.py
```

Pick the scene on the left, aim, press **Capture** or the **space bar**.
Full-resolution frames land in `model/dataset/raw/<scene>/`, numbered and
resuming across sessions. The live counts keep your coverage balanced.

Scenes are the five shapes plus **Mixed**, for photos with several shapes at
once. The folder is only bookkeeping — YOLO takes its classes from the label
files, never from the folder — but keeping mixed scenes out of a shape's folder
stops that shape's count from claiming coverage it does not have.

## B2. What to shoot

Target **200–300 photos total**, roughly balanced across shapes.

Vary these deliberately — a dataset that only varies in one dimension trains a
model that only works in one situation:

| Vary | How |
|---|---|
| **Position** | Cover the whole board. Include all four corners, not just the middle |
| **Rotation** | Turn each object through a full circle in steps — this is what teaches orientation |
| **Spacing** | Objects alone, in pairs, touching, and clustered |
| **Company** | Each shape alone, and each shape surrounded by others |
| **Lighting** | At least two sessions at different times of day |

Fixed exposure does not fix brightness — ambient light still moves it. Run
`preflight.py` at the start of each session and note whether `lighting` passed,
so you know which condition each block of photos belongs to.

## B3. The one thing that decides whether the model ignores the other two shapes

**Put the two shapes you were NOT assigned into the photos**, in frame, alongside
the ones you were.

Then leave them **unlabelled** when you label. They become hard negatives, and
the model learns to actively ignore them. Training only on three shapes without
ever showing the other two is how a star gets classified as a hexagon.

The capture tool offers all five shapes for exactly this reason, and the
**Mixed** scene for the photos where they appear together — which is what the
board actually looks like at run time.

## B4. While you shoot

- Keep the marker visible — tick **Require marker** to enforce it.
- Glance at the per-shape counts every so often and even them out.
- If you move a lamp, treat it as a new lighting condition, not a mistake.

| Problem | Fix |
|---|---|
| Photos look soft | Something moved the focus. Stop, refocus, and delete the soft batch |
| Counts are lopsided | Shoot the shape that is behind, in fresh positions rather than more of the same |
| Marker warning keeps firing | An object is covering it. Move it, or move the marker |
| You had to move the camera | Everything shot before is still usable for training, but redo A5 onward |

## B5. Before training

1. Open the folders and delete anything blurred, half-out-of-frame, or duplicated.
2. Check each shape has photos from all over the board, not one region.
3. Confirm the two unassigned shapes appear across the set.

---

# Part C — Labelling

Needs no hardware. Allow about 3 hours for the drawing.

## C1. Build the label set

```bash
cd pi
python tools/build_label_set.py
```

This writes the photos that need labelling into `model/dataset/label/images/`,
**downscaled to 1280 px as JPEG**, and puts `manifest.csv` beside them.

**Expect:**

```
  with objects    238  (circle, mixed, square, star)
  empty negatives  42  of 107 available (hexagon, triangle)
  total           280   at 1280 px, JPEG
```

Two things happen here, both deliberate.

**It downscales.** The camera's frames are 6 MB each, and 280 of them is 1.7 GB
— enough to make the labelling UI crawl and far too much to upload for
training. At 1280 px the set is 45 MB and an object is still about 130 px, well
above the 65 px the network sees at 640.

**It does not take every photo.** Your hexagon and triangle folders hold 107
photos with nothing labellable in them. YOLO wants around 10% of a set to be
empty images; 107 out of 345 is 31%, and a model trained on that learns to keep
quiet. The tool samples them across the **brightness range**, so both lighting
conditions are represented, and reports how many it held back.

| Problem | Fix |
|---|---|
| "No images for [...]" | `shapes:` in `config.yaml` does not match your folder names |
| Fewer negatives than you expected | Correct — the budget scales with the number of labelled photos |
| Photos look softer than the originals | Expected. The originals are untouched in `raw/` |
| You later find the model fires on hexagons | Raise `NEGATIVE_FRACTION`, re-run, label the extra ones (they are all empty, so it is quick) |

## C2. Start Label Studio

```powershell
pip install label-studio

# Serve the images from disk instead of uploading them. The browser import
# silently caps at 100 files, and 280 would fail without saying so.
# The document root must be the PARENT of the image folder.
$env:LABEL_STUDIO_LOCAL_FILES_SERVING_ENABLED = "true"
$env:LABEL_STUDIO_LOCAL_FILES_DOCUMENT_ROOT = "C:\Users\suraj\Desktop\INA700\model\dataset\label"
label-studio start
```

Both variables must be set **before** Label Studio starts, in the same shell.

It opens on `http://localhost:8080`. Create an account — it is local, nothing
leaves the machine.

1. **Create Project** → name it `INA700`.
2. **Settings → Labeling Interface → Code** → paste the contents of
   `model/label_config.xml`. Paste the XML, nothing else.
3. **Settings → Cloud Storage → Add Source Storage → Local files**:

   | Field | Value |
   |---|---|
   | Absolute local path | `...\model\dataset\label\images` |
   | File Filter Regex | `.*\.jpg` |
   | Treat every bucket object as a source file | **ON** |

4. **Sync Storage.**

**Expect:** exactly **280 tasks**, and an image visible when you open one.

| Problem | Fix |
|---|---|
| "cannot be the same as LOCAL_FILES_DOCUMENT_ROOT" | The root must be the parent folder — `...\label`, not `...\label\images` |
| Sync gives 1 task, not 280 | "Treat every bucket object as a source file" was off |
| Tasks exist but no image appears | Local files serving was not enabled when the server started |
| `manifest.csv` appears as a task | The storage is pointing at `label/` instead of `label/images/` |
| Import stops at 100 | You used drag-and-drop rather than local storage |

> The order of the three labels in that file **is** the class order in the
> export. It matches `detector.class_map` in `config.yaml`. Do not reorder them.

## C3. Draw the boxes

Keys `1` `2` `3` pick circle, square, star. Drag a box around each one.

| Rule | Why |
|---|---|
| Box the **whole** object, including a star's points | A box cut through the points teaches the model a smaller object than it will see |
| Box **tight** — no surrounding paper | The orientation estimator thresholds inside this box; extra paper adds shadow |
| Box objects **off the sheet** too | Let the model report shape honestly; `PICK_AREA_*` in RAPID rejects positions off the A3 |
| **Never** box a hexagon or triangle | This is the whole hard-negative strategy |
| Submit empty photos with **no boxes at all** | An empty label file is the signal. Skipping the photo is not the same thing |

Photos with `expect_labels = no` in `manifest.csv` are the empty ones. Submit
each of them without drawing anything.

> **Submit, never Skip.** The two buttons sit side by side. Skip records a
> *cancelled* annotation, which does not export — so a skipped negative teaches
> the model nothing, which is the one job it had. Check the count: submitted
> annotations should equal the images you have been through.

**Label across the shapes, not down the list.** Working alphabetically means
hours of circles before the first square, and a model trained on that finds
circles and is blind to everything else. Spread the work so all three classes
build up together — it matters if you want to pre-annotate the remainder from a
model trained on the first batch.

## C4. Export

**Export** → **YOLO** → download the zip. Unpack it so you get:

```
model/dataset/label/
    images/          already there
    labels/          from the export
    classes.txt      from the export
```

## C5. Validate and split — the gate

```bash
cd pi
python tools/split_dataset.py
```

**Expect:** a class table and the path to `data.yaml`. Anything else is a
problem list, and it exits without writing.

| It says | What happened |
|---|---|
| `class order mismatch` | The labelling config was edited. Fix the order — training would otherwise succeed with every shape mislabelled, and nothing would crash |
| `missing` | A photo was never submitted. An empty one still has to be submitted |
| `coordinates not normalised` | Wrong export format. Re-export as YOLO, not COCO or Pascal VOC |
| `no matching image` | A stale label file from an earlier export. Delete it |

The split is stratified by class **and** by brightness, with a fixed seed, so
validation always covers both lighting conditions and the same split comes back
on a re-run.

---

# Part D — Training

## D1. Zip the split

```bash
cd model/dataset
tar -a -c -f yolo.zip yolo
```

## D2. Train on Colab

Open `model/train_yolo.ipynb`, set **Runtime → Change runtime type → T4 GPU**,
and work down the cells. Upload `yolo.zip` when it asks.

About 10 minutes for 150 epochs on ~280 photos.

**Stop at cell 5 and look at the drawn boxes.** A box in the wrong place there
is a labelling error, and no amount of training repairs it.

## D3. Judge the result

| Look at | Want | If not |
|---|---|---|
| `mAP50` | above 0.95 | Below 0.9 on three large, well-separated shapes means labels, not training |
| Confusion matrix, `background` column | hexagon and triangle land here | They are being called shapes — shoot more mixed scenes and re-run C1 |
| `square` recall | in line with the others | It has the fewest photos, so it degrades first. Shoot more squares |
| `results.png` | val loss flat at the end | Still falling: raise `epochs`. Rising: it is over-fitting, lower them |

## D4. Install the model

Unpack the download into `model/`, then in `pi/config/config.yaml`:

```yaml
detector:
  kind: yolo
  model_path: ../model/best.pt      # ../model/best_ncnn_model on the Pi
  image_size: 640                   # must match the imgsz it was trained at
  confidence: 0.5
```

Then:

```bash
cd pi
python tools/preflight.py
python smoke_test.py
```

**Expect:** `smoke_test.py` reports an inference time and finds your objects.

| Problem | Fix |
|---|---|
| Nothing detected | `image_size` does not match training, or `class_map` is out of order |
| Detects, but the shape name is wrong | `class_map` order against `classes.txt`. C5 checks this |
| Far too slow on the Pi | Use `best_ncnn_model`, and drop `image_size` to 480 — retrain at that size |
| Fires on hexagons | Raise `confidence`, then fix it properly with more negatives |

---

# Part E — Testing without hardware

Everything here runs from saved photos. No camera, no robot.

## E1. Check the interpreter

VS Code's status bar must say **opencv_env**, and that environment needs
Ultralytics:

```powershell
conda activate opencv_env
pip install ultralytics
```

## E2. Two cycles end to end

**Run and Debug → `7 - Smoke test (trained model, saved photos)`**

**Expect:** two cycles reporting SUCCESS, and the messages that went to the
robot, each well under the 80-character RAPID limit.

```
cycle 1: SUCCESS in 1 attempt(s) -> CIRCLE GREEN x=355.6 y=228.2 rz=0.0
  move circle 355.56 228.16 0.0#   (30 chars, RAPID limit 80)
```

The first inference takes **20-30 seconds** while the model loads, then settles
near 120 ms. That cold start is real: on the day, start the system well before
you need it.

| Problem | Fix |
|---|---|
| `No module named ultralytics` | Wrong interpreter, or E1 not done |
| `FileNotFoundError: ../model/best.pt` | Unpack `ina700_model.zip` into `model/` |
| Cycles FAILED, 0 detections | The model is still loading — the wait is capped at 120 s |
| `Frame directory not found` | Run `tools/split_dataset.py` first |

## E3. Score the whole pipeline against the labels

**Run and Debug → `8 - Offline check (whole pipeline vs labels)`**

This is the one worth reading. Ultralytics only judges the detector; this judges
what the robot is actually told — shape, colour, and whether the angle was
measured well enough to place on.

**Expect**, on the current model and validation split:

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

| What to watch | Why |
|---|---|
| Any `UNKNOWN` colour | Every object should get a name. UNKNOWN means the colour thresholds need work |
| `spurious` climbing | The model is reporting shapes that are not there — raise `detector.confidence` |
| Many below the gate | Outlines are too weak to measure. Usually light, focus or glare |
| `recall` falling | Lower `detector.confidence`, at the cost of more spurious reports |

Both use `config/config.offline.yaml`, which differs from the lab profile in
exactly three ways: photos instead of a camera, the identity mapper because most
saved photos have no marker in frame, and a loopback robot that always answers
DONE. The detector, orientation estimator and colour classifier are the real ones.

---

# Part F — Running on the Raspberry Pi

The Pi lives in the lab and is already set up. That makes this a normal
deployment rather than an emergency, so it can be done early and repeated
whenever the model changes.

## F1. Benchmark before anything else

```bash
cd INA700/pi
python3 tools/benchmark.py --config config/config.pi.yaml
```

Needs **no camera and no robot** - only the saved photos. It answers the one
question that can sink the demo, in about two minutes.

```
model load and warm-up: 18.4 s
per frame   median 780 ms   worst 910 ms   budget 3000 ms
PASS - worst case is under 1800 ms, comfortably inside budget
```

| Result | Do |
|---|---|
| PASS | Carry on |
| TIGHT | Usable, but re-export at 480 for headroom when convenient |
| FAIL | Re-export NCNN at 480 in Colab. The input size is fixed **at export**, so editing `image_size` alone changes nothing |

Note the warm-up figure and write it down. The system is genuinely unavailable
for that long at start-up, so start it before the examiner is watching.

Re-run this after **every** retrain. It is two minutes and it is the difference
between knowing and hoping.

## F2. Camera

```bash
python3 tools/preflight.py --config config/config.pi.yaml
```

Same checks that pass on the laptop: camera found, exposure and gain as set,
marker detected, lighting in range.

| Problem | Fix |
|---|---|
| `no Basler camera detected` | USB3 port and cable - the Pi's USB2 ports will not carry this camera |
| `pypylon not installed` | Pylon SDK for **ARM64**, then the pypylon wheel |
| `tkinter` fails | `sudo apt install python3-tk` |

## F3. Network

The Pi takes the address the PC used. Set `robot.host` in `config/config.pi.yaml`
to the Pi's own address on the robot network, and confirm the robot reaches it
before starting a cycle.

## F4. Run

```bash
python3 main.py --config config/config.pi.yaml
```

The GUI needs a display - the station monitor, or VNC.

## F5. The fallback

If the Pi ever fails on the day, the same code runs on the laptop:

```powershell
python main.py --config config/config.yaml
```

Nothing about the architecture changes. The two profiles differ only in
`model_path` and `transport`, which is the whole argument for putting them in
configuration rather than in code. Keep the laptop configured and tested so the
option stays real.

---

## Order of work when the robot is only free for one session

1. A1–A5 first, without the robot.
2. Then A6, A7, A8, A9, A10 while you have it.
3. Give the robot back.
4. Part B with the camera alone.
5. Parts C and D at your desk - no hardware at all.

If time runs out, stop after A7. A8 and A9 are quicker to redo than the teaching.

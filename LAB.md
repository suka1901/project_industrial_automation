# The lab session, start to finish

Everything is settled on the **PC**: the camera plugs in here, every
measurement is made here, every number is edited here. The Pi is then sent one
bundle and only runs it. That keeps the three-hour window free of
edit-copy-unpack loops, and keeps one copy of the truth instead of two.

`README.md` explains why the system is built the way it is. This file is for
standing at the bench, in order, with nothing left to remember.

Author: Suraj Karki · Course: INA700 — AI-based pick and place

---

## The shape of the session

| Step | Where | What | Gate before moving on |
|---|---|---|---|
| 1 | PC | checks with no hardware | tests green |
| 2 | PC + camera | marker, exposure, field of view | jitter < 0.02 px/mm |
| 3 | robot | teach `wobj1`, verify, mapping | 0.5 mm at four crosses, 1–2 mm camera-to-robot |
| 4 | robot + PC | `wobj2`, rotation sense, slot angles | a square at 45° seats straight |
| 5 | PC → Pi | one command deploys and verifies | hashes match, preflight passes |
| 6 | Pi | run it | a full cycle |

**Two rules that save the session**

1. **Calibrate with the camera here, then move only the cable to the Pi.**
   Position is re-solved from the marker every frame, so swapping USB costs
   nothing. **DO NOT MOVE THE CAMERA ITSELF**
2. **Measured numbers go in `pi/config/config.yaml`.** `config/profiles/pi.yaml`
   only overrides the detector and the view. Anything measured that is put in a
   profile, the other machine never sees.

---

## 1. No hardware — on the PC

```bash
cd pi
python -m pytest -q
python smoke_test.py --config config/profiles/mock.yaml
python tools/offline_check.py --config config/profiles/offline.yaml
```

| Command | What it proves |
|---|---|
| `pytest` | the code is the code you tested; nothing green, nothing else matters |
| `smoke_test.py` | two whole cycles run end to end against mock adapters |
| `offline_check.py` | the model against the held-out photos: recall, precision, the colours it names, and which angles came from a consensus rather than a clean fit |

**Gate:** all tests green. Do not take a failing tree to the station.

---

## 2. Camera and marker — on the PC, camera plugged in here

Lay the printed sheet with the marker at the centre of the A3, flat, square to
the table. Then:

```bash
python tools/preflight.py --length 100
python calibration/aruco_check.py --length 100 --camera basler
```

Watch the marker for a **full minute** — the failure that matters is
intermittent, usually somebody leaning over the bench.

| Row | What it must say |
|---|---|
| camera | opens, and the line reads **`the whole sensor`**, not `CROPPED` |
| marker detected | `ids [0]` in every frame |
| marker steady | jitter below **0.02 px/mm** |
| field of view | covers the sheet — it fails with the shortfall in mm if not |
| lighting | 95th percentile **180–210**, nothing clipping |
| slot angles | `pasted; play …` (step 4 sets these) |
| slot angle source | `measured with 'fitted', which is what runs` (step 4) |

**Fixing the rows**

- *Lighting* says what to change it to: `try camera.exposure_us 11179 (it is
  3000 now)`. Put that in `config.yaml`, run preflight again.
- *CROPPED* means the camera is delivering part of its sensor — a crop left in
  Pylon Viewer, which survives a power cycle and looks exactly like a longer
  lens. The code resets it at every open; if it still says CROPPED, clear it in
  Pylon Viewer.
- *Jitter above 0.02*: in order — kill glare, refocus, add light.
- *Field of view too small*: the sheet must fit; the jig need not (step 4).

**Gate:** marker detected in every frame, jitter under 0.02. Everything after
this inherits it, so do not book robot time until it passes.

---

## 3. The robot frame

### 3.1 Teach `wobj1` with the POINTER, not the cup

Manual mode → Jogging → tool = **pointer**, motion linear. Three points, each
touched **on the sheet surface** — they set the Z datum as well as the origin
and the axes:

| Point | Where |
|---|---|
| X1 | the sheet corner that is the origin — this point *is* (0, 0) |
| X2 | the far end of the **297 mm** edge |
| Y1 | along the 420 mm edge, as far out as you can reach |

Hover and sight down the pointer; do not press. Let the arm settle before
reading each point. Teaching with the cup instead costs about 1.3 mm on every
pick — more than parallax and detection noise together.

### 3.2 Verify it against the printed crosses

Pointer, Coordinate System `WorkObject`, Work Object `wobj1`:

| Cross | Should read |
|---|---|
| origin corner | `10, 10` |
| along +X | `287, 10` |
| along +Y | `10, 410` |
| opposite | `287, 410` |

**Gate: within 0.5 mm at every cross.**

| What you see | What it means |
|---|---|
| the same offset at all four | the origin is off — re-touch X1 |
| right at X1, worse further out | the X axis is rotated — re-touch X2, further out |
| X and Y swapped | +X was taught along the long edge |
| one cross wrong, three right | a bad reading, not a bad frame — retake it |

Then swap the tool back to the **cup** and re-check `PICK_SURFACE_Z_MM` in
`robot/StationData.mod` on a scrap object: the 3-point method just put Z = 0 at
the paper, and the stored value was tuned against a different datum.

### 3.3 Camera against robot — the mapping gate

Start the window on the PC, put one object on the sheet, read X and Y off the
table, jog the pointer there, compare. **Three well-separated spots, one of them
a corner.**

**Gate: within 1–2 mm everywhere.**

| What you see | The number to change, in `config.yaml` |
|---|---|
| all off by the same amount | `aruco.marker_centre_xy_mm` |
| all off by the same percentage | `aruco.marker_length_mm` |
| X and Y swapped or rotated | `aruco.marker_angle_deg` (0 / 90 / 180 / 270) |
| Y mirrored | `aruco.y_axis_flipped: true` |
| centre good, corners out | lens distortion — live with it |

**Do not guess at the turn and the mirror.** There are eight combinations and
each wrong one costs an edit, a deploy and a restart. Measure one object from
the origin corner, read what the GUI says for it, and ask:

```bash
python tools/solve_axes.py --true 60 80 --reported 278.5 121.5
```

It prints what every setting would read and names the one that fits. Use an
object well away from the marker's centre — near the middle, several settings
agree, and the tool says so when they do.

If nothing fits within a few millimetres, the axes are not merely turned: that
is the signature of `wobj1` taught with +X along the long edge, and then
`sheet.span_xy_mm`, `marker_centre_xy_mm` and `SHEET_SPAN_X/Y` in
`StationData.mod` all have to swap with it.

---

## 4. The jig: `wobj2`, rotation sense, slot angles

### 4.1 Teach `wobj2` and confirm the slots

Teach the placing work object at the jig, then confirm `p10`–`p60` still land in
their slots. These are taught in `wobj1` and converted into `wobj2` — the
conversion is already in `StationData.mod`; you are only checking the physical
result.

### 4.2 Rotation sense

Place a **square** at roughly 45°, send one pick, watch it seat.

| What you see | Fix |
|---|---|
| turned the wrong way by twice the error | flip `coordinates.angle_sign` |
| close, but off by a constant | the slot angles — 4.3 |
| circle fine, everything else wrong | almost always `angle_sign` |

If the wrist does not turn **at all**, hard-code it on the pendant for one
cycle, in `MainModule.mod`:

```rapid
RETURN RelTool(placeTargets{request.shapeIndex}, 0, 0, 0 \Rz:=30);
```

Turning there means `RelTool` works and the rotation is being lost earlier; not
turning means nothing on the Pi can fix it. Put `request.rotation` back after.

### 4.3 Slot angles — on the PC, camera plugged in here

```bash
python calibration/slot_angles.py --camera basler --config config/config.yaml
```

Pass the same `--config` that will run: the tool builds its estimator from it
and records which one in `slot_angles.yaml`. Preflight fails on a mismatch,
because `rz = slot − object` only cancels while one estimator measures both.

| Key | Does |
|---|---|
| `1`–`5` | choose the shape |
| `R` | drag a box round that slot |
| `SPACE` | record a seating (refused until the slot has been seen empty) |
| `C` | clear this shape and start it over |
| `S` | save |

Seat the object, wait for the reading to settle, `SPACE`. Then **lift it out,
seat it again, `SPACE` again — at least three times per shape.** The spread
across seatings is the only honest measure of the slot's play.

The blue box is what you drew; the **green** one is what was measured. A green
box round the jig plate reads perfectly steadily and is the plate's angle, not
the slot's.

**If the jig does not fit in the camera's view**, slide it in and slide it back.
These are rotations, and sliding does not change one — only turning the jig
would. Push it along a straight edge; never let it twist.

| Problem | Meaning |
|---|---|
| marked **LOOSE** | play above 10% of the symmetry period — tolerable, but every placement must live inside it |
| `play` 0.00–0.02° | a re-seat did not really happen; a hand cannot repeat to a hundredth of a degree |
| `n=1` or `n=2` | not enough seatings to judge the play |
| won't settle | glare, focus or light — the star is the most sensitive |

Paste the saved `place_slot_angles_deg` block into `config.yaml`.

**Gate:** three or more seatings per shape, and preflight's *slot angle source*
row green.

---

## 5. Deploy to the Pi — one command

Move the camera's USB cable from the PC to the Pi (the camera itself does not
move), put the Pi on the robot network, then from the project root:

```powershell
.\deploy.ps1 <pi-address>      # ./deploy.sh on bash; the address is remembered
```

It runs the tests, builds the bundle, copies it, unpacks it, **checks the Pi's
`config.yaml` hashes the same as this one**, and runs preflight over SSH. That
hash is the point: an unpack that did not overwrite leaves the Pi on last week's
calibration, and nothing about it looks wrong until the robot moves.

```powershell
.\deploy.ps1 -WithCamera       # also the marker and lighting rows, on the Pi
.\deploy.ps1 -SkipBuild        # push the bundle already built
```

Every later change to a number is: edit here, deploy again.

**If the Pi is bare** (it should not be — the venv is already there):

```bash
sudo apt install python3-tk
source ~/venv/bin/activate
pip install ncnn pyyaml opencv-python numpy pillow
# pypylon needs the ARM64 Pylon SDK installed first
```

No ultralytics and no torch on the Pi: the Pi profile runs the exported model on
the 12 MB ncnn runtime, and torch's aarch64 wheel fills the disk before it
finishes installing.

---

## 6. On the Pi

From the Pi's own monitor for the window, or over SSH for the console view.
**Activate the virtual environment first — every command needs it:**

```bash
source ~/venv/bin/activate
cd ~/INA700/pi
```

`run.sh` refuses with that exact line if you forget, rather than failing later
as `ModuleNotFoundError`.

Run it, do not source it: `./run.sh`. Sourced, it replaces the shell of the
terminal you are typing in, and closing the window closes that terminal.

```bash
./run.sh preflight     # is this Pi ready
./run.sh bench         # how fast the model runs HERE
./run.sh               # the window: live view, dropdowns, Send pick to robot
```

| Command | Expect |
|---|---|
| `preflight` | every row green, including *slot angle source* |
| `bench` | about **426 ms median**, first frame near 1 s — that is warm-up — against a 3000 ms budget |
| `./run.sh` | the window, with the live view and the status bar |
| `./run.sh console` | the same system with a `pick>` prompt; works over plain SSH, where Tk cannot open a display |
| `./run.sh check` | the model against the held-out photos, on the Pi |
| `./run.sh light` | the sheet's brightness and every object's contrast, live — move the lamp until the number stops changing for the better |

The wrapper carries `--config config/profiles/pi.yaml` for you; the base config
says `detector: yolo`, which the Pi cannot run. Extra arguments pass through, so
`./run.sh preflight --no-camera` works. `./run.sh help` lists them.

### Running a cycle — it takes two buttons

| Route in | How |
|---|---|
| the window | shape and colour dropdowns, **Send pick to robot** |
| the terminal that launched it | type `circle red`, enter |
| any other terminal | `echo "circle red" > /tmp/ina700.cmd` |

1. Your button chooses the object and sends its position. **Nothing moves yet.**
2. The status bar reads `PRESS THE YELLOW BUTTON` — the robot is holding the
   position, waiting for you at the cell.
3. Press it. The arm picks where the camera said and places in that shape's
   slot, turned by `rz`. The status bar says `the robot is placing the square`.
4. `status` in the console view lists what the camera sees right now, with X, Y,
   Rz and the fit per object. `quit` shuts down cleanly.

The picture itself refreshes at the capture rate, so it stays live; the boxes
on it come from inference and are up to half a second behind. On a still table
you cannot tell. While the arm sweeps through the frame you can, and that is
the overlay being honest about its age rather than a fault.

If the window feels heavy on the Pi, `gui.preview_max_width` is the knob —
640 there against 1000 on the PC, because rescaling the frame is what the
window spends its cores on.

With the window up, the launching terminal also carries the log, so type into a
second terminal through the pipe — or set `logging: console_level: WARNING` in
`config/profiles/pi-gui.yaml`.

### What the orientation is telling you

The confidence is an **overlap with an ideal square or star**, 0 to 1. It is
reported, never acted on: every object is placed at the best angle available,
and nothing is refused or left straight.

| What you see | What it means |
|---|---|
| fit above 0.85 | a clean silhouette; good to about half a degree |
| fit 0.6–0.8 | a decent reading, a degree or two out at worst |
| `the angle is a guess from N segmentation(s)` in the log | no mask fitted well, so the candidates' consensus was sent. Usually a pale object; side light fixes it |
| `no segmentation found an object in the crop` | the only case with no angle at all. Lighting, not code |

Read the guesses out of the log after a run — that is where to look if a
placement came out crooked. Nothing is shown on screen during the cycle.

---

## 7. Rehearse, then hand in

1. All three shapes on the sheet, not touching, at clearly different angles.
   The jig empty.
2. Ask for each in turn by shape **and colour**; press the yellow button each
   time.
3. Watch: picked from where it lies, placed in its own slot, turned to match.
4. A **second cycle without restarting the program** — that is the requirement
   being tested.
5. The printed inference time stays under 3 s. It should read about 0.4 s.

Count the placements as the examiner will: all three picked in each cycle, five
of six at the correct orientation, at least one of each shape.

**Before leaving the lab:**

```bash
# carry back anything you changed on the Pi (you should not have, but check)
scp pi@<pi-address>:~/INA700/pi/config/config.yaml pi/config/config.yaml
```

Export the station in RobotStudio (**Controller → Pack and Go**), put the `.pgz`
in `pack-and-go/`, and from the project root:

```bash
python make_submission.py
```

That writes `FinalProject_SurajKarki.zip` — program files, trained model,
Pack-and-Go — and runs the tests first. It refuses rather than writing an
incomplete or wrongly named zip; the course reports those as failed, with no
resubmission.

The Pack-and-Go has to be the station as examined and cannot be made
afterwards. If you edited the RAPID modules on the pendant, copy the text back
into `robot/` so the repo matches what the Pack-and-Go captured.

---

## 8. When something is wrong

| Symptom | First thing to check |
|---|---|
| `ModuleNotFoundError` on the Pi | the venv: `source ~/venv/bin/activate` |
| "the object is still on the board", but it was picked | the camera check after the pick. The arm should be clear at `Phome`; if it is in frame, or the scene is stale, lower `robot.verify_tolerance_mm` or set it to 0 |
| `ModuleNotFoundError: ultralytics` | you ran `python3 main.py` instead of `./run.sh` |
| the terminal closes with the window | you ran `source run.sh`. Run it as `./run.sh` — only the venv is sourced |
| nothing rotates | the fit scores in the log — below 0.6 it is lighting, not the robot |
| one shape is always placed at the same wrong angle | the fit score in the log for that shape. A pale object on white paper is measured from its border rather than its brightness; if the fit is still low, a side light buys more than any setting |
| a white object is seen but never rotated | `./run.sh light`. A white square needs about 40 grey levels of contrast against the paper; it has 13 at a sheet of 100 and 34 at 150. Raise `camera.exposure_us` toward the top of the 150–245 band, then move the lamp low and to one side so the object's edge casts a shadow |
| everything rotates the wrong way | `coordinates.angle_sign` |
| everything off by the same angle | the slot angles, and whether they were measured with the running estimator |
| picks land beside the object | `wobj1` and the four crosses, then the mapping gate |
| the Pi behaves differently from the PC | deploy again and read the hash line — they are not running the same config |
| "off board" refusals | `sheet.span_xy_mm` must match `SHEET_SPAN_X/Y` in `StationData.mod` |
| the robot never connects | the server listens on `0.0.0.0:5000`; the address in `ServerCommuncatio.sys` must be the **Pi's**, not the PC's |
| the camera sees too little | the `CROPPED` line in step 2 |
| the window says STOPPED | a worker thread died — read the log; usually the camera or the robot connection |

### What a change needs

| What you changed | What to do |
|---|---|
| a number in `config.yaml` | edit on the PC, `.\deploy.ps1` again |
| Python code, or a re-exported model | same: edit on the PC, deploy |
| anything taught on the robot — `wobj1`, `wobj2`, `p10`–`p60`, `PICK_SURFACE_Z_MM`, the `.mod` modules, the address in `ServerCommuncatio.sys` | nothing. It lives in the controller and reaches the submission through the Pack-and-Go |

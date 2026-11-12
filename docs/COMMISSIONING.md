# Commissioning and operation

How to bring the cell up from nothing: calibrate the camera against the robot,
measure the jig, deploy to the Raspberry Pi, and run it.

The order matters. Each stage has a gate, and every later stage inherits the
error of the one before it — a camera-to-robot mapping that is 3 mm out cannot
be rescued by anything downstream.

[`README.md`](../README.md) explains why the system is built the way it is.
This document is what to do at the bench.

---

## Two rules

1. **Calibrate with the camera on the PC, then move only the cable to the Pi.**
   Position is re-solved from the marker on every frame, so moving the USB
   cable between machines costs nothing — but moving the camera itself
   invalidates nothing except your patience, since the next frame corrects it.
   Keep it still anyway while measuring, or the gates below will not settle.
2. **Measured numbers belong in `pi/config/config.yaml`.**
   `config/profiles/pi.yaml` overrides only the detector and the view. A
   measurement put in a profile is a measurement the other machine never sees.

| Stage | Where | Gate before moving on |
|---|---|---|
| 1 Software | PC | tests green |
| 2 Camera and marker | PC + camera | marker jitter < 0.02 px/mm |
| 3 Robot frame | robot | 0.5 mm at four crosses, 1–2 mm camera to robot |
| 4 Jig and slot angles | robot + PC | a square at 45° seats straight |
| 5 Deployment | PC → Pi | config hashes match, preflight passes |
| 6 Operation | Pi | a complete cycle |

---

## 1. Software, with no hardware

```bash
cd pi
python -m pytest -q
python smoke_test.py --config config/profiles/mock.yaml
python tools/offline_check.py --config config/profiles/offline.yaml
```

| Command | What it establishes |
|---|---|
| `pytest` | the code is the code that was tested |
| `smoke_test.py` | two complete cycles against mock adapters |
| `offline_check.py` | the model against held-out photos: recall, precision, the colours it names, and which angles came from a consensus rather than a clean fit |

**Gate:** all tests green.

---

## 2. Camera and marker

Lay the printed marker sheet flat on the table, square to its edges, with the
marker at the centre of the A3.

```bash
python tools/preflight.py --length 100
python calibration/aruco_check.py --length 100 --camera basler
```

Watch the marker for a full minute. The failure that matters is intermittent —
usually somebody leaning over the bench.

| Row | Expected |
|---|---|
| camera | opens, and reports **`the whole sensor`**, not `CROPPED` |
| marker detected | `ids [0]` in every frame |
| marker steady | jitter below **0.02 px/mm** |
| field of view | covers the sheet; it fails with the shortfall in millimetres |
| lighting | sheet in the **150–245** band, nothing clipping |
| slot angles | set in stage 4 |
| slot angle source | `measured with 'fitted', which is what runs` |

**Resolving failures**

- *Lighting* names the change: `try camera.exposure_us 11179 (it is 3000 now)`.
  Put that in `config.yaml` and run preflight again. Aim near the top of the
  band — contrast scales with signal, and a pale object needs all of it.
- *CROPPED* means the camera is delivering part of its sensor. A crop left in
  Pylon Viewer survives a power cycle and looks exactly like a longer lens. The
  code resets the area of interest at every open; if it still reports CROPPED,
  clear it in Pylon Viewer.
- *Jitter above 0.02*, in order: kill glare, refocus, add light.
- *Field of view too small*: the sheet must fit. The jig need not — see 4.3.

**Gate:** marker detected in every frame, jitter under 0.02 px/mm.

---

## 3. The robot frame

### 3.1 Teach `wobj1` with the pointer

Manual mode → Jogging → tool **pointer**, motion linear. Three points, each
touched on the sheet surface, so they set the Z datum as well as the origin and
the axes:

| Point | Where |
|---|---|
| X1 | the sheet corner that is the origin — this point *is* (0, 0) |
| X2 | the far end of the **297 mm** edge |
| Y1 | along the 420 mm edge, as far out as the arm reaches |

Hover and sight down the pointer rather than pressing, and let the arm settle
before each reading. Teaching with the vacuum cup instead costs about 1.3 mm on
every pick — more than parallax and detection noise together.

### 3.2 Verify against the printed crosses

Pointer, coordinate system `WorkObject`, work object `wobj1`:

| Cross | Should read |
|---|---|
| origin corner | `10, 10` |
| along +X | `287, 10` |
| along +Y | `10, 410` |
| opposite | `287, 410` |

**Gate: within 0.5 mm at every cross.**

| Symptom | Cause |
|---|---|
| the same offset at all four | the origin is off — re-touch X1 |
| correct at X1, worse further out | the X axis is rotated — re-touch X2, further out |
| X and Y swapped | +X was taught along the long edge |
| one cross wrong, three right | a bad reading, not a bad frame — retake it |

Then swap the tool back to the cup and re-check `PICK_SURFACE_Z_MM` in
`robot/StationData.mod` against a scrap object: the three-point method has just
put Z = 0 at the paper, and the stored value was tuned against a different
datum.

### 3.3 Camera against robot

Start the window on the PC, put one object on the sheet, read X and Y from the
table, jog the pointer to that position and compare. Use **three
well-separated spots, one of them a corner.**

**Gate: within 1–2 mm everywhere.**

| Symptom | The value to change in `config.yaml` |
|---|---|
| all off by the same amount | `aruco.marker_centre_xy_mm` |
| all off by the same percentage | `aruco.marker_length_mm` |
| X and Y swapped or rotated | `aruco.marker_angle_deg` (0 / 90 / 180 / 270) |
| Y mirrored | `aruco.y_axis_flipped: true` |
| centre accurate, corners out | lens distortion |

**Do not guess at the turn and the mirror.** There are eight combinations, and
each wrong one costs an edit, a deployment and a restart. Measure one object
from the origin corner, read what the GUI reports for it, and ask:

```bash
python tools/solve_axes.py --true 60 80 --reported 278.5 121.5
```

It prints what every setting would read and names the one that fits. Use an
object well away from the marker's centre; near the middle several settings
agree, and the tool says so when they do.

If nothing fits within a few millimetres the axes are not merely turned. That
is the signature of `wobj1` taught with +X along the long edge, in which case
`sheet.span_xy_mm`, `aruco.marker_centre_xy_mm` and `SHEET_SPAN_X/Y` in
`StationData.mod` all have to swap with it.

---

## 4. The jig

### 4.1 Teach `wobj2`

Teach the placing work object at the jig, then confirm `p10`–`p60` still land in
their slots. They are taught in `wobj1` and converted into `wobj2`; the
conversion is already in `StationData.mod`, so this is a check of the physical
result, not a calculation.

### 4.2 Rotation sense

Place a square at roughly 45°, command one pick, and watch it seat.

| Symptom | Fix |
|---|---|
| turned the wrong way, by twice the error | flip `coordinates.angle_sign` |
| close, but off by a constant | the slot angles — 4.3 |
| circle correct, everything else wrong | almost always `angle_sign` |

If the wrist does not turn **at all**, hard-code a rotation on the pendant for
one cycle, in `MainModule.mod`:

```rapid
RETURN RelTool(placeTargets{request.shapeIndex}, 0, 0, 0 \Rz:=30);
```

Turning there proves `RelTool` works and the rotation is being lost earlier; not
turning means nothing on the Pi can fix it. Restore `request.rotation`
afterwards.

### 4.3 Slot angles

```bash
python calibration/slot_angles.py --camera basler --config config/config.yaml
```

Pass the same `--config` that will run: the tool builds its estimator from it
and records which one in `slot_angles.yaml`. Preflight fails on a mismatch,
because `rz = slot − object` only cancels the estimator's constant offset while
one estimator measures both terms.

| Key | Action |
|---|---|
| `1`–`5` | choose the shape |
| `R` | drag a box around that slot |
| `SPACE` | record a seating (refused until the slot has been seen empty) |
| `C` | clear this shape and start again |
| `S` | save |

Seat the object, wait for the reading to settle, press `SPACE`. Then lift it
out, seat it again and record again — **at least three seatings per shape.** The
spread across seatings is the only honest measure of the slot's play.

The blue box is the one you drew; the **green** one is what was measured. A
green box around the jig plate reads perfectly steadily and is the plate's
angle, not the slot's.

**If the jig does not fit in the camera's view**, slide it in and slide it back
afterwards. These are rotations, and sliding does not change one — only turning
the jig would. Push it along a straight edge and never let it twist.

| Reading | Meaning |
|---|---|
| marked **LOOSE** | play above 10% of the symmetry period; tolerable, but every placement must live inside it |
| `play` 0.00–0.02° | a re-seat did not really happen — a hand cannot repeat to a hundredth of a degree |
| `n=1` or `n=2` | too few seatings to judge the play |
| will not settle | glare, focus or light; the star is the most sensitive |

Paste the saved `place_slot_angles_deg` block into `config.yaml`.

**Gate:** three or more seatings per shape, and preflight's *slot angle source*
row green.

---

## 5. Deployment

Move the camera's USB cable from the PC to the Pi — the camera itself stays
where it is — put the Pi on the robot network, then from the project root:

```powershell
.\deploy.ps1 <pi-address>      # ./deploy.sh on bash; the address is remembered
```

It runs the tests, builds the bundle, copies it, unpacks it, **checks that the
Pi's `config.yaml` hashes the same as this one**, and runs preflight over SSH.
That hash is the point: an unpack that did not overwrite leaves the Pi on last
week's calibration, and nothing about it looks wrong until the robot moves.

```powershell
.\deploy.ps1 -WithCamera       # also the marker and lighting rows, on the Pi
.\deploy.ps1 -SkipBuild        # send the bundle already built
```

Every later change to a number is: edit on the PC, deploy again.

For a Pi with nothing installed on it yet, see
[`PI_SETUP.txt`](../PI_SETUP.txt) — operating system, virtual environment and
libraries, including an offline install. Note that the Pi does not get
`ultralytics` or torch: it runs the exported model on the 12 MB NCNN runtime,
and torch's aarch64 wheel fills the Pi's disk before it finishes installing.

---

## 6. Operation

From the Pi's own monitor for the window, or over SSH for the console view.
Activate the virtual environment first — every command needs it:

```bash
source ~/venv/bin/activate
cd ~/INA700/pi
```

`run.sh` refuses with that line if you forget, rather than failing later as
`ModuleNotFoundError`. Run it, do not source it: sourced, it replaces the shell
of the terminal you are typing in.

```bash
./run.sh preflight     # is this Pi ready
./run.sh light         # sheet brightness and per-object contrast, live
./run.sh bench         # how fast the model runs here
./run.sh               # the window: live view, dropdowns, Send pick to robot
./run.sh console       # the same system with a pick> prompt, for SSH
./run.sh check         # the model against the held-out photos
```

The wrapper carries `--config config/profiles/pi.yaml`; the base config names
the YOLO detector, which the Pi cannot run. Extra arguments pass through, so
`./run.sh preflight --no-camera` works. `./run.sh help` lists them.

### Running a cycle

| Route in | How |
|---|---|
| the window | shape and colour dropdowns, **Send pick to robot** |
| the terminal that launched it | type `circle red` |
| any other terminal | `echo "circle red" > /tmp/ina700.cmd` |

1. The command chooses the object and sends its position. **Nothing moves yet.**
2. The status bar reads `PRESS THE YELLOW BUTTON` — the robot is holding the
   position, waiting at the cell.
3. On the button press, the arm picks where the camera said and places in that
   shape's slot, turned by `rz`.
4. `status` in the console view lists what the camera sees, with X, Y, Rz and
   the fit per object. `quit` shuts down cleanly.

The picture refreshes at the capture rate, so it stays live; the boxes on it
come from inference and are up to half a second behind. On a still table this
is invisible. While the arm sweeps through the frame it is not, and that is the
overlay being honest about its age rather than a fault.

If the window is heavy on the Pi, `gui.preview_max_width` is the knob — 640
there against 1000 on the PC, because rescaling the frame is what the window
spends its cores on.

### Acceptance check

A cell is commissioned when, without restarting the program:

1. All three shapes lie on the sheet, not touching, at clearly different
   angles, and the jig is empty.
2. Each is requested in turn by shape **and** colour, and picked from where it
   lies.
3. Each is placed in its own slot, turned to match.
4. A second cycle runs on the same process.
5. The printed inference time stays within the configured budget.

### Reading the orientation confidence

The confidence is an overlap with an ideal square or star, 0 to 1. It is
reported, never acted on: every object is placed at the best angle available,
and nothing is refused or left straight.

| Reading | Meaning |
|---|---|
| fit above 0.85 | a clean silhouette, good to about half a degree |
| fit 0.6–0.8 | a decent reading, a degree or two out at worst |
| `the angle is a guess from N segmentation(s)` in the log | no mask fitted well, so the candidates' consensus was sent. Usually a pale object; side light fixes it |
| `no segmentation found an object in the crop` | the only case with no angle at all. Lighting, not code |

The guesses are in the log, not on screen. That is where to look if a placement
came out crooked.

---

## 7. Troubleshooting

| Symptom | First thing to check |
|---|---|
| `ModuleNotFoundError` on the Pi | the virtual environment: `source ~/venv/bin/activate` |
| "the object is still on the board", but it was picked | the camera check after the pick. The arm should be clear at `Phome`; if it is in frame, or the scene is stale, lower `robot.verify_tolerance_mm` or set it to 0 |
| `ModuleNotFoundError: ultralytics` | `python3 main.py` was run instead of `./run.sh` |
| the terminal closes with the window | `run.sh` was sourced. Run it as `./run.sh` — only the virtual environment is sourced |
| nothing rotates | the fit scores in the log — below 0.6 it is lighting, not the robot |
| one shape is always placed at the same wrong angle | the fit score for that shape. A pale object on white paper is measured from its border rather than its brightness; if the fit is still low, a side light buys more than any setting |
| a white object is seen but never rotated | `./run.sh light`. A white square needs about 40 grey levels of contrast against the paper; it has 13 at a sheet of 100 and 34 at 150. Raise `camera.exposure_us` toward the top of the 150–245 band, then move the lamp low and to one side so the object's edge casts a shadow |
| everything rotates the wrong way | `coordinates.angle_sign` |
| everything off by the same angle | the slot angles, and whether they were measured with the running estimator |
| picks land beside the object | `wobj1` and the four crosses, then the camera-to-robot gate |
| the Pi behaves differently from the PC | deploy again and read the hash line — they are not running the same config |
| "off board" refusals | `sheet.span_xy_mm` must match `SHEET_SPAN_X/Y` in `StationData.mod` |
| the robot never connects | the server listens on `0.0.0.0:5000`; the address in `ServerCommuncatio.sys` must be the **Pi's**, not the PC's |
| the camera sees too little | the `CROPPED` line in stage 2 |
| the window says STOPPED | a worker thread died — read the log; usually the camera or the robot connection |

### What a change requires

| Changed | Action |
|---|---|
| a number in `config.yaml` | edit on the PC, deploy again |
| Python code, or a re-exported model | the same: edit on the PC, deploy |
| anything taught on the robot — `wobj1`, `wobj2`, `p10`–`p60`, `PICK_SURFACE_Z_MM`, the `.mod` modules, the address in `ServerCommuncatio.sys` | nothing here. It lives in the controller |

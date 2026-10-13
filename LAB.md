# At the station

Everything is settled on the **PC**: the camera is plugged in here, every
measurement is made here, every number is edited here. The Pi is then sent one
bundle and only runs it. That keeps the three-hour window free of edit-copy-
unpack loops, and keeps one copy of the truth instead of two.

`README.md` explains why the system is built this way; this file is for
standing at the bench.

Author: Suraj Karki · Course: INA700 — AI-based pick and place

**The shape of the session**

| | Where | What |
|---|---|---|
| 1 | PC | no-hardware checks |
| 2 | PC, camera on it | marker, exposure, mapping |
| 3 | robot | teach the frames, rotation sense |
| 4 | PC, camera on it | the jig's slot angles |
| 5 | PC → Pi | one command deploys and verifies |
| 6 | Pi | run it |
| 7 | — | rehearse, then hand in |

**The one rule about moving the camera:** calibrate it here, then move only the
USB cable to the Pi. Position is re-solved from the marker every frame, so the
cable costs nothing — but a bumped mount invalidates the sheet geometry and
sends you back to step 2.

**And about where numbers live:** measured values go in `pi/config/config.yaml`.
`config/profiles/pi.yaml` only overrides the detector and the view. Anything
measured that is put in a profile the other machine never sees.

---

## 1. No hardware — on the PC

```bash
cd pi
python -m pytest -q                                        # all green
python smoke_test.py --config config/profiles/mock.yaml    # two cycles, no hardware
python tools/offline_check.py --config config/profiles/offline.yaml
```

The last one scores the model against the held-out photos: recall, precision,
the colours it named, and which angles came from a consensus rather than a
clean fit.

---

## 2. Camera and marker — on the PC, camera plugged in here

```bash
python tools/preflight.py --length 100
python calibration/aruco_check.py --length 100 --camera basler
```

Watch the marker for a **full minute** — the failure that matters is
intermittent, usually somebody leaning over the bench.

| Row | What it must say |
|---|---|
| camera | opens; the line reads **`the whole sensor`**, not `CROPPED` |
| marker detected | `ids [0]` in every frame |
| marker steady | jitter below **0.02** px/mm |
| field of view | covers the sheet; it fails with the shortfall in mm if not |
| lighting | 95th percentile **180–210**, nothing clipping |

A failing lighting row says what to change it to, e.g. `try
camera.exposure_us 11179 (it is 3000 now)`. Edit `config.yaml` here and run it
again.

`CROPPED` means the camera is delivering part of its sensor — a crop someone
left in Pylon Viewer, which survives a power cycle and looks exactly like a
longer lens. The code resets it at every open; if it still says CROPPED, clear
it in Pylon Viewer.

**Do not book robot time until the marker row passes.** Everything after
inherits it.

---

## 3. The robot frame — the gate everything stands on

### 3.1 Teach `wobj1` with the POINTER, not the cup

Manual mode, Jogging, tool = pointer, motion linear. Three points, each touched
**on the sheet surface** — they set the Z datum as well as the origin and axes:

| Point | Where |
|---|---|
| X1 | the sheet corner that is the origin — this point *is* (0, 0) |
| X2 | the far end of the **297 mm** edge |
| Y1 | along the 420 mm edge, as far out as you can reach |

Hover and sight down the pointer; do not press. Let the arm settle before
reading. Teaching with the cup instead costs about 1.3 mm on every pick — more
than parallax and detection noise together.

**Verify against the printed crosses**, pointer, work object `wobj1`:

| Cross | Should read |
|---|---|
| origin corner | `10, 10` |
| along +X | `287, 10` |
| along +Y | `10, 410` |
| opposite | `287, 410` |

Within **0.5 mm** at every cross. The same offset everywhere means the origin is
off; error growing with distance means the X axis is rotated; swapped readings
mean +X was taught along the long edge.

Then swap the tool back to the cup and re-check `PICK_SURFACE_Z_MM` on a scrap
object — the 3-point method just put Z = 0 at the paper.

### 3.2 Camera against robot — the mapping gate

Put one object down, read X and Y off the GUI on the PC, jog there, compare.
Three well-separated spots, one of them a corner. **Within 1–2 mm everywhere.**

| What you see | What it is |
|---|---|
| all off by the same amount | `aruco.marker_centre_xy_mm` |
| all off by the same percentage | `aruco.marker_length_mm` |
| X and Y swapped or rotated | `aruco.marker_angle_deg` |
| Y sign wrong | set `aruco.y_axis_flipped: true` |
| centre good, corners out | lens distortion; live with it |

### 3.3 `wobj2` and the rotation sense

Teach the placing work object at the jig and confirm `p10`–`p60` still land in
their slots. Then place a **square** at roughly 45°, run one pick, watch it
seat.

| What you see | Fix |
|---|---|
| turned the wrong way by twice the error | flip `coordinates.angle_sign` |
| close, but off by a constant | the slot angles — step 4 |
| circle fine, everything else wrong | almost always `angle_sign` |

If the wrist does not turn **at all**, hard-code it on the pendant for one
cycle, in `MainModule.mod`:

```rapid
RETURN RelTool(placeTargets{request.shapeIndex}, 0, 0, 0 \Rz:=30);
```

Turning there means `RelTool` works and the rotation is being lost earlier; not
turning means nothing on the Pi can fix it. Put `request.rotation` back after.

Nothing taught on the robot ever goes in the bundle. It lives in the
controller, and reaches the submission through the Pack-and-Go.

---

## 4. The jig's slot angles — on the PC, camera plugged in here

```bash
python calibration/slot_angles.py --camera basler --config config/config.yaml
```

Pass the same `--config` that will run: the tool builds its estimator from it
and records which one in `slot_angles.yaml`, and preflight fails on a mismatch —
slot and object angles only cancel while one estimator measures both.

For each shape: `1`–`5` to pick it, `R` and drag a box round that slot, wait for
the reading to settle, `SPACE`. Then **lift it out, seat it again, `SPACE` again
— at least three times.** The spread across seatings is the only honest measure
of the slot's play; the tool refuses `SPACE` until it has seen the slot empty.
`C` clears a shape, `S` saves. Paste the saved block into
`coordinates.place_slot_angles_deg`.

**If the jig does not fit in the camera's view**, slide it in and slide it back.
These are rotations, and sliding does not change one — only turning the jig
would. Push it along a straight edge; never let it twist.

The box matters: the blue box is what you drew, the green one is what was
measured. A green box round the jig plate reads perfectly steadily and is the
plate's angle, not the slot's.

| Problem | Meaning |
|---|---|
| marked **LOOSE** | play above 10% of the symmetry period — tolerable, but the placement must live inside it |
| `play` of 0.00–0.02° | a re-seat did not really happen; a hand cannot repeat to a hundredth of a degree |
| `n=1` or `n=2` | not enough seatings to judge the play |
| will not settle | glare, focus or light — the star is the most sensitive |

---

## 5. Deploy — one command

```powershell
.\deploy.ps1 <pi-address>     # ./deploy.sh on bash; the address is remembered
```

It runs the tests, builds the bundle, copies it, unpacks it, **checks that the
Pi's `config.yaml` hashes the same as this one**, and then runs preflight over
SSH. That check is the point: an unpack that did not overwrite leaves the Pi on
last week's calibration, and nothing about it looks wrong until the robot moves.

Add `-WithCamera` once the camera's cable is on the Pi, to run the marker and
lighting rows there too. `-SkipBuild` pushes the bundle already built.

Every later change to a number means: edit here, deploy again. One command, no
second copy of the truth.

**First time on a new Pi only:**

```bash
sudo apt install python3-tk
pip install ncnn pyyaml opencv-python numpy pillow
# pypylon needs the ARM64 Pylon SDK installed first
```

No ultralytics and no torch on the Pi: the Pi profile runs the exported model on
the 12 MB ncnn runtime, and torch's aarch64 wheel fills the disk before it
finishes.

---

## 6. On the Pi — three commands, no flags

```bash
cd ~/INA700/pi
./run.sh preflight     # is this Pi ready
./run.sh bench         # how fast the model runs here
./run.sh               # the window: live view, dropdowns, Start cycle
```

`./run.sh console` is the same system with a terminal instead of a window,
which is what works over plain SSH — Tk cannot open a display there.
`./run.sh help` lists the lot.

The wrapper exists for one reason: it carries `--config config/profiles/pi.yaml`
for you. The base config says `detector: yolo`, which the Pi cannot run, and
forgetting the flag fails in a way that reads like a broken model rather than a
wrong command. Anything you add is passed through — `./run.sh preflight
--no-camera` works.

The benchmark is the Pi's own answer and cannot be taken from the PC: expect
about **426 ms median**, first frame near 1 s — that is warm-up — against a
3000 ms budget.

Three ways in, all live at once under `pi-gui.yaml`:

| Route | How |
|---|---|
| the window | shape and colour dropdowns, **Start cycle** |
| the terminal that launched it | type `circle red`, enter |
| any other terminal | `echo "circle red" > /tmp/ina700.cmd` |

`status` lists what the camera sees right now, with X, Y, Rz and the fit per
object. `quit` shuts down cleanly. With the window up, the launching terminal
also carries the log, so type in a second terminal through the pipe — or set
`logging: console_level: WARNING` in `config/profiles/pi-gui.yaml`.

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
2. Ask for each in turn by shape and colour; press the yellow button each time.
3. Watch: picked from where it lies, placed in its own slot, turned to match.
4. A **second cycle without restarting the program** — that is the requirement
   being tested.
5. The printed inference time stays under 3 s. It should read ~0.4 s.

Count the placements as the examiner will: five of six correct orientation, at
least one of each shape, all three picked in each cycle.

Then, **before leaving**, export the station in RobotStudio (**Controller → Pack
and Go**), put the `.pgz` in `pack-and-go/`, and run from the project root:

```bash
python make_submission.py
```

That writes `FinalProject_SurajKarki.zip` with the program files, the trained
model and the Pack-and-Go, running the tests first. It refuses rather than
writing an incomplete or wrongly named zip — the course reports those as failed
with no resubmission.

The Pack-and-Go has to be the station as examined, and cannot be made
afterwards. If you edited the RAPID modules on the pendant, copy the text back
into `robot/` so the repo matches what the Pack-and-Go captured.

---

## 8. When something is wrong

| Symptom | First thing to check |
|---|---|
| nothing rotates | the fit scores in the log — below the gate it is lighting, not the robot |
| everything rotates the wrong way | `coordinates.angle_sign` |
| everything off by the same angle | the slot angles, and whether they were measured with the running estimator |
| picks land beside the object | `wobj1` and the four crosses, then the mapping gate |
| the Pi behaves differently from the PC | deploy again and read the hash line — they are not running the same config |
| "off board" refusals | `sheet.span_xy_mm` must match `SHEET_SPAN_X/Y` in `StationData.mod` |
| robot never connects | the server listens on `0.0.0.0:5000`; the address in `ServerCommuncatio.sys` must be the **Pi's**, not the PC's |
| camera sees too little | the `CROPPED` line in step 2 |

# At the station

Everything to do in the lab, in order. Each step says what to run, what it must
say, and what to do when it does not. `README.md` explains why the system is
built this way; this file is for standing at the bench.

Nothing here is optional reading in the 3-hour exam window: steps 1 to 4 are
about half an hour if nothing is wrong, and every later step inherits them.

Author: Suraj Karki · Course: INA700 — AI-based pick and place

---

## 0. Before leaving the desk — on the PC

```bash
cd pi
python -m pytest -q                                    # all green
python smoke_test.py --config config/profiles/mock.yaml   # two cycles, no hardware
python tools/offline_check.py --config config/profiles/offline.yaml
```

Then build the bundle, which runs the tests again and refuses to build on a
failure:

```bash
./rebundle.sh          # or .\rebundle.ps1 on Windows
```

**Rebuild after every change to `config.yaml`.** Every measured value travels
inside the bundle — marker centre, slot angles, exposure. A stale bundle is a Pi
running last week's calibration, and nothing about it looks wrong.

---

## 1. Copy it to the Pi — on the PC

```powershell
scp ina700-pi.tar.gz pi@<pi-address>:~/
ssh pi@<pi-address> "mkdir -p ~/INA700 && tar -xzf ~/ina700-pi.tar.gz -C ~/INA700"
```

Confirm the right code arrived — SSH is fine for this:

```bash
cd ~/INA700/pi
ls adapters/detection/shape_fit.py          # exists = this week's bundle
grep "kind:" config/config.yaml | head -3   # orientation kind, detector kind
grep -A3 place_slot_angles_deg config/config.yaml
```

If any of those disagree, the unpack did not overwrite. Fix it here — every
later step inherits the error silently.

**First time on a new Pi only:**

```bash
sudo apt install python3-tk
pip install ncnn pyyaml opencv-python numpy pillow
# pypylon needs the ARM64 Pylon SDK installed first
```

No ultralytics and no torch on the Pi. The Pi profile runs the exported model on
the 12 MB ncnn runtime; torch's aarch64 wheel fills the disk before it finishes.

---

## 2. Pre-flight — SSH is fine

```bash
python3 tools/preflight.py --length 100 --config config/profiles/pi.yaml
```

**Pass `--config`.** Without it preflight reads the base config, which says
`detector: yolo`, and judges a configuration the Pi never runs.

| Row | What it must say |
|---|---|
| packages, config | all `ok` |
| slot angles | `pasted; play ...` |
| **slot angle source** | `measured with 'fitted', which is what runs` |
| camera | opens; the log line reads **`the whole sensor`**, not `CROPPED` |
| marker detected | `ids [0]` in every frame |
| marker steady | jitter below **0.02** px/mm |
| **field of view** | covers the sheet; it fails with the shortfall in mm if not |
| lighting | 95th percentile **180–210**, nothing clipping |

A failing lighting row tells you what to change it to, e.g. `try
camera.exposure_us 11179 (it is 3000 now)`. Put that in `config.yaml`, rebundle,
run it again.

`CROPPED` means the camera is delivering part of its sensor — a crop someone
left in Pylon Viewer, which survives a power cycle and looks exactly like a
longer lens. The code resets it at every open; if it still says CROPPED, the
camera is refusing, and Pylon Viewer is where to clear it.

**slot angle source failing** means the stored slot angles were measured with a
different estimator than the one about to run. Re-measure them (step 5), or set
`orientation.kind` back to the one named. Mixing them puts every placement out
by the difference, silently.

Add `--no-camera` to skip everything needing the camera.

---

## 3. The model — SSH is fine

```bash
python3 tools/benchmark.py --config config/profiles/pi.yaml --count 20
python3 tools/offline_check.py --config config/profiles/pi.yaml
```

Expect about **426 ms median**, first frame near 1 s — that is warm-up. The
budget printed is 3000 ms.

`ModuleNotFoundError: ultralytics` means `--config` was dropped: only the Pi
profile uses ncnn.

---

## 4. The robot frame — the gate everything else stands on

### 4.1 Teach `wobj1` with the POINTER, not the cup

Manual mode, Jogging, tool = pointer, motion linear. Three points, each touched
**on the sheet surface** — they set the Z datum as well as the origin and axes:

| Point | Where |
|---|---|
| X1 | the sheet corner that is the origin — this point *is* (0, 0) |
| X2 | the far end of the **297 mm** edge |
| Y1 | along the 420 mm edge, as far out as you can reach |

Hover and sight down the pointer; do not press. Let the arm settle before
reading. Teaching with the cup instead of the pointer costs about 1.3 mm on
every pick, more than parallax and detection noise together.

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

### 4.2 Camera against robot — the mapping gate

Put one object down, read X and Y from the GUI, jog there, compare. Three
well-separated spots, one of them a corner. **Within 1–2 mm everywhere.**

| What you see | What it is |
|---|---|
| all off by the same amount | `aruco.marker_centre_xy_mm` |
| all off by the same percentage | `aruco.marker_length_mm` |
| X and Y swapped or rotated | `aruco.marker_angle_deg` |
| Y sign wrong | set `aruco.y_axis_flipped: true` |
| centre good, corners out | lens distortion; live with it |

### 4.3 Rotation sense

Place a **square** at roughly 45°, run one pick, watch it seat.

| What you see | Fix |
|---|---|
| turned the wrong way by twice the error | flip `coordinates.angle_sign` |
| close, but off by a constant | the slot angle — step 5 |
| circle fine, everything else wrong | almost always `angle_sign` |

If the wrist does not turn **at all**, hard-code it on the pendant for one
cycle, in `MainModule.mod`:

```rapid
RETURN RelTool(placeTargets{request.shapeIndex}, 0, 0, 0 \Rz:=30);
```

Turning there means `RelTool` works and the rotation is being lost earlier; not
turning means nothing on the Pi can fix it. Put `request.rotation` back after.

---

## 5. The jig — `wobj2` and the slot angles

Teach the placing work object at the jig and confirm `p10`–`p60` still land in
their slots.

```bash
python3 calibration/slot_angles.py --camera basler --config config/config.yaml
```

Pass the same `--config` the station runs: the tool builds its estimator from it
and records which one in `slot_angles.yaml`, and preflight fails on a mismatch.

For each shape: `1`–`5` to pick it, `R` and drag a box round that slot, wait for
the reading to settle, `SPACE`. Then **lift it out, seat it again, `SPACE`
again — at least three times.** The spread across seatings is the only honest
measure of the slot's play; the tool refuses `SPACE` until it has seen the slot
empty. `C` clears a shape, `S` saves. Paste the saved block into
`coordinates.place_slot_angles_deg`, rebundle, copy across.

**If the jig does not fit in the camera's view**, slide it in and slide it back.
These are rotations, and sliding does not change one — only turning the jig
would. Push it along a straight edge; never let it twist. Nothing else needs the
jig in frame: the placing positions live on the robot.

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

## 6. Run it

```bash
python3 main.py --config config/profiles/pi-gui.yaml   # window, needs a screen
python3 main.py --config config/profiles/pi.yaml       # console, SSH is fine
```

Three ways in, all live at once under `pi-gui.yaml`:

| Route | How |
|---|---|
| the window | shape and colour dropdowns, **Start cycle** |
| the terminal that launched it | type `circle red`, enter |
| any other terminal | `echo "circle red" > /tmp/ina700.cmd` |

`quit` shuts down cleanly. Typing `status` in the console view lists what the
camera sees right now, with X, Y, Rz and the fit score per object.

A cycle waits for the yellow button, picks, and places in that shape's slot.
With the window up, the launching terminal also carries the log, so type in a
second terminal through the pipe — or set `logging: console_level: WARNING` in
`config/profiles/pi-gui.yaml`.

---

## 7. What the orientation is telling you

The confidence is an **overlap with an ideal square or star**, 0 to 1 — not the
old harmonic strength. It is reported, never acted on: every object is placed at
the best angle available, and nothing is refused or left straight.

| What you see | What it means |
|---|---|
| fit above 0.85 | a clean silhouette; the angle is good to about half a degree |
| fit 0.6–0.8 | a decent reading, a degree or two out at worst |
| `the angle is a guess from N segmentation(s)` in the log | no mask fitted well, so the candidates' consensus was sent. Usually a pale object; side light fixes it |
| `no segmentation found an object in the crop` | the only case with no angle at all. Lighting, not code |

Read the guesses out of the log after a run — that is where to look if a
placement came out crooked. Nothing is shown on screen during the cycle.

---

## 8. The rehearsal — do this once before being examined

1. Lay out all three shapes on the sheet, not touching, at clearly different
   angles. The jig empty.
2. Ask for each in turn by shape and colour; press the yellow button each time.
3. Watch: picked from where it lies, placed in its own slot, turned to match.
4. Do a **second cycle without restarting the program** — that is the
   requirement being tested.
5. Check the printed inference time stays under 3 s. It should read ~0.4 s.

Count the placements as the examiner will: five of six correct orientation, at
least one of each shape, all three picked in each cycle.

---

## 9. Hand it in — before leaving the lab

Export the station in RobotStudio (**Controller → Pack and Go**), put the
`.pgz` in `pack-and-go/`, and run from the project root:

```bash
python make_submission.py
```

That writes `FinalProject_SurajKarki.zip` with the program files, the trained
model and the Pack-and-Go, and runs the tests first. It refuses rather than
writing an incomplete or wrongly named zip — the course reports those as failed
with no resubmission. `--pack-and-go <path>` takes the file from anywhere.

Do this at the station. The Pack-and-Go has to be the station as examined, and
it cannot be made afterwards.

---

## 10. When something is wrong

| Symptom | First thing to check |
|---|---|
| nothing rotates | the fit scores in the log — if they are below the gate it is the lighting, not the robot |
| everything rotates the wrong way | `coordinates.angle_sign` |
| everything off by the same angle | slot angles, and whether they were measured with the running estimator |
| picks land beside the object | `wobj1` and the four crosses; then the mapping gate |
| "off board" refusals | `sheet.span_xy_mm` must match `SHEET_SPAN_X/Y` in `StationData.mod` |
| robot never connects | the server listens on `0.0.0.0:5000`; the address in `ServerCommuncatio.sys` must be the **Pi's**, not the PC's |
| camera opens but sees too little | the `CROPPED` line in step 2 |

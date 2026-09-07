# INA700 Final Project — System Design

**Target grade: A** — Grade Level III functionality plus an object-oriented
architecture following SOLID.

---

## 1. The system in one paragraph

A Basler camera looks down at a picking area. A Raspberry Pi 4 runs a trained model
that finds the **three shapes assigned by the instructor**, measures each one's
position and orientation, converts those pixels into **picking work object**
millimetres using an ArUco marker fixed on the table, and sends one object at a time
to an ABB robot over TCP. The operator presses the **yellow button**; the robot picks
the object with a **vacuum cup**, turns its wrist by the amount the server calculated,
and seats the object in its slot in the **placing work object**. Then it waits for the
next button press. Forever.

### What this project inherits

| | What it established | What carries forward |
|---|---|---|
| **Step 1** | Pick and place with teach-pendant selection, two work objects, ≤5 robtargets, yellow button, vacuum DO | The entire robot motion design, unchanged |
| **Ex. 2** | Threading and OOP: a `Camera` class, an `ArUco` class, one thread each | Both class names and both responsibilities, kept intact |
| **Step 2** | Object selection arrives over a socket; robot splits the message for X and Y | The protocol and the parser, extended with Rz, shape and colour |
| **Final** | The server is now a vision system rather than a person typing | Everything on the Pi |

The robot program is therefore **Step 1's program with a different source of
coordinates**. That is deliberate: it is the part that must work under exam pressure,
so it stays the part that has already been proven twice.

---

## 2. Requirements and where each one lives

| # | Requirement | Source | Home in the design |
|---|---|---|---|
| R1 | Detect 3 assigned shapes; **ignore** the other 2 | PDF | Training data + `AllowedShapeSelector` |
| R2 | Extract position **and** orientation | PDF | `YoloDetector` + `HarmonicOrientationEstimator` |
| R3 | Pixels → work object coordinates, via **ArUco** | README | `ArucoCalibrator` + `MutableHomographyMapper` |
| R4 | Send data to the robot over a server | PDF | `TcpServerTransport` + `MessageCodec` |
| R5 | GUI showing position and orientation | PDF | `TkView` |
| R6 | **Multithreading**, one distinct job per thread | PDF | `infrastructure/runtime.py` |
| R7 | Robot: client comms, dynamic pick, fixed place | PDF | `MainModule.mod` |
| R8 | Pick only a chosen colour | PDF | `HsvColourClassifier` + `ColourRequestSelector` |
| R9 | Unlimited cycles, user selects the object | PDF | `CycleController` + GUI + yellow button |
| R10 | Inference **< 3 s**, printed | PDF | `VisionPipeline` timing |
| R11 | 5 of 6 placed correctly; ≤2 retries | PDF | `place_rotation_deg` + `CycleController._object_was_lifted` |
| R12 | Two work objects | Step 1 | `wobjPick`, `wobjPlace` |
| R13 | **≤5 robtargets** + approach + home | Step 1 | Five used, doubling as pick reference and slots |
| R14 | Survives a reprogrammed work object | Step 1 | No absolute positions anywhere |
| R15 | Yellow button starts each pick | Steps 1–2 | `RunPickCycle` |
| R16 | Split the message for X and Y | Step 2 | `MainModule.WordAt` |
| R17 | No code inside `ServerCommuncatio.sys` | Step 2 | It is only ever called |
| R18 | Clean code: no deep nesting, no duplication | Course | Early returns, one helper per concept |

---

## 3. The shape of the system

Two machines, two work objects, one marker.

```
        Raspberry Pi 4  (192.168.125.201)              ABB robot  (192.168.125.3)
        ──────────────────────────────               ─────────────────────────
        Basler camera                                     yellow button
             │                                                  │
        capture ─▶ inference ─▶ coordinates ──TCP──▶  MainModule ─▶ PickPlace
             │         │             │        5000        │            │
             │    ArUco marker   wobjPick                 │       wobjPick (pick)
             │    re-solves the                           │       wobjPlace (place)
             └──▶ Tkinter GUI    mapping every frame       └── vacuum cup
```

**The division of labour is the important part.** The Pi knows only the *picking*
work object — it is the only frame the camera can see, because the marker defines it.
The placing jig is entirely the robot's business. Consequence: reprogramming the
placing work object needs **no change on the Pi at all**, and the vision system can
never send a wrong placing position because it never computes one.

---

## 4. The Pi application

Dependencies point **inwards only**. The domain knows nothing about OpenCV, sockets
or Tkinter.

```
┌──────────────────────────────────────────────────────────────┐
│ adapters/    Camera · ArUco · YOLO · Homography · TCP · Tk    │  I/O, swappable
├──────────────────────────────────────────────────────────────┤
│ ports/       FrameSource · ObjectDetector · SceneCalibrator   │  abstract (ABC)
│              CoordinateMapper · RobotTransport · Selector     │
├──────────────────────────────────────────────────────────────┤
│ application/ VisionPipeline · CoordinateService               │  use cases
│              CycleController · SharedState · selectors        │
├──────────────────────────────────────────────────────────────┤
│ domain/      Detection · WorldPose · Shape · marker · geometry │  pure rules
└──────────────────────────────────────────────────────────────┘
```

| SOLID | Where it is visible |
|---|---|
| **S**ingle responsibility | `Camera` only acquires. `ArUco` only detects and draws markers. `ArucoCalibrator` only turns a detected marker into a coordinate frame. `TcpServerTransport` only moves bytes. |
| **O**pen/closed | Adding "pick the leftmost first" is a new `ObjectSelector` appended to the chain in the container. `CycleController` is never edited. |
| **L**iskov | `FileFrameSource` substitutes for `BaslerFrameSource`; `LoopbackTransport` for the real robot. The whole system runs on a laptop because of this. |
| **I**nterface segregation | `SceneCalibrator` exists precisely because a calibrator needs the whole frame while a `CoordinateMapper` needs only a point. Forcing them into one interface would have been the easy, wrong choice. |
| **D**ependency inversion | `infrastructure/container.py` is the only file that names a concrete class. Change the config, get a different system. |

**Carried forward from Exercise 2.** That exercise established a `Camera` class for
acquisition and display and an `ArUco` class for detection and drawing, one thread
each. Both survive here under the same names and with the same jobs — `Camera`
additionally implements the `FrameSource` port so a file replay can stand in for it,
and `ArUco` is *used by* `ArucoCalibrator` rather than being extended into it. Marker
detection and coordinate-frame construction are two responsibilities, so they are two
classes; the standalone `aruco_check.py` reuses `ArUco` alone, which is only possible
because of that split.

**The evidence the structure works:** ArUco calibration was added after the design was
finished, and it cost one new port, one new adapter and two config keys. Nothing in
`application/` changed.

---

## 5. Threading (R6)

| Thread | Its one job |
|---|---|
| `capture` | grab frames, keep only the newest (optionally show Exercise 2's `Output` window) |
| `inference` | ArUco calibration + model + orientation + colour, timed |
| `connection` | bring the robot link up, track its status |
| `cycle` | run one pick-and-place per operator request |
| main | Tkinter — Tk must own the main thread |

Rules that keep it safe: bounded `queue.Queue(maxsize=2)` between stages so a slow
stage drops stale frames instead of growing memory; one `SharedState` behind an
`RLock` handing the GUI **immutable snapshots**; a single `shutdown` Event every loop
checks; a timeout on every blocking call.

---

## 6. Vision (R1, R2, R10)

**Model:** YOLO11n trained on your three shapes only, exported to **NCNN**, run at
**320×320**. On a Pi 4 that is roughly 0.3–0.9 s — inside the 3 s budget, with the
measured time printed every cycle and shown in the GUI.

**Making it ignore the other two shapes (R1):** include them in the training photos
**unlabelled**. They become hard negatives and the model learns to leave them alone.
Training only on three shapes without ever showing the other two is how a star ends
up classified as a hexagon.

**Position and angle:** the network gives class and bounding box; inside that box,
classical CV measures precisely. The network recognises, geometry measures — faster and
more precise than an oriented-box model on a Pi.

**The angle is read from a harmonic, not a bounding rectangle.** `cv2.minAreaRect`
returns an angle unique only modulo 90°, which fits a square and nothing else: a star
repeats every 72° and a hexagon every 60°, and neither divides into 90. It is also
unstable on a star, where which pair of points defines the rectangle can flip between
frames and jump the angle.

Instead the outline becomes a radius-versus-direction signature, and the harmonic
matching the shape's symmetry order is read off:

```
Z = Σ r_k · exp(i · N · θ_k)          orientation = arg(Z) / N
```

Rotating the object by α multiplies Z by exp(i·N·α), so the phase *is* the orientation.
Two properties earn their keep:

- **The answer arrives already folded.** `arg()` lands in (−π, π], so dividing by N
  lands in ±180/N — the shape's own symmetry period. A star comes out within ±36°
  with no separate folding step.
- **|Z| is a free confidence measure.** A circle has no N-th harmonic, so the magnitude
  collapses and the estimator reports *no rotation* rather than noise. Below
  `min_confidence` it refuses, which is the honest answer when a mask is ragged.

`tests/test_orientation.py` builds stars, squares, triangles and hexagons analytically,
rotates them by known amounts, and checks the estimator recovers those rotations to
0.1° — so the shape most likely to lose placement marks is tested long before the lab.

`tools/orientation_probe.py` repeats that on **real photos**, with no labels: it
rotates the image by a known amount and requires the reported angle to follow.
On the lab dataset that gives 1.5° median where `|Z| ≥ 0.10`, and 12° where
`|Z| < 0.05` — which is what sets `min_place_confidence`.

**A weak angle is refused, not guessed.** Reporting 0° when the outline is
unreadable is only honest if something acts on it, so `Detection` carries
`angle_confidence` and `OrientationConfidenceSelector` drops the object before it
reaches the robot. `Shape.is_rotationally_free` exempts the circle, whose angle is
meaningless by definition. Skipping a pick is recoverable; seating a star 30° out
is not.

**Colour (R8):** hue voting over the object's own pixels, in its own class.

Two things this gets right that the obvious version does not. It classifies the
**object, not the box** — a star fills barely a third of its bounding box, so a
median over the box measures paper, and every black star came out white until
this was fixed. `adapters/detection/segmentation.py` provides the mask, shared
with the orientation estimator so there is one definition of "the object".

And white and black carry **no hue at all**, so they cannot be named by a hue
range. They are decided on brightness relative to the paper — fractions of its
95th percentile rather than fixed levels, so the answer survives the sheet
ranging 67-162 across shooting sessions.

The older version: HSV masking inside the box, in its own class, so a colour threshold
can never break shape detection.

---

## 7. Calibration — the ArUco marker (R3)

A 5×5 ArUco marker is **fixed permanently** on the table. Every frame it is detected
and its four corners are matched against the same four corners in millimetres.

**Why four corners rather than the perimeter ratio in the course notes.**
`aruco_perimeter / (length × 4)` gives *scale only*, and only if the camera looks
exactly straight down. Four corners give **scale, origin and rotation together** and
cancel the perspective error of a tilted camera — same marker, same detection call,
strictly more information. The perimeter ratio is still computed as an **independent
cross-check**: a disagreement over 15% means the marker was misread or
`marker_length_mm` is wrong, and the calibration is rejected rather than used.

**Why solve it live.** If the camera is knocked between setup and the demonstration,
the system corrects itself on the next frame. A one-off calibration would go on
quietly picking in the wrong place.

The marker length used throughout the course material is **100 mm** — that is the
config default, and the supplied rubber marker is made to that size, so
`marker_length_mm: 100.0` is simply correct.

**The marker does not have to sit at `wobj1`'s origin.** `marker_centre_xy_mm` takes
any offset, measured by jogging the tool tip to the marker centre. Putting the origin
on the marker would make it `[0, 0]`, but the marker must stay clear of the picking
area, and moving `wobj1` shifts `Papproach`, `PICK_SURFACE_Z_MM` and the `PICK_AREA_*`
bounds with it. Measuring one offset against an already-proven work object is the
cheaper trade, and Stage 6 catches any error in it as a uniform shift.

**Mount the marker at object-top height.** The homography maps the image onto the
plane the marker lies in, while the camera sees the objects' *top* faces. Calibrated
on the board plane, every object is reported displaced outward by about `r·h/H` —
roughly 2 mm for 10 mm objects at 150 mm from centre under a camera 800 mm up. It is
systematic, worst at the corners, and looks like lens distortion except that it points
outward. Every object is the same thickness, so a shim removes it entirely.

**Before trusting anything:**

```bash
python calibration/aruco_check.py --length 100 --camera basler
```

Shows detected IDs, px/mm, and the **jitter** over 60 frames. Above roughly
0.02 px/mm the detection is unstable and no downstream tuning will rescue the
accuracy — fix focus, lighting and glare first.

`cv2.aruco` requires **opencv-contrib-python**. Plain `opencv-python` does not include
it, whatever the course README's install line says.

---

## 8. The vacuum rule — this is what earns R11

A suction cup changes the orientation problem completely, and getting it backwards is
the easiest way to lose the placement marks.

The cup grabs the object **wherever it lies**. The robot therefore picks **straight
down** at a fixed wrist angle, and the object arrives on the cup still at its own
angle. To seat it in a slot cut at angle `S`, the wrist must turn by `S − θ` at
**placing** — not by `θ`, and not by `−θ`.

So the server sends **the rotation the robot applies when placing**, already reduced
into the shape's own symmetry:

| Shape | Symmetry | Largest turn ever needed |
|---|---|---|
| Circle | infinite | 0° — never rotates |
| Square | 90° | 45° |
| Triangle | 120° | 60° |
| Star (5-point) | 72° | 36° |
| Hexagon | 60° | 30° |

A square measured at 273° is corrected by 3°, not 273°. Long wrist travel and
axis-limit errors disappear.

`tests/test_geometry.py` proves the defining property directly: for every shape and
every angle, `object + rotation ≡ slot (mod period)`. If that holds, the object fits.

---

## 9. Protocol (R4, R16)

Grown from the working minimal exercise, which sent `move square`. It now carries
the coordinates the camera measured.

```
server → robot   move circle 123.45 -45.30 -12.5#     (30 chars)
server → robot   quit#
robot  → server  DONE: circle#
robot  → server  ERROR: unknown shape 'blob'#
```

Words separated by spaces, `#` ends a message. The robot splits it with `StrFind` /
`StrPart` / `StrToVal` — exactly the elements Step 2 requires.

**Colour is not sent.** The operator types `circle red` at the terminal, but working
out which object is a red circle is the server's job. The robot needs only where the
object is and which slot it belongs in, so colour stops at the server. One less field
on the wire and one less thing for the RAPID parser to get wrong.

**A RAPID `string` holds 80 characters** and the controller truncates silently past
that. The longest possible command is about 34; a unit test proves every shape stays
inside the limit at extreme coordinates.

**Two-way framing.** TCP is a byte stream, so one read can return half a message or
two at once. Both ends terminate with `#`: the server buffers until it sees one, and
the robot treats `#` as a word separator so the terminator never sticks to the last
number.

X and Y are absolute in the picking work object. Rz is the **placing** rotation from §8.
X, Y and the shape are all **required**: the objects lie wherever they were dropped, so
a command without coordinates describes nothing and is refused. Only Rz may be omitted,
because a circle needs no turning.

## 10. The robot program (R7, R12–R17)

Two modules, plus the course's `ServerCommuncatio.sys` which is **only called, never
edited** apart from its server address.

| Module | Holds |
|---|---|
| `StationData.mod` | every value taught or measured on this cell — `vac`, `wobj1`, `wobj2`, the seven robtargets, the shape catalogue, speeds, timings, protocol strings |
| `MainModule.mod` | the program — command loop, parsing, motion, gripper |

The split is along the line that matters in practice: **re-teaching the cell touches
`StationData` only**, and `MainModule` contains no coordinate, speed or timing of its
own. The clean-code brief asks for small focused functions rather than many modules,
so two is enough — and every value in `StationData` is one already proven on hardware.

### The robtarget budget (R13) — and the trick that pays for it

Five are allowed for picking and placing, plus one approach and one home. Exactly
five are used: `p10`, `p30`, `p40`, `p50`, `p60`.

In the minimal exercise they covered **both** ends of the job: resolved against `wobj1`
a target was where that shape sat, resolved against `wobj2` the *same* target was its
slot in the jig. Two frames, one set of numbers.

Now that the objects are scattered at random, only the placing half survives — hence
the array is named `placeTargets`. The picking pose is computed instead, and it is the
same for every shape: all the objects are one thickness and the cup always descends
vertically, so only X and Y change. `PICK_SURFACE_Z_MM` is a single constant and
`Papproach` supplies the tool orientation.

That single constant matters. The five taught Z values span −0.23 to 5.20 mm, which is
hand-jogging scatter rather than real thickness — inheriting them would drive the cup
into the board at one target and leave it short of a seal at another.

### The objects are placed at random — what that costs

Figure 1 of the instructions shows the layout: shapes scattered loose on the picking
board, the slotted jig alongside. Picking is therefore entirely camera-driven, and the
taught `p10`–`p60` X and Y are **dead numbers at picking time**. The picking pose is computed from
`Papproach` (for the tool orientation) plus the camera's X and Y and one height
constant — it carries no shape data at all, because with equal thicknesses the pick is
identical for every shape. The shape only decides where the object *goes*.

There is deliberately **no fallback to a taught position**. Picking at yesterday's spot
would drive the cup into a bare board, so a command without coordinates is refused.

**Arm configuration cannot be taught for a computed target**, so `ConfL \Off` and
`ConfJ \Off` are set at start-up. Without them the controller checks each computed pose
against a stored configuration and stops mid-board with a configuration error. Watch the
first few picks and confirm the arm takes a sensible posture.

Random placement also removes the only cheap sanity check. With objects at fixed positions a wrong
coordinate is obvious; with random ones, a miscalibrated camera reports a plausible
number and is simply believed. `PickPointIsOnTheBoard` fences the picking area in
`wobj1` millimetres, turning a bad coordinate into a refused command instead of a
collision. **Measure the real board and widen those four constants** — they must cover
every position an object can occupy.

### Clean code (R18)

- Early returns instead of nested `IF` — `RunVisionCycle` is flat.
- `FieldAt` is written once and used for all seven fields.
- One procedure, one job: `VacuumOn`, `PickTargetFor`, `OperatorConfirmsStart`.
- Names say what they mean: `abovePick`, not `p10`.
- Every cell-specific number lives in `StationData` and nowhere else.

### Required RAPID elements — coverage

| Element | Where |
|---|---|
| TCP / work object calibration | `StationData`: `vac`, `wobj1`, `wobj2` |
| `FUNC` | `OperatorConfirmsStart`, `HandleCommand`, `ParseCommand`, `WordAt`, `ShapeIndexOf`, `PickTargetFor`, `PlaceTargetFor` |
| `PROC` | `main`, `PrepareCell`, `RunCommandLoop`, `RunPickCycle`, `PickAndPlace`, `VacuumOn`/`Off` |
| `IF` | mode selection, parse guards, grip check |
| `WHILE` / `FOR` | cycle loops; `FOR` in `ShapeIndexOf` |
| `MoveL` / `MoveJ` | descent and release / travel |
| `Offs` | every derived position |
| `Set` / `Reset` | `VacuumOn` / `VacuumOff` — note these replace `SetDO`, which does not satisfy the required element |
| `WaitDI` | `RunPickCycle` |
| `WaitTime` | grip settle, release, debounce |
| `TPWrite` | status throughout |
| `TPReadFK` | `OperatorConfirmsStart` — object selection itself comes from the server terminal |
| `StrFind`, `StrLen`, `StrPart`, `StrToVal` | `WordAt`, `ParseCommand` |
| `StrMap` | `ShapeIndexOf` case folding |
| `wobjdata`, `robtarget`, `num`, `string`, `bool`, array | `StationData`, `MainModule` |

---

## 11. Build order

| Phase | Work | Why here |
|---|---|---|
| 0 | ✅ Scaffold, domain, ports, mocks, 54 unit tests | everything after is testable on a laptop |
| 1 | Dataset: 200–300 photos, varied light and position, the two forbidden shapes present but **unlabelled** | biggest single driver of final accuracy |
| 2 | Train YOLO11n, export NCNN, benchmark on the Pi, confirm < 3 s | fail fast if the model is too slow |
| 3 | Mount and measure the marker; `aruco_check.py` until jitter is low | nothing downstream is meaningful before this |
| 4 | Measure the marker's position in `wobj1`; teach `wobjPlace`; measure slot angles | needs the station |
| 5 | Load the RAPID modules; prove **manual mode** end to end | Step 1 working again = a safety net |
| 6 | Connect the socket; prove vision mode with one shape | one variable at a time |
| 7 | Verify `angle_sign` and `y_axis_flipped` with two deliberate test picks | mirrored coordinates are silent and fatal |
| 8 | Two full cycles, colour filter, operator-selected object | the exam scenario |
| 9 | Comments, naming pass, Pack-and-Go, `FinalProject_StudentName.zip` | a wrongly named ZIP is an automatic fail |

---

## 12. Risks, and what is already done about them

| Risk | Mitigation in place |
|---|---|
| Pi inference too slow | 320px NCNN; drop to 256 if needed; timing printed every cycle from day one |
| Marker mounted below object-top height | shim it level with the object tops; otherwise expect an outward error growing toward the corners |
| Camera knocked before the demo | live calibration re-solves every frame |
| Marker briefly covered | `hold_last_good: true` keeps the last good calibration |
| Angle sign or Y mirrored | two config flags, each verified with one test pick |
| RAPID string truncation | 36-char protocol, proven by test |
| Vision server dies in the exam | manual mode still demonstrates pick and place |
| Tool calibration eats the 3 hours | tool referenced symbolically; only `StationData` changes |
| Lighting differs from training day | shoot the dataset in the lab, at lab light, plus augmentation |

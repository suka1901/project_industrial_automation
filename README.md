# INA700 — AI-based pick and place

A Basler camera looks down at an A3 sheet. A trained YOLO model finds three
assigned shapes on it, measures each one's position and orientation, converts
pixels into the robot's work-object millimetres, and sends a picking command
over TCP. An ABB robot picks with a vacuum cup and places each shape in its
fixed slot.

Author: Suraj Karki
Course: INA700 — AI-based pick and place, University West

**Assigned shapes: circle, square, star.** Hexagon and triangle must never be
detected or acted on.

- **[STEPS.md](STEPS.md)** — every practical step, in order, from testing with
  no hardware through to the full rehearsal. Start there.

---

## Layout

```
INA700/
├─ README.md              this file: what it is and why it is built this way
├─ STEPS.md               how to run, test, calibrate, train and deploy
├─ pi/                    the vision application (Python)
├─ robot/                 RAPID modules for the ABB controller
├─ model/                 trained weights, dataset, training notebook
├─ docs/                  course material, UML diagrams, the untouched server file
└─ ServerCommuncatio.sys  course-supplied, one line changed (see below)
```

## Running it right now, with no hardware

```bash
cd pi
python -m unittest discover -s tests      # 68 tests
python smoke_test.py --config config/profiles/mock.yaml
```

Full detail, including the tests that use the real trained model, is in
[STEPS.md](STEPS.md).

---

The UML diagrams are `docs/uml/*.puml`:

| File | Shows |
|---|---|
| `01-overview` | the layering, one adapter per port |
| `02-domain` | the frozen value types and enums |
| `03-ports-vision` | camera, detector, orientation, colour |
| `04-ports-mapping-comms` | coordinates, ArUco, transports, GUI |
| `05-application` | pipeline, cycle controller, the selector chain |
| `06-runtime` | the threads and the queues between them |

```bash
plantuml -tpng docs/uml/*.puml
```

## Design

### Layers

Dependencies point inward only. Nothing in `domain` knows that OpenCV, YOLO,
Tkinter or sockets exist.

```
domain/          shapes, angles, the harmonic maths     no I/O, no libraries
ports/           nine abstract interfaces                what the app needs
application/     pipeline, selectors, cycle controller    policy
adapters/        camera, YOLO, ArUco, colour, GUI, TCP    the outside world
infrastructure/  Container, threads, logging              wiring
```

**One configuration, three overlays.** `config/config.yaml` is the lab profile
and the only file holding measured values. `config/profiles/*.yaml` list only
what they change — a dozen lines each — and `extends` pulls in the base:

| Profile | Changes |
|---|---|
| `mock` | synthetic camera, mock detector, passthrough colour, loopback robot |
| `offline` | saved photos, identity mapper, loopback robot |
| `pi` | NCNN weights instead of PyTorch |

Four full copies had already drifted — the mock said `exposure_us: 8000` where
the lab said `3000` — and a value measured at the station would have had to be
copied into three files by hand. Now there is one place to change.

`Container` reads the merged configuration and builds everything. Swapping the mock
detector for the trained model, or a file of photos for the camera, is a
configuration edit — which is why the same code runs on the laptop and the Pi.

### Threads

Each thread owns one job, as the assignment requires.

| Thread | Does |
|---|---|
| capture | pulls frames off the camera |
| inference | ArUco calibration, model, orientation, colour — timed |
| connection | accepts the robot and holds the socket |
| cycle | runs a picking cycle when the operator asks |
| main (Tk) | the GUI |

Frames pass through bounded queues holding two items, so a slow consumer drops
stale frames instead of growing a backlog. Shared state sits behind an `RLock`
and hands out immutable snapshots, so the GUI can never read a half-written
update.

### Orientation is read from a harmonic, not a bounding rectangle

`cv2.minAreaRect` gives an angle unique only modulo 90°, which fits a square and
nothing else. It also jumps on a star as the defining pair of points changes.

Instead the outline becomes a radius-versus-direction signature, and the N-th
harmonic is taken, where N is the shape's symmetry order — 5 for a star, 4 for a
square, 3 for a triangle, 6 for a hexagon:

```
Z = Σ r_k · exp(i · N · θ_k)          orientation = arg(Z) / N
```

Rotating the object by α multiplies Z by exp(i·N·α), so the phase *is* the
orientation. Three things follow:

- The answer arrives already folded into ±180/N — the shape's own symmetry
  period. A star comes out within ±36° with no separate folding step.
- **|Z| is a free confidence measure.** A circle has no N-th harmonic, so the
  magnitude collapses and the estimator reports *no rotation* rather than noise.
- Because the model only has to *find* the object, training can rotate and flip
  the images freely. A system that regressed the angle from the network could
  not.

A weak angle is refused rather than guessed: `Detection` carries
`angle_confidence`, and `OrientationConfidenceSelector` drops the object before
it reaches the robot. `Shape.is_rotationally_free` exempts the circle. Measured
on the held-out photos: above |Z| 0.10 the angle held to 1.5°; below 0.05 it was
12° out. Skipping a pick is recoverable, seating a star 30° out is not.

### Colour is judged on the object, not the box

A star fills barely a third of its bounding box, so anything averaged over the
box measures paper. `adapters/detection/segmentation.py` provides the object
mask, shared with the orientation estimator so there is one definition of "the
object".

White and black carry no hue, so a hue range can never name them. They are
decided on brightness relative to the paper — fractions of its 95th percentile
rather than fixed levels, so the answer survives the sheet ranging 67–162
between shooting sessions.

### Coordinates come from the marker, every frame

A 100 mm ArUco marker (DICT_5X5_100, ID 0) sits in view. Its four corners give a
homography from pixels to work-object millimetres:

```
[x' y' w']ᵀ = H · [u v 1]ᵀ            x = x'/w'   y = y'/w'
```

Four corners rather than a scale factor, because a homography also absorbs the
camera not being perfectly perpendicular. It is re-solved on every frame, so a
nudged camera corrects itself instead of silently reporting stale positions.

The marker must sit at **object-top height**: the camera sees the objects' top
faces, and calibrating on the board instead puts every object outward by about
`r·h/H`, worst at the corners.

### The vacuum cup decides where rotation happens

A cup picks straight down and does not care how the object is turned. The wrist
turn therefore belongs at **placing**, not picking:

```
rz = fold(slot_angle − object_angle)
```

### Division of labour

The Pi knows only `wobj1`, the picking sheet. The robot owns `wobj2` and the
slots. The protocol carries shape, x, y and angle — never colour, which is a
selection rule, not something the robot needs.

```
server → robot   move circle 123.45 -45.30 -12.5#      or   quit#
robot  → server  DONE: circle#                          or   ERROR: ...#
```

`#` terminates a message so two replies in one TCP read stay separable, and the
codec guards the 80-character limit RAPID imposes on `string`.

### Robot side

Two modules: `StationData.mod` for taught values, `MainModule.mod` for logic.
Two work objects, five `robtarget`s plus approach and home, a yellow button to
start each pick, vacuum on a digital output. The picking fence derives from one
measured corner of the A3 sheet, so re-teaching `wobj1` costs two numbers rather
than four.

`ServerCommuncatio.sys` is course-supplied and contains **no student code**. The
only edit is line 52, the PC address, `192.168.125.2` → `192.168.125.201`. The
untouched original is at `docs/ServerCommuncatio.sys.original`; `diff` shows the
single change.

---

## Is this object-oriented? The evidence

The grade asks for "a well-designed architecture and object-oriented
programming principles", so here is the case, with numbers rather than claims.

**Paradigm: object-oriented at the seams, functional at the core.** That split
is deliberate. Anything with identity, state or a collaborator is a class; the
angle and geometry maths has none of those, so it is pure functions over frozen
values. Claiming pure OOP would mean wrapping `wrap_deg` in a class to no
benefit.

### The four pillars, in this code

| Pillar | Where | Evidence |
|---|---|---|
| **Abstraction** | `ports/interfaces.py` | 9 `ABC` ports. The application layer names no concrete class |
| **Encapsulation** | throughout | 192 private attributes against 1 public; 12 frozen dataclasses that cannot be mutated after construction |
| **Inheritance** | 31 edges | Every one implements a port or `Enum`. Nothing inherits from a concrete adapter |
| **Polymorphism** | 21 adapters | `FrameSource` has 3, `ObjectSelector` has 7. Swapping one is a config edit |

```
ColourClassifier      2   HsvColourClassifier, PassthroughColourClassifier
CoordinateMapper      2   IdentityMapper, MutableHomographyMapper
FrameSource           3   Camera, FileFrameSource, SyntheticFrameSource
ObjectDetector        2   MockDetector, YoloDetector
ObjectSelector        7   AllowedShape, Confidence, OrientationConfidence,
                          ShapeRequest, ColourRequest, NearestToOrigin, Composite
RobotTransport        2   LoopbackTransport, TcpServerTransport
```

### SOLID

| | Where |
|---|---|
| **S**ingle responsibility | One thread, one job. `MessageCodec` encodes; `RobotCommander` converses; `TcpServerTransport` moves bytes |
| **O**pen/closed | A new picking rule is a new `ObjectSelector` added to the chain in the container. `CycleController` is never edited — that is how `OrientationConfidenceSelector` was added |
| **L**iskov | `Camera`, `FileFrameSource` and `SyntheticFrameSource` are interchangeable. The offline profile proves it: the same `VisionPipeline` runs on saved photos |
| **I**nterface segregation | 9 narrow ports rather than one "vision system". `ColourClassifier` has a single method |
| **D**ependency inversion | `Container` is the only file that names a concrete class. Everything above depends on the abstractions |

### Patterns used

**Strategy** — every port. **Composite** — `CompositeSelector` holds a list of
`ObjectSelector` and is one itself, so a chain and a single rule are
interchangeable. **Template method** — `Worker.run()` fixes the thread lifecycle
and subclasses supply `step()`. **Adapter** — every class in `adapters/`.
**Dependency injection** — constructor injection throughout, wired in one place.

### It is enforced, not just described

`tests/test_architecture.py` reads the imports and fails if a dependency ever
points outward, if the core acquires a framework, if a port loses its
implementation, or if anything inherits from a concrete adapter:

```
domain/geometry.py imports 'cv2'. The core must not depend on I/O or a framework.
```

That is the answer to "how do you know it stayed object-oriented?" — the
document cannot drift from the code, because the test would fail first.

## Requirements

### Mandatory

| Requirement | Where |
|---|---|
| Multithreading, one job per thread | `infrastructure/runtime.py` |
| AI inference — shape, position, orientation | `YoloDetector` + `HarmonicOrientationEstimator` |
| Coordinate translation pixel → work object | `adapters/mapping/`, ArUco homography |
| Server communication Pi → robot | `TcpServerTransport`, `MessageCodec` |
| GUI showing position and orientation | `adapters/gui/tk_view.py` |
| Robot: client communication | `MainModule.mod` |
| Robot: dynamic picking | `PickTargetFor` |
| Robot: fixed-position placing | `placeTargets{5}` in `wobj2` |
| Must not respond to the other two shapes | 3-class model — it cannot emit them — plus `AllowedShapeSelector` |

### Grade Level III

| Requirement | Where |
|---|---|
| Colour detection, pick only a specified colour | `ColourRequestSelector` |
| Infinite cycles without restart | `CycleWorker` |
| User input selects the object | GUI shape and colour dropdowns |
| Retry up to two times | `max_attempts: 3` — first try plus two retries |
| Inference under 3 s, time printed | printed every cycle; 118 ms measured on x86 |
| Organised, named, commented | 63 modules, 78 tests, author header on each file |

Grade A additionally asks for a well-designed architecture and OOP — the layers,
ports and composition root above.

---

## Model

Trained on 216 images, validated on 55 held out:

| Class | Instances | P | R | mAP50 | mAP50-95 |
|---|---|---|---|---|---|
| all | 114 | 0.962 | 0.905 | 0.985 | **0.826** |
| circle | 31 | 1.000 | 0.943 | 0.995 | 0.828 |
| square | 32 | 1.000 | 0.792 | 0.983 | 0.819 |
| star | 51 | 0.886 | 0.980 | 0.977 | 0.831 |

Square misses about one in five; star over-fires about one in nine. Detection
confidence is 0.6 rather than 0.5, because a forbidden shape reaching the robot
is worse than a missed pick — the operator can simply ask again.

Read `mAP50-95`, not `mAP50`: everything sits near 0.98 there, so it cannot
discriminate. And the photos repeat heavily, so a stratified random split puts
near-duplicates on both sides — 0.826 is honest but flattering. The number that
settles it is agreement with the robot at bench step A7.

Dataset: 345 photos, 271 labelled — 560 boxes and 43 empty hard negatives. The
hexagon and triangle photos carry no labels at all, which is what teaches the
model to stay quiet on them.

---

## Status

| Phase | State |
|---|---|
| Architecture and code | Done — 63 modules, 78 tests green |
| Robot programs | Done — proven on hardware for the minimal exercise |
| Camera and marker calibration | Partly — the marker needs remounting |
| Dataset and labelling | Done |
| Training | Done |
| Robot measurements | **Not started — the critical path** |
| Pi deployment | Not started — the Pi is set up in the lab, not yet benchmarked |

### Still placeholders

| Value | File | Measured at |
|---|---|---|
| `marker_centre_xy_mm`, `marker_angle_deg` | `pi/config/config.yaml` | A6 |
| `place_slot_angles_deg` | `pi/config/config.yaml` | A10 |
| `y_axis_flipped`, `angle_sign` | `pi/config/config.yaml` | A8, A9 |
| `verify_tolerance_mm` → 10–15 | `pi/config/config.yaml` | before the lab run |
| `SHEET_ORIGIN_X`, `SHEET_ORIGIN_Y` | `robot/StationData.mod` | A11 |
| `PICK_SURFACE_Z_MM` | `robot/StationData.mod` | A11 |

Also switch `detector.kind` to `yolo`, `robot.transport` to `tcp`, or use
`profiles/pi.yaml` which already has both.

### Known risks

**The marker is a printed paper sheet, wrinkled, lying where objects land.** It
should be the 100 mm rubber one, shimmed, clear of the A3. Every robot-side
number inherits it, so remount before booking robot time.

**Lighting is uncontrolled.** Sheet brightness ranged 67–162 at fixed exposure.
`preflight.py` reports it and gates on 180–210.

**Square has the fewest photos** at 38, so its recall degrades first.

---

## Hand-in

A single ZIP named exactly **`FinalProject_SurajKarki.zip`** containing the
complete program files, the trained AI model, and a **Pack-and-Go** of the robot
station from the examination. The Pack-and-Go can only be made in the lab — a
missing one means the submission is not assessed.

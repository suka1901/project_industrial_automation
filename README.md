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

---

## Layout

```
INA700/
├─ README.md              this file: what it is and why it is built this way
├─ LAB.md                 what to do at the station, in order
├─ deploy.ps1 / .sh       build, copy to the Pi, verify, pre-flight it
├─ pi/run.sh             the Pi's commands, with its profile already chosen
├─ make_submission.py     builds FinalProject_SurajKarki.zip
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
[LAB.md](LAB.md).

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
| mapping | coordinate translation: pixels → work object X, Y, Rz, every frame |
| cycle | runs a picking cycle when the operator asks, retries, waits for the robot |
| connection | accepts the robot and holds the socket |
| main (Tk) | the GUI |

Frames pass through bounded queues holding two items, so a slow consumer drops
stale frames instead of growing a backlog. Shared state sits behind an `RLock`
and hands out immutable snapshots, so the GUI can never read a half-written
update.

### Orientation: fit the shape, over several segmentations

Two things decide whether an angle is right, and only one of them is the maths.

**Finding the object is the hard half.** One threshold cannot separate every
object from the paper: brightness finds a dark object, colour finds a coloured
one, and a WHITE object on white paper differs from the paper by three or four
grey levels — less than the sensor's noise — so only its border, which steps in
brightness and casts a hairline shadow, gives it away. Four candidate masks are
therefore tried per object (`otsu`, `chroma`, `gradient`, `edges`) and the one
that best matches an ideal square or star wins; the search stops early when a
mask plainly fits, so a clearly visible object still costs one segmentation.

**The fit is also the confidence.** Laying an ideal shape over the mask and
sweeping it round gives both the angle and an overlap score, and the overlap is
what the gates read. This replaced a measure that could not do the job: the
harmonic's own |Z| says how N-lobed an outline is, which a speckled mask of a
white square scored 0.4 on while being 25° wrong, so raising that gate filtered
almost nothing.

Measured over 184 labelled objects, each read at five known rotations
(`tools/orientation_bench.py`):

| gate | squares kept | squares p90 error | stars kept | stars p90 error |
|---|---|---|---|---|
| 0.70 | 85% | 11.0° | 93% | 0.39° |
| 0.75 | 76% | 3.4° | 91% | 0.23° |
| **0.80** | **68%** | **2.0°** | **89%** | **0.17°** |

0.80 is where a square stops being wrong by more than the jig's own play, and
it costs the stars nothing.

**The angle itself** comes from the same N-fold idea as before, but summed over
the mask's whole AREA rather than its outline — every pixel votes, weighted by
rᴺ so the rim decides — which is both more precise (0.14° against 0.60°) and
indifferent to a nick in the contour. It is kept only while it agrees with the
fitted angle to within `agreement_deg`; past that the fitted angle, the one the
confidence vouches for, is what is sent.

**Slot angles must be measured by the same estimator.** `rz = slot − object`
cancels every constant offset an estimator has, but only while both terms come
from the same one. `calibration/slot_angles.py` therefore builds its estimator
from `config.yaml` and records which one in `slot_angles.yaml`, and preflight
FAILS on a mismatch rather than letting every placement be out by the
difference.

### The original estimator, still selectable as `orientation.kind: harmonic`

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

**Nothing is ever refused on a doubtful angle.** Every detected object is
placed at the best angle that could be worked out for it. When no segmentation
fits well, the candidates' fit-weighted consensus is sent instead of a zero:
they fail for different reasons — a shadow edge, a clipped tip, a hole in the
mask — so what they agree on is more likely the object's angle than any one of
them, and far more likely than nothing. Being a few degrees out is a worse
placement; being unrotated is a wrong one.

The fit still travels with every reading, and the log names each placement that
rested on a guess, so a run can be judged afterwards. Nothing flashes on screen
during it: a banner the operator must read and act on mid-cycle was a decision
the system should be making for itself.

The angles are averaged as directions rather than as numbers, because they live
on a circle of 360/N degrees. On a square, 1° and 89° are two degrees apart, not
eighty-eight, and their arithmetic mean — 45° — is the one answer certainly
wrong.

### What has to be in the camera's view

The **A3 sheet** does — an object outside the picture cannot be picked, and the
ArUco marker printed at the sheet's centre is what maps pixels to millimetres.

The **jig does not**. The placing positions are taught on the robot, in `wobj2`,
and nothing at run time reads the jig. It is only needed while measuring the
slot angles, and those are *rotations*: the jig can be slid into view and back
out without changing them, as long as it is never turned on the way. Preflight
therefore judges the field of view against the sheet alone, and says how many
millimetres it is short when it does not fit.

The camera also keeps its area of interest in its own memory, so a crop left
behind in Pylon Viewer survives a power cycle, and a cropped image is
indistinguishable from a longer lens — the table simply looks closer. The full
sensor is therefore requested explicitly on every open (`camera.full_sensor`),
and a camera that will not widen says so in the log rather than passing for a
narrow lens.

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

## Why orientation is measured this way

Three shapes, three different symmetry periods: the square repeats every 90°,
the star every 72°, and the circle has no orientation at all. Any method has to
handle all three, and report honestly when there is nothing to report.

**The obvious approach does not work.** `cv2.minAreaRect` fits a rotated
bounding box, which is the first thing anyone reaches for. But a rectangle is
only defined **modulo 90°**, so it can only measure shapes whose symmetry period
divides 90. The square qualifies. The star does not — 72 does not divide 90, so
a five-pointed star has *five* equally minimal rectangles, 18° apart, and pixel
noise decides which one OpenCV returns. Measured over a full rotation, 1 px of
contour noise:

| Shape | `minAreaRect` median / worst | Harmonic median / worst |
|---|---|---|
| Square (period 90°) | 0.19° / 0.90° | 0.16° / 0.67° |
| Star (period 72°) | **17.83° / 35.97°** | 0.11° / 0.45° |

The star error is not noise that averaging could remove — it is a quantised jump
between five equally stable wrong answers. The box centre fails too: a five-fold
shape has no opposing vertex to balance each tip, so its bounding box is
lopsided and its centre sits **15.8 px — about 4.9 mm — off the true centre**,
against 0.5 px for the area centroid. The cup would miss a small star entirely.

**What is used instead.** The orientation is the phase of the N-th Fourier
coefficient of the object's radial profile; the magnitude of that coefficient is
the confidence.

Said without the jargon: a star's five tips are five equally correct answers
72° apart, so averaging them directly gives nothing — they cancel. Multiply
every angle by five first and those 72° gaps become 360° gaps, which is to say
the five answers land on top of each other. Average them there, divide the
result by five, and that is the orientation. `docs/orientation_method.svg` draws
it in four steps.

The confidence is not a separate check bolted on afterwards: if the shape really
has N-fold symmetry the terms agree after the multiplication and the sum is
long, and if it is a circle they cancel to nearly zero. The same arithmetic that
produces the angle says whether the angle means anything, which is where the
weak-angle warning comes from.

**The architectural consequence.** One estimator covers all three shapes with a
single parameter — N = 4 for the square, N = 5 for the star, and for the circle
the magnitude collapses and it correctly reports no orientation, with no special
case anywhere. A bounding-box approach would need per-shape branching. Adding a
hexagon later means writing the number 6 in a config file, not writing code:
open for extension, closed for modification, on something real.

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
| Multithreading, one job per thread | `infrastructure/runtime.py` — capture, inference, mapping, cycle, connection, plus the GUI |
| AI inference — shape, position, orientation | `YoloDetector` + `FittedOrientationEstimator` (`HarmonicOrientationEstimator` still selectable) |
| Coordinate translation pixel → work object | `MappingWorker` thread, `CoordinateService`, ArUco homography in `adapters/mapping/` |
| Server communication Pi → robot | `TcpServerTransport`, `MessageCodec` |
| GUI showing position and orientation | `adapters/gui/tk_view.py` — live camera view with the pick centre and the angle drawn on every object; the target's X/Y/Rz in the status bar |
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
| Retry up to two times | `max_attempts: 3` — first try plus two retries, `retry_delay_s` apart; none spent while the robot is disconnected |
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
| Architecture and code | Done — 295 tests green, the layering enforced by tests |
| Robot programs | Done — proven on hardware for the minimal exercise |
| Dataset, labelling, training | Done — 345 photos, 271 labelled, model exported for the Pi |
| Camera and marker calibration | Done on the PC; re-check the marker after any remount |
| Robot measurements | **Not started — the critical path** |
| Full cycle on the robot | **Never run with this code** |

### Measured at the station, not before

| Value | File | Step in LAB.md |
|---|---|---|
| `place_slot_angles_deg` | `pi/config/config.yaml` | 4 — and preflight FAILS until they are re-measured with the running estimator |
| `y_axis_flipped`, `angle_sign` | `pi/config/config.yaml` | 3.2, 3.3 |
| `verify_tolerance_mm` → 10–15 | `pi/config/config.yaml` | before the first real cycle |
| `PICK_SURFACE_Z_MM` | `robot/StationData.mod` | 3.1, on a scrap object |
| the Pi's address in `ServerCommuncatio.sys` | the controller | before anything connects |

### How a change reaches the Pi

Everything is fixed on the PC — the camera plugs in here, every number is
edited here — and `deploy.ps1` (or `deploy.sh`) builds, copies, unpacks and then
checks that the Pi's `config.yaml` hashes the same as this one before running
preflight there. Nothing is edited on the Pi, so there is never a second copy of
the truth. Nothing taught on the robot travels in the bundle at all: it lives in
the controller and reaches the submission through the Pack-and-Go.

### Known risks

**The model was trained at a dimmer exposure than the camera now runs.** The
sheet read 144–160 in the dataset and 180–210 now. Watch the first detections;
if recall drops, a round of photos at the current exposure is the fix.

**Square has the fewest photos** at 38, so its recall degrades first — and white
squares on white paper are also where the orientation fit is weakest.

**The sheet and the jig do not both fit in the frame.** They do not have to: the
jig is only needed while measuring the slot angles, and it can be slid in and
out as long as it is never turned.

---

## Hand-in

A single ZIP named exactly **`FinalProject_SurajKarki.zip`** containing the
complete program files, the trained AI model, and a **Pack-and-Go** of the robot
station from the examination. The Pack-and-Go can only be made in the lab — a
missing one means the submission is not assessed.

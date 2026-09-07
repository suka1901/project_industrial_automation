# INA700 Final Project — AI-based Pick and Place

Vision system on a Raspberry Pi 4 with a Basler camera that detects
shapes, measures their position and orientation, converts pixels into the robot's
work object coordinates and drives an ABB robot to pick each object and place it in
its fixed slot.

**Target grade: A** — Grade Level III functionality plus an object-oriented
architecture following SOLID.

---

## Where things are

```
INA700/
├─ ARCHITECTURE.md       the design, the reasoning, the build order  <- read this first
├─ STATUS.md             what is done, what is blocked, what is still a placeholder
├─ LAB_PLAN.md          which order to do the lab work in, and the gate for each session
├─ PROCEDURE.md          bench steps: calibrate, shoot, label, train
├─ CALIBRATION.md        why each calibration gate exists
├─ SUBMISSION.md         hand-in checklist
├─ README.md             this file
├─ pi/                   the Raspberry Pi application (Python)
├─ robot/                RAPID modules for the ABB controller
├─ model/                dataset and trained weights
└─ docs/                 calibration notes, protocol spec
```

## Running it right now, with no hardware

```bash
cd pi
python -m unittest discover -s tests -v     # 54 unit tests
python smoke_test.py                        # full pipeline, mock adapters, headless
python main.py                              # the same, with the GUI
```

The default profile in `config/config.yaml` uses a synthetic camera, a mock detector
and a loopback robot, so the whole system runs on any laptop with Python and PyYAML.
Everything the lab adds — the Basler camera, the trained model, the real robot — is
a config change, not a code change.

## Switching to the lab

In `config/config.yaml`:

```yaml
profile: lab
camera:    { kind: basler }
detector:  { kind: yolo, model_path: ../model/best_ncnn_model }
colour:    { kind: hsv }
coordinates: { mapper: aruco }
robot:     { transport: tcp }
```

## Configuring your three shapes

When the instructor assigns them, edit one list:

```yaml
shapes: [CIRCLE, SQUARE, STAR]
```

and the matching `detector.class_map`. No shape name is hard-coded in any logic, so
nothing else changes.

## Layout of `pi/`

| Folder | Contains | Depends on |
|---|---|---|
| `domain/` | value objects, shape symmetry, angle maths | nothing (pure Python) |
| `ports/` | the abstract interfaces | `domain` |
| `application/` | vision pipeline, coordinates, cycle control, selectors | `domain`, `ports` |
| `adapters/` | `Camera` (Basler), `ArUco`, YOLO, OpenCV, sockets, Tkinter | `domain`, `ports` |
| `infrastructure/` | threads, logging, the composition root | everything |

Dependencies point inwards only. `application/` never imports `adapters/` — concrete
classes are chosen in `infrastructure/container.py` from the config file.

## Threads

| Thread | Responsibility |
|---|---|
| `capture` | grab frames from the camera, keep only the newest |
| `inference` | AI model + orientation + colour, and time it |
| `connection` | bring the robot link up, track its status |
| `cycle` | run one pick-and-place cycle per operator request (yellow button starts the motion) |
| main | Tkinter GUI (Tk must own the main thread) |

They communicate only through bounded queues and one lock-guarded `SharedState`
that hands the GUI immutable snapshots.

## Pi to robot protocol

A RAPID `string` holds **80 characters maximum**, so the protocol is short and
fixed-field. A unit test proves every shape/colour combination stays under the limit.

```
server -> robot   move circle 123.45 -45.30 -12.5#
server -> robot   quit#
robot  -> server  DONE: circle#
robot  -> server  ERROR: unknown shape 'blob'#
```

Words separated by spaces, `#` ends a message. Colour is **not** sent — the operator
types `circle red`, but matching the colour is the server's job.

Shape, X and Y are required. The objects are scattered on the board at random, so there
is no taught position to fall back on and a command without coordinates is refused. The
robot also refuses a position outside the A3 sheet (`PICK_AREA_*` in
`StationData.mod`) — measure your board and set those before running.

The PC/Pi is the **server** on port `5000` — the working setup binds
`192.168.125.201`. The robot (`192.168.125.3`, netmask `255.255.255.0`) dials out
to it via `RobotAsClientConnect` in the course's `ServerCommuncatio.sys`.

`ServerCommuncatio.sys` line 52 has been pointed at `192.168.125.201` — the only change
made to that file, an address and not a line of logic. The original is preserved at
`docs/ServerCommuncatio.sys.original`; `diff` the two to see it is a two-byte edit.

**This line changes again when vision moves to the Raspberry Pi.** Re-upload the module
to the controller after editing it, and re-check with `ping` before the run.

## Calibration — ArUco marker

A 5x5 ArUco marker stays fixed on the table. Its four corners are detected every
frame and give scale, origin and rotation together, so a nudged camera corrects
itself instead of quietly picking in the wrong place.

```bash
python calibration/aruco_check.py --length 100 --camera basler
```

Confirms the marker is detected, shows its ID and the px/mm ratio, and reports the
**jitter** over the last 60 frames. Above about 0.02 px/mm, fix focus and lighting
before trusting any coordinate.

Set these once in `config.yaml` under `aruco:`. The supplied rubber marker is 100 mm,
so only the position needs measuring — jog the robot to the marker centre, read X and
Y in `wobj1`, and note its rotation:

```yaml
aruco:
  marker_length_mm: 100.0
  marker_centre_xy_mm: [<x>, <y>]
  marker_angle_deg: 0.0
```

Mount the marker **level with the top of the objects**. The homography maps to the
plane the marker sits in, and the camera sees the objects' top faces — calibrating on
the board plane leaves a systematic outward error that grows toward the corners.

`cv2.aruco` needs **opencv-contrib-python**. Plain `opencv-python` does not include
it, despite what the course README's install line suggests.

A manual 4-point fallback (`calibration/calibrate_homography.py`) is also there if
the marker is ever unavailable.

## Before handing in

Submit a single ZIP named exactly `FinalProject_StudentName.zip` containing the
program files, the trained model and a Pack-and-Go of the robot station.
**A submission that does not follow that pattern is failed with no resubmission.**

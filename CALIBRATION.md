# Calibration — the order to do it in

Everything downstream inherits the errors made here. A model trained on badly
lit photos can be retrained in an hour; a camera mapping that is 5 mm out will
have you chasing phantom bugs in the robot program for a day. So this comes first,
and each stage has a **gate** — something you can point at and say "that is
correct" — before the next one starts.

**Read this alongside `ARCHITECTURE.md` §7 (the ArUco design) and §8 (the vacuum
rotation rule).**

---

## Stage 0 — Environment · 15 min

| | |
|---|---|
| **Do** | Confirm the toolchain works before touching hardware. |
| **Gate** | `python tools/preflight.py` reports **All checks passed**, and Pylon Viewer shows a live image. |
| **Fails when** | `cv2.aruco` is missing → you have plain `opencv-python`. Uninstall every OpenCV package and install only `opencv-contrib-python`. |

```bash
cd pi
python tools/preflight.py                 # packages, camera, config
python tools/preflight.py --length 100    # and the marker, once it is mounted
```

It checks the packages, enumerates the Basler camera, grabs a frame, reads the
config, and — with `--length` — measures the marker's stability. Run it at the
start of every session, including the examination.

Do not skip the Pylon Viewer check. If the vendor's own tool cannot see the
camera, no amount of Python will.

---

## Stage 1 — Mount and aim the camera · 30 min

| | |
|---|---|
| **Do** | Fix the camera rigidly above the picking area. Frame it so the **whole picking area and the marker** are visible with room to spare. Focus on the table surface. Set exposure and gain manually. |
| **Gate** | Objects at all four corners of the picking area are in frame and in focus. Nudging the bench does not move the image. |
| **Fails when** | Auto-exposure is left on — the colours then shift between your dataset and exam day, and the colour rule (R8) starts guessing. Fix exposure in `config.yaml` and leave it. |

The camera never moves again after this. If it does, live ArUco calibration will
absorb it — but your training photos will not match.

---

## Stage 2 — Mount the marker · 10 min

The marker is the supplied 100 mm rubber DICT_5X5_100, ID 0. Its size is known,
so there is nothing to measure — but **where** and **at what height** it sits
both matter.

| | |
|---|---|
| **Do** | Fix it flat and permanently, well inside the frame where lens distortion is smallest, and **clear of where objects land** so nothing can cover it. Shim it so its face is level with the **top surface of the objects** (see below). |
| **Gate** | Flat, square to the board, fully visible with objects on the board, and at object-top height. |
| **Fails when** | Mounted at the frame edge, lifting at a corner, or somewhere an object or the arm crosses it mid-cycle. |

**Why the height matters.** The homography maps the image onto *the plane the
marker lies in*. The camera sees the objects' top faces, which sit one object
thickness above the board. Calibrate on the board plane and every object is
reported displaced outward from the image centre by roughly

```
error  ≈  r · h / H          r = distance from image centre
                             h = object thickness
                             H = camera height
```

For 10 mm objects, a camera 800 mm up and an object 150 mm off centre that is
about 2 mm — the size of your whole mapping tolerance, systematic rather than
random, and worst at the corners. Since every object is the same thickness,
shimming the marker to object-top height removes it by construction.

---

## Stage 3 — Verify detection and stability · 20 min

```bash
cd pi
python calibration/aruco_check.py --length 100 --camera basler
```

| | |
|---|---|
| **Do** | Watch the live overlay. Check the ID is 0. Watch the **jitter** figure over a minute. |
| **Gate** | Marker detected in every frame; **jitter below 0.02 px/mm**. |
| **Fails when** | Glare across the marker, soft focus, or too little light. Fix it here. Nothing downstream can compensate for an unstable detection. |

This is the single most important gate in the list. Do not move on while the
number is jumping around.

---

## Stage 4 — Locate the marker in `wobj1` · 20 min · needs the robot

| | |
|---|---|
| **Do** | Keep the taught `wobj1`. Jog the tool tip to the **marker centre**, read work-object X and Y off the pendant, and put them in `marker_centre_xy_mm`. If the marker is not square to `wobj1`'s X axis, measure that angle too. |
| **Gate** | The two numbers written down, and the mapping check in Stage 6 agreeing within 1–2 mm. |
| **Why not put the origin on the marker?** | It is allowed — `marker_centre_xy_mm` would then be `[0, 0]`. But the marker has to sit clear of the picking area, and moving `wobj1` shifts everything expressed in it: `Papproach` needs re-teaching, `PICK_SURFACE_Z_MM` changes, and the four `PICK_AREA_*` bounds change. `wobj1` is already taught and proven on hardware, so measuring one offset is the cheaper trade. |
| **Note** | An error in the measured offset appears as a *uniform* shift, which Stage 6 catches — then correct it by editing the same two numbers. |

---

## Stage 5 — Fill in the config · 5 min

In `pi/config/config.yaml`:

```yaml
aruco:
  marker_length_mm: 100.0
  marker_centre_xy_mm: [<x>, <y>]     # the marker centre, measured in wobj1
  marker_id: 0
coordinates:
  mapper: aruco
camera:
  kind: basler
```

| **Gate** | `python smoke_test.py` still runs and prints an inference time. |

---

## Stage 6 — Verify the mapping · 20 min · needs the robot

| | |
|---|---|
| **Do** | Put an object at a spot you can jog to. Read the X/Y the GUI reports; jog the robot there and compare. Repeat at three well-separated spots, including near a corner. |
| **Gate** | Agreement within **~1–2 mm everywhere**, corners included. |
| **Fails when** | Centre is fine but corners are off → lens distortion; move the marker more central, or add the intrinsic calibration step. Everything off by a constant → the marker length is wrong (back to Stage 2). Everything mirrored → Stage 7. |

---

## Stage 7 — Resolve the two sign flags · 20 min · needs the robot

The two settings that are silent when wrong and fatal in the demonstration.

| | |
|---|---|
| **Do** | **`y_axis_flipped`** — place one object clearly off-centre in +Y. If the reported Y has the wrong sign, flip the flag. **`angle_sign`** — place a square deliberately at about 45°. Rotating it clockwise should move the reported angle consistently one way; if the correction the robot applies makes the fit worse rather than better, flip `angle_sign`. |
| **Gate** | One test pick of a square placed at 45° seats cleanly in its slot. |
| **Why it earns marks** | This is requirement R11 — 5 of 6 placed with correct orientation. Both flags are one character each and cost you the whole placement score if either is wrong. |

---

## Stage 8 — Teach `wobjPlace` and the slot offsets · 30 min · needs the robot

| | |
|---|---|
| **Do** | Teach the placing work object at the jig, and check the five slot targets `p10`–`p60` still land correctly in it. Then measure each shape's arrival angle: seat the object in its slot, lift it straight out **without turning it**, put it on the picking board, and read it with `python calibration/slot_angles.py --camera basler`. |
| **Gate** | A hand-sent `move star <x> <y> <rz>` seats the star cleanly in its slot. |
| **Why here** | The moment this passes, you have a **complete working Step 1** again — your fallback if anything on the vision side fails during the examination. |

---

## Stage 9 — Capture the dataset · 2–3 hours

```bash
cd pi
python tools/capture_gui.py
```

Pick the shape, aim, press **Capture** (or space). Full-resolution frames land in
`model/dataset/raw/<shape>/`, numbered and resuming across sessions.

| | |
|---|---|
| **Target** | 200–300 photos. Vary position, rotation, spacing, and clustering. The tool shows a live count per shape. |
| **Critical** | Include the **two shapes you were NOT assigned**, in shot, and leave them **unlabelled** at labelling time. They become hard negatives — this is what makes the model genuinely ignore them rather than guess. |
| **Gate** | Roughly balanced counts (the tool shows them live), marker visible in the great majority of frames, nothing blurred. |
| **Fails when** | Every photo is shot in one lighting condition, at one time of day. Shoot in the lab, at lab light, across a session or two. |

---

## The dependency map

```
Stage 0  environment
   │
Stage 1  camera mounted and aimed ─────────────┐
   │                                           │
Stage 2  marker mounted and shimmed            │
   │                                           │
Stage 3  detection stable  ◀── THE KEY GATE    │
   │                                           │
   ├──────────────┐                            │
   ▼              ▼                            ▼
Stage 4        Stage 5                     Stage 9
wobjPick       config                      dataset capture
   │              │                            │
   └──────┬───────┘                            │
          ▼                                    │
      Stage 6  mapping verified                │
          │                                    │
          ▼                                    │
      Stage 7  sign flags resolved             │
          │                                    │
          ▼                                    ▼
      Stage 8  wobjPlace + Step 1 working   training
```

Stage 9 only needs Stages 1–3, so **dataset capture can run in parallel** with
the robot work — and it is the long pole. Shoot photos whenever you have the
camera but not the robot.

---

## What to do first, right now

1. **Stage 0** — five commands, no hardware.
2. **Stage 2** — mount the marker, shimmed to object-top height.
3. **Stage 1 + 3** — mount, aim, and run `aruco_check.py` until the jitter is flat.

Only once Stage 3's gate is green does the robot become worth booking.

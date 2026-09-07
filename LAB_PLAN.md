# Lab plan

`PROCEDURE.md` says how each step works. This says which order to do them in,
and what has to be true before moving on.

Two months and open lab access means there is no reason to rush a step or carry
an unverified number forward. Every session below ends on a **gate** — a
measurable condition. If the gate does not pass, that session is not finished,
and the next one will only build on sand.

Author: Suraj Karki
Course: INA700 - AI-based pick and place

---

## Session 1 — Foundation

Nothing downstream means anything until this passes. Bench and Pi only; the
robot is needed at the end.

| Step | Reference | Why here |
|---|---|---|
| Remount the marker | A1 | The rubber 100 mm one, shimmed to object-top height, **clear of the A3 sheet**. The paper printout currently sits where objects land |
| Re-aim and focus | A2 | After moving the marker, focus on an object's top face |
| Fix exposure | A3 | Target sheet 180–210. It has been reading 78 |
| Detection and stability | A5 | The gate below |
| Pi benchmark | F1 | Two minutes, no camera needed, answers the 3 s question |

**Gate:** `aruco_check.py` shows ID 0 in every frame with **jitter below 0.02
px/mm**, held for a full minute, and `benchmark.py` reports PASS or TIGHT.

> Do not book robot time before this passes. Every measurement in Session 2
> inherits the marker's stability.

---

## Session 2 — The work object

Robot needed. This is where the six placeholders start becoming real numbers.

| Step | Reference | Writes |
|---|---|---|
| Marker centre in `wobj1` | A6 | `marker_centre_xy_mm`, `marker_angle_deg` |
| Verify the mapping | A7 | nothing — it confirms A6 |
| A3 sheet corner | A11 | `SHEET_ORIGIN_X`, `SHEET_ORIGIN_Y` |
| Pick height | A11 | `PICK_SURFACE_Z_MM` |

**Gate:** A7 agrees within **1–2 mm at three well-separated spots, including a
corner**. A corner error growing outward means the marker is not at object-top
height — go back to A1 rather than accepting it.

---

## Session 3 — Signs and angles

Robot needed. Short if Session 2 was clean.

| Step | Reference | Writes |
|---|---|---|
| Y direction | A8 | `y_axis_flipped` |
| Rotation direction | A9 | `angle_sign` |
| Teach `wobj2`, measure slots | A10 | `place_slot_angles_deg` |

**Gate:** a square deliberately placed at 45° seats cleanly in its slot.

---

## Session 4 — Full rehearsal

Everything connected, on the Pi, exactly as at the exam.

- `robot.transport: tcp`, `verify_tolerance_mm: 10–15`
- Six objects on the sheet, including hexagons and triangles
- Two complete cycles, all three shapes each, chosen by operator input
- Confirm the inference time printed each cycle stays under 3 s
- Confirm a hexagon or triangle is **never** picked

**Gate:** two cycles, six objects, at least five placed with the correct
orientation — the Grade Level III criterion, met without intervention.

---

## After the gates pass

With time left over, in order of value:

1. **Re-shoot the underexposed photos.** Roughly half the dataset has the sheet
   at 67–86 where it should read 180–210. Retrain and compare `mAP50-95`.
2. **Re-run `tools/offline_check.py`** after any retrain — it scores what the
   robot is actually told, not just the detector.
3. **Pack-and-Go** from the station, for the ZIP.
4. **Rehearse the presentation.** Know why the angle comes from a harmonic
   rather than `minAreaRect`, and why the Pi and laptop profiles differ by two
   lines.

---

## What to record every session

Paste these back and they can be checked against expectations:

- `preflight.py` output in full
- `aruco_check.py` px/mm and jitter
- `benchmark.py` result
- Every number written into `config.yaml` or `StationData.mod`, and where it came from
- Anything that surprised you

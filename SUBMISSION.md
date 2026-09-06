# Submission checklist

The ZIP must be named exactly **`FinalProject_SurajKarki.zip`**.
A submission that does not follow the pattern is failed with no resubmission.

## Include

- [ ] `pi/` — the Raspberry Pi application (without `__pycache__` and `logs/`)
- [ ] `robot/` — `MainModule.mod` and `StationData.mod`
- [ ] `ServerCommuncatio.sys` — the course file, one line changed (address only)
- [ ] `model/best.pt` and the NCNN export — **not yet trained**
- [ ] Pack-and-Go of the robot station from the examination — **not yet produced**
- [ ] `README.md`, `ARCHITECTURE.md`, `CALIBRATION.md`

## Leave out

- `__pycache__/`, `pi/logs/`, `.vscode/`
- `docs/course-material/` — the instructor's own PDFs
- `docs/superseded/` — optional; it shows the working history but is not the solution

## Before zipping

```bash
cd pi
python tools/preflight.py --length <measured mm>
python -m unittest discover -s tests
```

## Still open

| Item | Where |
|---|---|
| Label the 280 photos (PROCEDURE.md Part C) | Label Studio |
| Train and export the model (PROCEDURE.md Part D) | `model/train_yolo.ipynb` |
| `PICK_SURFACE_Z_MM` — teach one pick point | `robot/StationData.mod` |
| `SHEET_ORIGIN_X / Y` — measure the A3 sheet corner | `robot/StationData.mod` |
| `place_slot_angles_deg` — run `calibration/slot_angles.py` | `pi/config/config.yaml` |
| `marker_centre_xy_mm` — jog to the marker centre, read X/Y in wobj1 | `pi/config/config.yaml` |
| Switch the profile to camera/yolo/aruco/tcp | `pi/config/config.yaml` |
| `verify_tolerance_mm: 10-15` for the lab | `pi/config/config.yaml` |

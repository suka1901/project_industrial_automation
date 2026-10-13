"""Builds FinalProject_SurajKarki.zip - the one file that gets handed in.

    python make_submission.py --pack-and-go path\\to\\Station.pgz

The course is blunt about this: a submission that does not follow the pattern
is not assessed and there is no resubmission. So the three things it asks for
are checked rather than assumed - the complete program files, the trained AI
model, and a Pack-and-Go of the station from the examination - and the build
refuses rather than producing a zip that is quietly missing one of them.

The dataset stays out. It is 2.1 GB of camera frames, it is not a program
file, and the model is what the photos were for.

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent
STUDENT = "SurajKarki"
ZIP_NAME = f"FinalProject_{STUDENT}.zip"

# Where a Pack-and-Go is looked for when one is not given on the command line.
PACK_AND_GO_SUFFIXES = (".pgz", ".zip")
PACK_AND_GO_FOLDER = "pack-and-go"

# Everything that is a program file, a document or the model.
INCLUDE = (
    "pi",                       # the vision system, its tests and its tools
    "robot",                    # the two RAPID modules
    "docs/uml",                 # the architecture, as diagrams
    "docs/marker_sheet_a3.pdf",  # needed to reprint the calibration sheet
    "model/best.pt",            # the trained model
    "model/best_ncnn_model",    # and its Pi export
    "model/train_yolo.ipynb",   # how it was trained
    "model/label_config.xml",
    "ServerCommuncatio.sys",    # the course's module, with its address set
    "README.md",
    "LAB.md",
    "rebundle.sh",
    "rebundle.ps1",
    "make_submission.py",
)

# Never shipped: build leftovers, run-time output, and anything the camera made.
EXCLUDED_NAMES = {"__pycache__", ".pytest_cache", ".git", ".venv", "venv",
                  "logs", "dataset", "runs"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".log", ".tar.gz", ".tgz"}


def is_wanted(path: Path) -> bool:
    """Is this file part of the submission?"""
    if any(part in EXCLUDED_NAMES for part in path.parts):
        return False
    if path.suffix in EXCLUDED_SUFFIXES or path.name.endswith(".tar.gz"):
        return False
    return path.is_file()


def wanted_files(root: Path = ROOT, include: Iterable[str] = INCLUDE) -> List[Path]:
    """Every file to ship, as paths relative to the project root."""
    found: List[Path] = []
    for entry in include:
        target = root / entry
        if target.is_file():
            if is_wanted(target):
                found.append(target.relative_to(root))
        elif target.is_dir():
            found.extend(path.relative_to(root)
                         for path in sorted(target.rglob("*")) if is_wanted(path))
    return sorted(set(found))


def find_pack_and_go(given: Optional[str], root: Path = ROOT) -> Optional[Path]:
    """The station's Pack-and-Go, given explicitly or left in pack-and-go/."""
    if given:
        path = Path(given).expanduser()
        return path if path.is_file() else None

    folder = root / PACK_AND_GO_FOLDER
    if not folder.is_dir():
        return None
    candidates = [path for path in sorted(folder.iterdir())
                  if path.is_file() and path.suffix.lower() in PACK_AND_GO_SUFFIXES]
    # The newest, so re-exporting during the exam and running this again does
    # the obvious thing rather than shipping the morning's station.
    return max(candidates, key=lambda path: path.stat().st_mtime) if candidates else None


def missing_requirements(files: List[Path],
                         pack_and_go: Optional[Path]) -> List[str]:
    """What the course asks for and this build does not have."""
    missing = []
    if not any(path.parts[:1] == ("pi",) for path in files):
        missing.append("the program files (pi/)")
    if not any(path.parts[:1] == ("robot",) for path in files):
        missing.append("the robot program (robot/)")
    if not any("best" in path.name for path in files):
        missing.append("the trained model (model/best.pt and best_ncnn_model)")
    if pack_and_go is None:
        missing.append("a Pack-and-Go of the station (--pack-and-go, or drop "
                       f"it in {PACK_AND_GO_FOLDER}/)")
    return missing


def tests_pass(root: Path = ROOT) -> bool:
    """Run the unit tests. A zip built from a failing tree looks identical."""
    print("Running the tests...")
    result = subprocess.run([sys.executable, "-m", "pytest", "-q"],
                            cwd=str(root / "pi"))
    return result.returncode == 0


def build(files: List[Path], pack_and_go: Optional[Path],
          out: Path, root: Path = ROOT) -> Tuple[int, int]:
    """Write the zip. Everything sits under one folder, as a marker expects."""
    written = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for relative in files:
            archive.write(root / relative, f"{out.stem}/{relative.as_posix()}")
            written += 1
        if pack_and_go is not None:
            archive.write(pack_and_go,
                          f"{out.stem}/{PACK_AND_GO_FOLDER}/{pack_and_go.name}")
            written += 1
    return written, out.stat().st_size


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--pack-and-go", default=None,
                        help="the station's Pack-and-Go file; without it, the "
                             f"newest one in {PACK_AND_GO_FOLDER}/ is used")
    parser.add_argument("--out", default=str(ROOT / ZIP_NAME))
    parser.add_argument("--skip-tests", action="store_true",
                        help="only for a dry run before the station - the "
                             "submitted zip should never be built this way")
    parser.add_argument("--allow-missing", action="store_true",
                        help="build anyway, for a rehearsal before the exam. "
                             "The result is NOT a valid submission")
    args = parser.parse_args()

    files = wanted_files()
    pack_and_go = find_pack_and_go(args.pack_and_go)
    missing = missing_requirements(files, pack_and_go)

    if missing and not args.allow_missing:
        print("\nNot built. The course requires a single zip containing the "
              "complete program files, the trained model and a Pack-and-Go of "
              "the station - and a submission that does not follow the pattern "
              "is not assessed.\n\nThis build is missing:")
        for item in missing:
            print(f"  - {item}")
        print("\nExport the Pack-and-Go in RobotStudio at the end of the "
              "examination, then run this again.")
        return 1

    if not args.skip_tests and not tests_pass():
        print("\nNot built: the tests failed. Fix them, or pass --skip-tests "
              "knowingly.")
        return 1

    out = Path(args.out)
    if out.name != ZIP_NAME:
        print(f"\nRefusing to write {out.name}: the course requires exactly "
              f"{ZIP_NAME}, and a wrong name is reported as failed with no "
              f"resubmission.")
        return 1

    count, size = build(files, pack_and_go, out)
    print(f"\n  {out.name}   {size / 1e6:.1f} MB   {count} files")
    print(f"  program files : pi/, robot/, {len(files)} in total")
    print(f"  trained model : model/best.pt and model/best_ncnn_model")
    print(f"  pack and go   : "
          f"{pack_and_go.name if pack_and_go else 'MISSING - not a valid submission'}")
    if missing:
        print("\n  built with --allow-missing: this is a rehearsal, not a "
              "submission.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

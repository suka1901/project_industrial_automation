"""Headless end-to-end run against the mock adapters.

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""

from __future__ import annotations

import argparse
import queue
import sys
import threading
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))


from domain.models import PickRequest
from adapters.comms.message_codec import MessageCodec
from adapters.comms.robot_commander import RobotCommander
from application.cycle_controller import CycleController
from application.shared_state import SharedState
from infrastructure.container import Container
from infrastructure.config_loader import load_config  # noqa: E402
from infrastructure.logging_setup import configure_logging
from infrastructure.runtime import (
    CaptureWorker,
    ConnectionWorker,
    InferenceWorker,
    LatestResultHolder,
    ThreadSupervisor,
)


WARM_UP_TIMEOUT_S = 120.0   # a cold model on the Pi is slow to load


def main() -> int:
    parser = argparse.ArgumentParser(description="Headless end-to-end run, no hardware")
    parser.add_argument("--config", default="config/config.yaml",
                        help="profile to run; config/profiles/offline.yaml uses "
                             "the trained model against saved photos")
    args = parser.parse_args()

    config = load_config(BASE_DIR / args.config)
    print(f"profile: {args.config}")
    configure_logging(level="INFO", log_file=None)

    container = Container(config, BASE_DIR)
    state = SharedState()
    transport = container.build_transport()

    shutdown = threading.Event()
    frames: queue.Queue = queue.Queue(maxsize=2)
    results: queue.Queue = queue.Queue(maxsize=2)

    supervisor = ThreadSupervisor(shutdown)
    supervisor.add(CaptureWorker(shutdown, container.build_frame_source(), frames))
    supervisor.add(InferenceWorker(shutdown, container.build_vision_pipeline(),
                                   frames, results, state))
    supervisor.add(ConnectionWorker(shutdown, transport, state, MessageCodec().encode_quit()))
    supervisor.start_all()

    controller = CycleController(
        get_inference=LatestResultHolder(results),
        coordinates=container.build_coordinate_service(),
        selector=container.build_selector(),
        commander=RobotCommander(transport, MessageCodec(), reply_timeout_s=1.0),
        state=state,
        max_attempts=config["robot"].get("max_attempts", 3),
        verify_tolerance_mm=container.verify_tolerance_mm,
    )

    # Wait for the first inference rather than sleeping a fixed time: loading
    # and warming a real model takes seconds, and far longer on the Pi.
    deadline = time.monotonic() + WARM_UP_TIMEOUT_S
    while (time.monotonic() < deadline
           and state.snapshot().inference_ms <= 0.0
           and not shutdown.is_set()):          # a dead worker means never
        time.sleep(0.2)

    if shutdown.is_set():
        print("\nA worker thread died - see the traceback above. "
              "Wrong profile for this machine? config/profiles/offline.yaml "
              "runs from saved photos and needs no camera.")
        supervisor.stop_all()
        return 1
    if state.snapshot().inference_ms <= 0.0:
        print(f"NO inference within {WARM_UP_TIMEOUT_S:.0f} s - is the model loading?")

    print("\n--- running two cycles ---")
    for _ in range(2):
        report = controller.run_cycle(PickRequest())
        target = report.target
        print(f"cycle {report.cycle_index}: {report.outcome.value} "
              f"in {report.attempts} attempt(s)"
              + (f" -> {target.shape.value} {target.colour.value} "
                 f"x={target.pose.x:.1f} y={target.pose.y:.1f} "
                 f"rz={target.pose.rz:.1f}" if target else "")
              # Without the reason a failure is a mystery. Replaying saved
              # photos, the usual one is landing on a hard negative, which is
              # the model behaving correctly rather than a fault.
              + (f"   [{report.message}]" if not target and report.message else ""))

    print("\n--- messages that went to the robot ---")
    for message in getattr(transport, "sent", []):
        print(f"  {message}   ({len(message)} chars, RAPID limit 80)")

    snapshot = state.snapshot()
    print(f"\ndetections on the table : {len(snapshot.detections)}")
    print(f"last inference time     : {snapshot.inference_ms:.1f} ms")

    supervisor.stop_all()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

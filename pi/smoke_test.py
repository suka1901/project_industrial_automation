"""Headless end-to-end run against the mock adapters.

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""

from __future__ import annotations

import queue
import sys
import threading
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

import yaml

from domain.models import PickRequest
from adapters.comms.message_codec import MessageCodec
from adapters.comms.robot_commander import RobotCommander
from application.cycle_controller import CycleController
from application.shared_state import SharedState
from infrastructure.container import Container
from infrastructure.logging_setup import configure_logging
from infrastructure.runtime import (
    CaptureWorker,
    ConnectionWorker,
    InferenceWorker,
    LatestResultHolder,
    ThreadSupervisor,
)


def main() -> int:
    config = yaml.safe_load((BASE_DIR / "config/config.yaml").read_text(encoding="utf-8"))
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

    time.sleep(1.0)  # let the first frames flow through

    print("\n--- running two cycles ---")
    for _ in range(2):
        report = controller.run_cycle(PickRequest())
        target = report.target
        print(f"cycle {report.cycle_index}: {report.outcome.value} "
              f"in {report.attempts} attempt(s)"
              + (f" -> {target.shape.value} {target.colour.value} "
                 f"x={target.pose.x:.1f} y={target.pose.y:.1f} "
                 f"rz={target.pose.rz:.1f}" if target else ""))

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

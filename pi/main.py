"""Application entry point: builds the system and starts the threads.

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""

from __future__ import annotations

import argparse
import logging
import queue
import sys
import threading
from pathlib import Path

# Make the package importable when run directly from the pi/ folder.
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

import yaml  # noqa: E402

from adapters.comms.message_codec import MessageCodec  # noqa: E402
from adapters.comms.robot_commander import RobotCommander  # noqa: E402
from adapters.gui.tk_view import TkView  # noqa: E402
from application.cycle_controller import CycleController  # noqa: E402
from application.shared_state import SharedState  # noqa: E402
from infrastructure.container import Container  # noqa: E402
from infrastructure.config_loader import load_config
from infrastructure.logging_setup import configure_logging  # noqa: E402
from infrastructure.runtime import (  # noqa: E402
    CaptureWorker,
    ConnectionWorker,
    CycleWorker,
    InferenceWorker,
    LatestResultHolder,
    ThreadSupervisor,
)

log = logging.getLogger("main")


def main() -> int:
    parser = argparse.ArgumentParser(description="INA700 AI pick and place")
    parser.add_argument("--config", default="config/config.yaml",
                        help="path to the YAML configuration file")
    args = parser.parse_args()

    config = load_config(BASE_DIR / args.config)
    configure_logging(
        level=config.get("logging", {}).get("level", "INFO"),
        log_file=str(BASE_DIR / config["logging"]["file"])
        if config.get("logging", {}).get("file") else None,
    )

    log.info("Starting INA700 with profile '%s', shapes %s",
             config.get("profile"), config["shapes"])

    # --- build the object graph (composition root) -------------------------
    container = Container(config, BASE_DIR)
    state = SharedState()

    frame_source = container.build_frame_source()
    pipeline = container.build_vision_pipeline()
    coordinates = container.build_coordinate_service()
    selector = container.build_selector()
    transport = container.build_transport()

    commander = RobotCommander(
        transport=transport,
        codec=MessageCodec(),
        reply_timeout_s=config["robot"].get("reply_timeout_s", 60.0),
    )

    # --- queues connecting the threads -------------------------------------
    shutdown = threading.Event()
    frames: queue.Queue = queue.Queue(maxsize=2)
    results: queue.Queue = queue.Queue(maxsize=2)
    requests: queue.Queue = queue.Queue(maxsize=8)

    latest_result = LatestResultHolder(results)

    controller = CycleController(
        get_inference=latest_result,
        coordinates=coordinates,
        selector=selector,
        commander=commander,
        state=state,
        max_attempts=config["robot"].get("max_attempts", 3),
        verify_tolerance_mm=container.verify_tolerance_mm,
    )

    # --- start the worker threads ------------------------------------------
    supervisor = ThreadSupervisor(shutdown)
    supervisor.add(CaptureWorker(shutdown, frame_source, frames))
    supervisor.add(InferenceWorker(shutdown, pipeline, frames, results, state))
    supervisor.add(ConnectionWorker(shutdown, transport, state, MessageCodec().encode_quit()))
    supervisor.add(CycleWorker(shutdown, controller, requests, state))
    supervisor.start_all()

    # --- the view owns the main thread -------------------------------------
    # console needs no display, which is what makes an SSH session on the Pi
    # work; tk is the richer alternative when there is a monitor.
    view_kind = str(config.get("gui", {}).get("kind", "tk")).lower()
    view_class = TkView
    if view_kind == "console":
        from adapters.gui.console_view import ConsoleView
        view_class = ConsoleView

    view = view_class(
        allowed_shapes=container.shapes,
        on_cycle_requested=requests.put,     # queue is the thread-safe hand-off
        on_close=shutdown.set,
        snapshot_provider=state.snapshot,
        refresh_ms=config.get("gui", {}).get("refresh_ms", 100),
        budget_ms=config["vision"].get("inference_budget_ms", 3000.0),
        place_confidence_gate=config.get("orientation", {})
                                    .get("min_place_confidence", 0.10),
        has_stopped=shutdown.is_set,
    )

    try:
        view.run()
    except KeyboardInterrupt:
        log.info("Interrupted by the user")
    finally:
        supervisor.stop_all()
        log.info("Shutdown complete")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

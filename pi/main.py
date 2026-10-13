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
    MappingWorker,
    ThreadSupervisor,
)

log = logging.getLogger("main")


def main() -> int:
    parser = argparse.ArgumentParser(description="INA700 AI pick and place")
    parser.add_argument("--config", default="config/config.yaml",
                        help="path to the YAML configuration file")
    args = parser.parse_args()

    config = load_config(BASE_DIR / args.config)
    logging_config = config.get("logging", {})
    # The console view IS the terminal, so INFO chatter lands on top of what
    # the operator is typing. Warnings only there; the file still gets INFO.
    console_level = logging_config.get("console_level")
    if console_level is None and config.get("gui", {}).get("kind") == "console":
        console_level = "WARNING"
    configure_logging(
        level=logging_config.get("level", "INFO"),
        log_file=str(BASE_DIR / logging_config["file"])
        if logging_config.get("file") else None,
        console_level=console_level,
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
    results: queue.Queue = queue.Queue(maxsize=2)     # pixels, from inference
    scenes: queue.Queue = queue.Queue(maxsize=2)      # millimetres, from mapping
    requests: queue.Queue = queue.Queue(maxsize=8)

    robot_config = config["robot"]
    controller = CycleController(
        get_scene=LatestResultHolder(scenes),
        selector=selector,
        commander=commander,
        state=state,
        max_attempts=robot_config.get("max_attempts", 3),
        verify_tolerance_mm=container.verify_tolerance_mm,
        robot_ready=lambda: transport.is_connected,
        wait=shutdown.wait,          # returns True as soon as shutdown is set
        retry_delay_s=robot_config.get("retry_delay_s", 1.5),
        connect_wait_s=robot_config.get("connect_wait_s", 30.0),
    )

    # --- start the worker threads ------------------------------------------
    supervisor = ThreadSupervisor(shutdown)
    supervisor.add(CaptureWorker(shutdown, frame_source, frames,
                                 max_fps=config["camera"].get("capture_fps", 10.0),
                                 tap_path=config["camera"].get("frame_tap"),
                                 tap_interval_s=config["camera"].get(
                                     "frame_tap_interval_s", 0.5)))
    supervisor.add(InferenceWorker(shutdown, pipeline, frames, results, state))
    supervisor.add(MappingWorker(shutdown, coordinates, results, scenes, state))
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
        has_stopped=shutdown.is_set,
    )

    # Command sources run beside the view, not instead of it. Tk owns the
    # main thread, so the terminal prompt cannot be a view of its own - as a
    # source it can, which is how the window and the terminal are both live.
    gui_config = config.get("gui", {})
    sources = []
    if gui_config.get("terminal_input") and view_kind != "console":
        from adapters.gui.command_sources import TerminalCommandReader
        sources.append(TerminalCommandReader(container.shapes, requests.put,
                                             on_close=shutdown.set))
    if gui_config.get("command_pipe"):
        from adapters.gui.command_sources import PipeCommandReader
        sources.append(PipeCommandReader(gui_config["command_pipe"],
                                         container.shapes, requests.put))
    for source in sources:
        source.start()

    try:
        view.run()
    except KeyboardInterrupt:
        log.info("Interrupted by the user")
    finally:
        for source in sources:
            source.stop()
        supervisor.stop_all()
        log.info("Shutdown complete")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

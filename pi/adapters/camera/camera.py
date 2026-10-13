"""Basler image acquisition through pypylon.

Author: Suraj Karki
Course: INA700 - AI-based pick and place
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

from domain.models import Frame
from ports.interfaces import FrameSource

log = logging.getLogger(__name__)


class Camera(FrameSource):
    """Captures BGR images from a Basler camera, and optionally displays them."""

    def __init__(
        self,
        serial_number: Optional[str] = None,
        exposure_us: Optional[float] = None,
        gain: Optional[float] = None,
        timeout_ms: int = 5000,
        show_window: bool = False,
        full_sensor: bool = True,
    ) -> None:
        self._serial_number = serial_number
        self._exposure_us = exposure_us
        self._gain = gain
        self._timeout_ms = timeout_ms
        # Exercise 2's live 'Output' window. Useful while aiming the camera;
        # switched off in normal operation because the Tkinter GUI is the
        # real operator interface.
        self._show_window = show_window
        # The camera keeps its area of interest in its own memory, so a crop
        # somebody left behind in Pylon Viewer survives a power cycle and
        # silently narrows the field of view. Nothing in an image says it was
        # cropped - the table simply looks closer - so the full sensor is
        # asked for explicitly on every open.
        self._full_sensor = full_sensor
        # Typed as Optional because they only exist between open() and close().
        # Every use narrows them first, which also keeps the type checker quiet.
        self._camera: Optional[Any] = None
        self._converter: Optional[Any] = None
        self._sequence = 0

    def open(self) -> None:
        """Find the camera, apply settings and start grabbing."""
        # Imported lazily so the rest of the project runs on a laptop without
        # the Basler SDK installed.
        from pypylon import pylon

        factory = pylon.TlFactory.GetInstance()

        if self._serial_number:
            # Pin to one specific camera - important if the lab bench has two.
            info = pylon.DeviceInfo()
            info.SetSerialNumber(self._serial_number)
            device = factory.CreateDevice(info)
        else:
            device = factory.CreateFirstDevice()

        # Configure a local handle and publish it only once the camera is
        # fully set up, so a half-opened camera is never visible to read().
        camera = pylon.InstantCamera(device)
        camera.Open()

        if self._full_sensor:
            self._use_full_sensor(camera)

        # Fixed exposure and gain: auto-exposure changes the colours between
        # training and the exam, which is a common source of lost accuracy.
        try:
            if self._exposure_us is not None:
                camera.ExposureAuto.SetValue("Off")
                camera.ExposureTime.SetValue(float(self._exposure_us))
            if self._gain is not None:
                camera.GainAuto.SetValue("Off")
                camera.Gain.SetValue(float(self._gain))
        except Exception as exc:  # node names differ slightly between models
            log.warning("Could not apply exposure/gain settings: %s", exc)

        # Convert whatever the sensor delivers into plain 8-bit BGR for OpenCV.
        converter = pylon.ImageFormatConverter()
        converter.OutputPixelFormat = pylon.PixelType_BGR8packed
        converter.OutputBitAlignment = pylon.OutputBitAlignment_MsbAligned

        # LatestImageOnly: we always want the freshest view of the table.
        camera.StartGrabbing(pylon.GrabStrategy_LatestImageOnly)

        self._camera = camera
        self._converter = converter
        log.info("Basler camera opened (%s), %s",
                 camera.GetDeviceInfo().GetModelName(),
                 self._describe_area(camera))

    # --- the sensor's area of interest -------------------------------------

    @staticmethod
    def _node_value(camera: Any, name: str) -> Optional[float]:
        """A camera setting, or None when this model does not have it."""
        try:
            return float(getattr(camera, name).GetValue())
        except Exception:
            return None                  # pypylon raises for a missing node

    @staticmethod
    def _set_node(camera: Any, name: str, value) -> bool:
        try:
            getattr(camera, name).SetValue(value)
            return True
        except Exception as exc:
            log.debug("Could not set %s to %s: %s", name, value, exc)
            return False

    @staticmethod
    def _node_max(camera: Any, name: str) -> Optional[int]:
        try:
            node = getattr(camera, name)
            return int(node.GetMax() if hasattr(node, "GetMax") else node.Max)
        except Exception:
            return None

    def _use_full_sensor(self, camera: Any) -> None:
        """Undo any crop or binning, so the lens sees everything it can.

        The order matters: binning and decimation change what Width and Height
        mean, and an offset has to come down before the width can go up, or
        the camera refuses the value for running off the edge of the sensor.

        Every step is optional - models differ in which nodes they carry - so
        each is attempted and ignored if absent. A camera that will not widen
        is reported rather than left to look like a short lens.
        """
        for name in ("BinningHorizontal", "BinningVertical",
                     "DecimationHorizontal", "DecimationVertical"):
            if self._node_value(camera, name) not in (None, 1.0):
                self._set_node(camera, name, 1)

        self._set_node(camera, "OffsetX", 0)
        self._set_node(camera, "OffsetY", 0)

        for name in ("Width", "Height"):
            maximum = self._node_max(camera, name)
            if maximum is not None and self._node_value(camera, name) != maximum:
                self._set_node(camera, name, maximum)

        width = self._node_value(camera, "Width")
        height = self._node_value(camera, "Height")
        width_max = self._node_max(camera, "Width")
        height_max = self._node_max(camera, "Height")
        if None in (width, height, width_max, height_max):
            return
        if width < width_max or height < height_max:
            log.warning("The camera is still cropped to %d x %d of a possible "
                        "%d x %d - the field of view is %.0f%% of the sensor. "
                        "Check Pylon Viewer for a locked area of interest.",
                        width, height, width_max, height_max,
                        100.0 * (width * height) / (width_max * height_max))

    def _describe_area(self, camera: Any) -> str:
        """What the camera will actually deliver, and out of how much."""
        width = self._node_value(camera, "Width")
        height = self._node_value(camera, "Height")
        if width is None or height is None:
            return "area unknown"
        width_max = self._node_max(camera, "Width") or int(width)
        height_max = self._node_max(camera, "Height") or int(height)
        if int(width) == width_max and int(height) == height_max:
            return f"{int(width)} x {int(height)}, the whole sensor"
        return f"{int(width)} x {int(height)} of {width_max} x {height_max} - CROPPED"

    def read(self) -> Optional[Frame]:
        """Grab the newest image, or return None if the grab timed out."""
        from pypylon import pylon

        camera = self._camera
        converter = self._converter
        if camera is None or converter is None:
            log.debug("read() called before open() - no camera yet")
            return None

        if not camera.IsGrabbing():
            return None

        grab = camera.RetrieveResult(
            self._timeout_ms, pylon.TimeoutHandling_Return
        )
        try:
            if not grab.GrabSucceeded():
                log.debug("Basler grab failed: %s", grab.GetErrorDescription())
                return None
            image = converter.Convert(grab).GetArray()
        finally:
            grab.Release()

        if self._show_window:
            self._display(image)

        self._sequence += 1
        return Frame(image=image, sequence=self._sequence,
                     captured_at=time.monotonic())

    def _display(self, image) -> None:
        """Show the live feed in a resizable window, as in Exercise 2."""
        import cv2
        cv2.namedWindow("Output", cv2.WINDOW_NORMAL)
        cv2.imshow("Output", image)
        cv2.waitKey(1)

    def close(self) -> None:
        """Stop grabbing and release the camera, tolerating a partial open."""
        camera = self._camera
        if camera is None:
            return
        if self._show_window:
            try:
                import cv2
                cv2.destroyWindow("Output")
            except Exception:
                pass

        try:
            if camera.IsGrabbing():
                camera.StopGrabbing()
            camera.Close()
        except Exception as exc:
            log.warning("Error while closing the Basler camera: %s", exc)
        finally:
            self._camera = None
            self._converter = None

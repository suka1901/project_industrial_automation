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
    ) -> None:
        self._serial_number = serial_number
        self._exposure_us = exposure_us
        self._gain = gain
        self._timeout_ms = timeout_ms
        # Exercise 2's live 'Output' window. Useful while aiming the camera;
        # switched off in normal operation because the Tkinter GUI is the
        # real operator interface.
        self._show_window = show_window
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
        log.info("Basler camera opened (%s)",
                 camera.GetDeviceInfo().GetModelName())

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

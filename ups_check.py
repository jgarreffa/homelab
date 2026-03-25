# -*- coding: utf-8 -*-
import os
import array
import struct
import fcntl
from datadog_checks.base import AgentCheck

# ioctl to actively request a HID feature report from the device
# HIDIOCGFEATURE(64) - polls the device rather than waiting for it to send data
def _IOWR(type_char, number, size):
    return (3 << 30) | (size << 16) | (type_char << 8) | number

HIDIOCGFEATURE = _IOWR(ord('H'), 0x07, 64)

__version__ = "1.0.0"

# HID report byte positions for common generic UPS devices
# These are standard positions for CyberPower/generic HID UPS units
STATUS_BYTE    = 0
CHARGE_BYTE    = 2
RUNTIME_BYTE   = 4

# Status flags
FLAG_ON_BATTERY = 0x02
FLAG_LOW_BATTERY = 0x04
FLAG_CHARGING   = 0x10


class UpsCheck(AgentCheck):
    """
    Custom Datadog Agent check (Python 2.7 compatible).
    Reads UPS data directly from /dev/hidraw without needing NUT.

    Submits:
      - ups.battery.charge     (percent)
      - ups.on_mains           (1 = mains, 0 = on battery)
      - ups.battery.low        (1 = low battery, 0 = ok)

    Service checks:
      - ups.status             OK / WARNING / CRITICAL
      - ups.device.can_connect OK / CRITICAL
    """

    STATUS_SERVICE_CHECK = "ups.status"
    DEVICE_SERVICE_CHECK = "ups.device.can_connect"

    def check(self, instance):
        device = instance.get("device", "/dev/hidraw0")
        tags   = instance.get("tags", []) + ["device:digitech-ups"]

        try:
            # Actively request a HID feature report via ioctl
            # This polls the device immediately rather than waiting for it to send data
            fd = os.open(device, os.O_RDWR)
            try:
                buf = array.array('B', [0] * 64)
                buf[0] = 0  # report ID 0
                fcntl.ioctl(fd, HIDIOCGFEATURE, buf, True)
                data = buf.tostring()
            finally:
                os.close(fd)

            if not data or len(data) < 5:
                self.service_check(
                    self.DEVICE_SERVICE_CHECK,
                    AgentCheck.CRITICAL,
                    tags=tags,
                    message="No data returned from UPS device {0}".format(device),
                )
                return

            self.service_check(self.DEVICE_SERVICE_CHECK, AgentCheck.OK, tags=tags)

            # Parse bytes
            raw = struct.unpack("B" * len(data), data)

            status_byte  = raw[STATUS_BYTE]
            charge       = raw[CHARGE_BYTE] if len(raw) > CHARGE_BYTE else None
            runtime_raw  = raw[RUNTIME_BYTE] if len(raw) > RUNTIME_BYTE else None

            on_battery  = 1 if (status_byte & FLAG_ON_BATTERY) else 0
            low_battery = 1 if (status_byte & FLAG_LOW_BATTERY) else 0
            on_mains    = 0 if on_battery else 1

            self.gauge("ups.on_mains",       on_mains,    tags=tags)
            self.gauge("ups.battery.low",    low_battery, tags=tags)

            if charge is not None:
                self.gauge("ups.battery.charge", charge, tags=tags)

            if runtime_raw is not None:
                self.gauge("ups.battery.runtime", runtime_raw * 60, tags=tags)

            # Log raw bytes to help calibrate if values look wrong
            self.log.debug("UPS raw HID bytes: {0}".format(list(raw[:10])))

            # Service check
            if low_battery:
                self.service_check(
                    self.STATUS_SERVICE_CHECK,
                    AgentCheck.CRITICAL,
                    tags=tags,
                    message="UPS battery is LOW and on battery power!",
                )
            elif on_battery:
                self.service_check(
                    self.STATUS_SERVICE_CHECK,
                    AgentCheck.WARNING,
                    tags=tags,
                    message="UPS is running on battery — mains power lost",
                )
            else:
                self.service_check(
                    self.STATUS_SERVICE_CHECK,
                    AgentCheck.OK,
                    tags=tags,
                    message="UPS on mains power, battery charge: {0}%".format(charge),
                )

        except OSError as e:
            self.service_check(
                self.DEVICE_SERVICE_CHECK,
                AgentCheck.CRITICAL,
                tags=tags,
                message="Cannot open UPS device {0}: {1}".format(device, str(e)),
            )

# -*- coding: utf-8 -*-
import subprocess
import re
from datadog_checks.base import AgentCheck

__version__ = "1.0.0"


class UpsCheck(AgentCheck):
    """
    Custom Datadog Agent check (Python 2.7 compatible) that queries NUT
    (Network UPS Tools) via the upsc command and submits:

      - ups.battery.charge      (percent)
      - ups.battery.runtime     (seconds)
      - ups.battery.voltage     (V)
      - ups.input.voltage       (V)
      - ups.output.voltage      (V)
      - ups.load                (percent)

    Service checks:
      - ups.status              OK (on mains) / CRITICAL (on battery / low battery)
      - ups.nut.can_connect     OK / CRITICAL
    """

    STATUS_SERVICE_CHECK  = "ups.status"
    NUT_SERVICE_CHECK     = "ups.nut.can_connect"

    # NUT status flags
    STATUS_ONLINE       = "OL"   # On Line (mains power)
    STATUS_ON_BATTERY   = "OB"   # On Battery
    STATUS_LOW_BATTERY  = "LB"   # Low Battery
    STATUS_CHARGING     = "CHRG" # Charging
    STATUS_DISCHARGING  = "DISCHRG"

    def check(self, instance):
        ups_name = instance.get("ups_name", "ups")
        host     = instance.get("host", "localhost")
        port     = instance.get("port", 3493)
        tags     = instance.get("tags", []) + ["ups:{0}".format(ups_name)]

        target = "{0}@{1}:{2}".format(ups_name, host, port)

        try:
            proc = subprocess.Popen(
                ["upsc", target],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            output, err = proc.communicate()

            if isinstance(output, bytes):
                output = output.decode("utf-8")
            if isinstance(err, bytes):
                err = err.decode("utf-8")

            if proc.returncode != 0:
                self.service_check(
                    self.NUT_SERVICE_CHECK,
                    AgentCheck.CRITICAL,
                    tags=tags,
                    message="upsc failed: {0}".format(err.strip()),
                )
                return

            self.service_check(self.NUT_SERVICE_CHECK, AgentCheck.OK, tags=tags)

            # Parse key/value pairs from upsc output
            data = {}
            for line in output.splitlines():
                if ":" in line:
                    key, _, value = line.partition(":")
                    data[key.strip()] = value.strip()

            # --- Metrics ---
            def submit_gauge(metric, nut_key):
                val = data.get(nut_key)
                if val is not None:
                    try:
                        self.gauge(metric, float(val), tags=tags)
                    except ValueError:
                        pass

            submit_gauge("ups.battery.charge",   "battery.charge")
            submit_gauge("ups.battery.runtime",  "battery.runtime")
            submit_gauge("ups.battery.voltage",  "battery.voltage")
            submit_gauge("ups.input.voltage",    "input.voltage")
            submit_gauge("ups.output.voltage",   "output.voltage")
            submit_gauge("ups.load",             "ups.load")

            # --- Service check based on UPS status ---
            status = data.get("ups.status", "")

            if self.STATUS_LOW_BATTERY in status:
                self.service_check(
                    self.STATUS_SERVICE_CHECK,
                    AgentCheck.CRITICAL,
                    tags=tags,
                    message="UPS battery is LOW — status: {0}".format(status),
                )
            elif self.STATUS_ON_BATTERY in status:
                self.service_check(
                    self.STATUS_SERVICE_CHECK,
                    AgentCheck.WARNING,
                    tags=tags,
                    message="UPS is running on battery — status: {0}".format(status),
                )
            elif self.STATUS_ONLINE in status:
                self.service_check(
                    self.STATUS_SERVICE_CHECK,
                    AgentCheck.OK,
                    tags=tags,
                    message="UPS on mains power — status: {0}".format(status),
                )
            else:
                self.service_check(
                    self.STATUS_SERVICE_CHECK,
                    AgentCheck.UNKNOWN,
                    tags=tags,
                    message="Unknown UPS status: {0}".format(status),
                )

            # Submit status as a gauge too (1 = online, 0 = on battery)
            on_mains = 1 if self.STATUS_ONLINE in status else 0
            self.gauge("ups.on_mains", on_mains, tags=tags)

        except Exception as e:
            self.service_check(
                self.NUT_SERVICE_CHECK,
                AgentCheck.CRITICAL,
                tags=tags,
                message=str(e),
            )

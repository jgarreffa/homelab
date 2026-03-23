# -*- coding: utf-8 -*-
import subprocess
import re
from datadog_checks.base import AgentCheck

__version__ = "1.0.0"


class PingCheck(AgentCheck):
    """
    Custom Datadog Agent check (Python 2.7 compatible) that pings a host
    and submits:
      - network.ping.avg_rtt     (ms)
      - network.ping.min_rtt     (ms)
      - network.ping.max_rtt     (ms)
      - network.ping.packet_loss (%)
      - network.ping.can_connect (service check: OK / CRITICAL)
    """

    SERVICE_CHECK_NAME = "network.ping.can_connect"

    def check(self, instance):
        host  = instance.get("host", "8.8.8.8")
        count = int(instance.get("count", 5))
        tags  = instance.get("tags", []) + ["target_host:{0}".format(host)]

        try:
            # subprocess.run() does not exist in Python 2.7 — use Popen instead.
            # -W 5 tells ping to wait max 5s per packet, so the check is self-bounding.
            proc = subprocess.Popen(
                ["ping", "-c", str(count), "-W", "5", host],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            output, _ = proc.communicate()

            # In Python 2.7 communicate() returns bytes, decode to str
            if isinstance(output, bytes):
                output = output.decode("utf-8")

            # Parse RTT stats: rtt min/avg/max/mdev = 10.1/12.4/15.7/1.2 ms
            rtt_match = re.search(
                r"rtt min/avg/max/mdev = ([\d.]+)/([\d.]+)/([\d.]+)/([\d.]+)",
                output,
            )
            if rtt_match:
                self.gauge("network.ping.min_rtt", float(rtt_match.group(1)), tags=tags)
                self.gauge("network.ping.avg_rtt", float(rtt_match.group(2)), tags=tags)
                self.gauge("network.ping.max_rtt", float(rtt_match.group(3)), tags=tags)

            # Parse packet loss: "0% packet loss" or "100% packet loss"
            loss_match = re.search(r"(\d+)% packet loss", output)
            if loss_match:
                self.gauge(
                    "network.ping.packet_loss", float(loss_match.group(1)), tags=tags
                )

            if proc.returncode == 0:
                self.service_check(self.SERVICE_CHECK_NAME, AgentCheck.OK, tags=tags)
            else:
                self.service_check(
                    self.SERVICE_CHECK_NAME,
                    AgentCheck.CRITICAL,
                    tags=tags,
                    message="Ping to {0} failed (exit code {1})".format(host, proc.returncode),
                )

        except Exception as e:
            self.service_check(
                self.SERVICE_CHECK_NAME,
                AgentCheck.CRITICAL,
                tags=tags,
                message=str(e),
            )

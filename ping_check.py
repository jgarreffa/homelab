# -*- coding: utf-8 -*-
import subprocess
import re
from datadog_checks.base import AgentCheck

__version__ = "1.0.0"


class PingCheck(AgentCheck):

    SERVICE_CHECK_NAME = "network.ping.can_connect"

    def check(self, instance):
        host  = instance.get("host", "8.8.8.8")
        count = int(instance.get("count", 5))
        tags  = instance.get("tags", []) + ["target_host:{0}".format(host)]

        try:
            proc = subprocess.Popen(
                ["ping", "-c", str(count), "-W", "5", host],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            output, _ = proc.communicate()

            if isinstance(output, bytes):
                output = output.decode("utf-8")

            rtt_match = re.search(
                r"rtt min/avg/max/mdev = ([\d.]+)/([\d.]+)/([\d.]+)/([\d.]+)",
                output,
            )
            if rtt_match:
                self.gauge("network.ping.min_rtt", float(rtt_match.group(1)), tags=tags)
                self.gauge("network.ping.avg_rtt", float(rtt_match.group(2)), tags=tags)
                self.gauge("network.ping.max_rtt", float(rtt_match.group(3)), tags=tags)

            loss_match = re.search(r"(\d+)% packet loss", output)
            if loss_match:
                self.gauge("network.ping.packet_loss", float(loss_match.group(1)), tags=tags)

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

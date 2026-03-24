# -*- coding: utf-8 -*-
import hmac
import hashlib
import requests
from datetime import datetime
from datadog_checks.base import AgentCheck

__version__ = "1.0.0"

BASE_URL = "https://timetableapi.ptv.vic.gov.au"
ROUTE_TYPE_TRAIN = 0


def build_url(path, dev_id, api_key):
    """Sign a PTV API request with HMAC-SHA1 as required by the PTV API."""
    raw = "{0}?devid={1}".format(path, dev_id)
    key = api_key.encode("utf-8")
    msg = raw.encode("utf-8")
    signature = hmac.new(key, msg, hashlib.sha1).hexdigest().upper()
    return "{0}{1}&signature={2}".format(BASE_URL, raw, signature)


class PtvCheck(AgentCheck):
    """
    Custom Datadog Agent check (Python 2.7 compatible) for the Hurstbridge line.

    Submits per stop/direction:
      - ptv.next_train_minutes   minutes until next departure
      - ptv.disruptions.count    number of active disruptions on the line

    Service checks:
      - ptv.api.can_connect      OK / CRITICAL
      - ptv.disruptions.status   OK / WARNING / CRITICAL
    """

    API_SERVICE_CHECK   = "ptv.api.can_connect"
    DISRUPT_SERVICE_CHECK = "ptv.disruptions.status"

    def check(self, instance):
        dev_id  = str(instance.get("dev_id", ""))
        api_key = str(instance.get("api_key", ""))
        stops   = instance.get("stops", [])
        route_id = int(instance.get("route_id", 12))  # 12 = Hurstbridge line
        base_tags = instance.get("tags", []) + ["route:hurstbridge"]

        if not dev_id or not api_key:
            self.service_check(
                self.API_SERVICE_CHECK,
                AgentCheck.CRITICAL,
                tags=base_tags,
                message="Missing dev_id or api_key in ptv_check.yaml",
            )
            return

        # --- Disruptions for the whole Hurstbridge line ---
        try:
            disrupt_url = build_url(
                "/v3/disruptions/route/{0}".format(route_id),
                dev_id,
                api_key,
            )
            resp = requests.get(disrupt_url, timeout=10)
            resp.raise_for_status()
            data = resp.json()

            disruptions = data.get("disruptions", {})
            # Flatten all disruption categories into one list
            all_disruptions = []
            for category_list in disruptions.values():
                if isinstance(category_list, list):
                    all_disruptions.extend(category_list)

            disrupt_count = len(all_disruptions)
            self.gauge("ptv.disruptions.count", disrupt_count, tags=base_tags)

            if disrupt_count == 0:
                self.service_check(self.DISRUPT_SERVICE_CHECK, AgentCheck.OK, tags=base_tags)
            elif disrupt_count <= 2:
                self.service_check(
                    self.DISRUPT_SERVICE_CHECK,
                    AgentCheck.WARNING,
                    tags=base_tags,
                    message="{0} disruption(s) on Hurstbridge line".format(disrupt_count),
                )
            else:
                self.service_check(
                    self.DISRUPT_SERVICE_CHECK,
                    AgentCheck.CRITICAL,
                    tags=base_tags,
                    message="{0} disruptions on Hurstbridge line".format(disrupt_count),
                )

            self.service_check(self.API_SERVICE_CHECK, AgentCheck.OK, tags=base_tags)

        except Exception as e:
            self.service_check(
                self.API_SERVICE_CHECK,
                AgentCheck.CRITICAL,
                tags=base_tags,
                message="Error fetching disruptions: {0}".format(str(e)),
            )
            return

        # --- Next departure for each configured stop ---
        for stop in stops:
            stop_id   = stop.get("stop_id")
            stop_name = stop.get("name", str(stop_id))
            stop_tags = base_tags + ["stop:{0}".format(stop_name)]

            try:
                dep_url = build_url(
                    "/v3/departures/route_type/{0}/stop/{1}".format(
                        ROUTE_TYPE_TRAIN, stop_id
                    ),
                    dev_id,
                    api_key,
                )
                resp = requests.get(
                    dep_url,
                    params={"route_id": route_id, "max_results": 5, "expand": "run"},
                    timeout=10,
                )
                resp.raise_for_status()
                data = resp.json()

                departures = data.get("departures", [])
                now = datetime.utcnow()

                for dep in departures:
                    # Use estimated time if available, fall back to scheduled
                    dep_time_str = dep.get("estimated_departure_utc") or dep.get("scheduled_departure_utc")
                    if not dep_time_str:
                        continue

                    # Parse ISO8601 timestamp (strip trailing Z)
                    dep_time_str = dep_time_str.replace("Z", "")
                    dep_time = datetime.strptime(dep_time_str[:19], "%Y-%m-%dT%H:%M:%S")

                    minutes_away = (dep_time - now).total_seconds() / 60.0
                    if minutes_away < 0:
                        continue  # already departed

                    direction_id = dep.get("direction_id", 0)
                    direction = "inbound" if direction_id == 1 else "outbound"
                    dep_tags = stop_tags + ["direction:{0}".format(direction)]

                    self.gauge("ptv.next_train_minutes", round(minutes_away, 1), tags=dep_tags)
                    break  # only submit the very next departure per stop/direction

            except Exception as e:
                self.log.warning("Error fetching departures for stop {0}: {1}".format(stop_name, str(e)))

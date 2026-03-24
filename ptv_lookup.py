#!/usr/bin/env python3
"""
PTV API Lookup Script
---------------------
Use this to find stop IDs for the Hurstbridge line once you have your
PTV API credentials (dev_id and api_key from api@ptv.vic.gov.au).

Usage:
    python3 ptv_lookup.py

Fill in your DEV_ID and API_KEY below before running.
"""

import hmac
import hashlib
import requests
import json

# ---------------------------------------------------------------
# Fill these in with your PTV API credentials
DEV_ID  = "YOUR_DEV_ID"
API_KEY = "YOUR_API_KEY"
# ---------------------------------------------------------------

BASE_URL     = "https://timetableapi.ptv.vic.gov.au"
ROUTE_ID     = 12   # Hurstbridge line
ROUTE_TYPE   = 0    # 0 = Train


def build_url(path):
    """Sign a PTV API request with HMAC-SHA1."""
    raw       = "{0}?devid={1}".format(path, DEV_ID)
    key       = API_KEY.encode("utf-8")
    msg       = raw.encode("utf-8")
    signature = hmac.new(key, msg, hashlib.sha1).hexdigest().upper()
    return "{0}{1}&signature={2}".format(BASE_URL, raw, signature)


def get_stops():
    """Fetch all stops on the Hurstbridge line."""
    path = "/v3/stops/route/{0}/route_type/{1}".format(ROUTE_ID, ROUTE_TYPE)
    url  = build_url(path)
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    return resp.json().get("stops", [])


def get_disruptions():
    """Fetch active disruptions on the Hurstbridge line."""
    path = "/v3/disruptions/route/{0}".format(ROUTE_ID)
    url  = build_url(path)
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    disruptions = resp.json().get("disruptions", {})
    all_disruptions = []
    for category_list in disruptions.values():
        if isinstance(category_list, list):
            all_disruptions.extend(category_list)
    return all_disruptions


def get_next_departures(stop_id, stop_name):
    """Fetch next 5 departures from a given stop."""
    path = "/v3/departures/route_type/{0}/stop/{1}".format(ROUTE_TYPE, stop_id)
    url  = build_url(path)
    resp = requests.get(
        url,
        params={"route_id": ROUTE_ID, "max_results": 5},
        timeout=10,
    )
    resp.raise_for_status()
    departures = resp.json().get("departures", [])
    print("\n  Next departures from {0} (stop {1}):".format(stop_name, stop_id))
    for dep in departures:
        scheduled = dep.get("scheduled_departure_utc", "N/A")
        estimated = dep.get("estimated_departure_utc", "on time")
        direction = dep.get("direction_id")
        print("    Scheduled: {0}  |  Estimated: {1}  |  Direction ID: {2}".format(
            scheduled, estimated, direction
        ))


def main():
    print("=" * 60)
    print("PTV Hurstbridge Line — API Lookup")
    print("=" * 60)

    # --- Stops ---
    print("\n[1] All stops on the Hurstbridge line:\n")
    stops = get_stops()
    stops_sorted = sorted(stops, key=lambda s: s.get("stop_sequence", 0))
    for stop in stops_sorted:
        print("  stop_id: {:<6}  name: {}".format(
            stop.get("stop_id"), stop.get("stop_name")
        ))

    # --- Disruptions ---
    print("\n[2] Active disruptions:\n")
    disruptions = get_disruptions()
    if not disruptions:
        print("  No active disruptions.")
    else:
        for d in disruptions:
            print("  - {0}: {1}".format(d.get("disruption_type"), d.get("title")))

    # --- Next departures from key stations ---
    print("\n[3] Next departures from key stations:")
    key_stations = [s for s in stops if s.get("stop_name") in ("Eltham", "Parliament")]
    for station in key_stations:
        get_next_departures(station.get("stop_id"), station.get("stop_name"))

    print("\n" + "=" * 60)
    print("Copy the stop_ids above into your ptv_check.yaml")
    print("=" * 60)


if __name__ == "__main__":
    main()

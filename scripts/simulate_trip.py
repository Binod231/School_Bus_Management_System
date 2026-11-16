#!/usr/bin/env python3
"""
EDURIDE - High-Frequency GPS Trip & Telematics Simulator
Simulates real-time vehicle GPS pings, geofence arrival detection,
speeding telematics alerts, and end-of-trip sweep verification.
"""

import sys
import time
import math
import argparse
import urllib.request
import json
import urllib.parse

def haversine_distance(lat1, lon1, lat2, lon2):
    R = 6371000.0  # Earth radius in meters
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2.0)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0)**2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return R * c

def interpolate_points(p1, p2, num_steps):
    points = []
    for i in range(num_steps + 1):
        ratio = i / float(num_steps)
        lat = p1[0] + (p2[0] - p1[0]) * ratio
        lon = p1[1] + (p2[1] - p1[1]) * ratio
        points.append((lat, lon))
    return points

def make_request(url, method="GET", headers=None, data=None):
    if headers is None:
        headers = {}
    req = urllib.request.Request(url, method=method, headers=headers)
    if data is not None:
        req.data = json.dumps(data).encode("utf-8")
        req.headers["Content-Type"] = "application/json"
    try:
        with urllib.request.urlopen(req) as resp:
            content = resp.read().decode("utf-8")
            return resp.status, json.loads(content) if content else {}
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8")
        try:
            parsed = json.loads(err_body)
        except Exception:
            parsed = {"raw": err_body}
        return e.code, parsed

def login_driver(base_url, email, password):
    login_url = f"{base_url}/api/v1/login"
    post_data = urllib.parse.urlencode({"username": email, "password": password}).encode("utf-8")
    req = urllib.request.Request(
        login_url,
        data=post_data,
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    )
    with urllib.request.urlopen(req) as resp:
        body = json.loads(resp.read().decode("utf-8"))
        return body.get("access_token")

def main():
    parser = argparse.ArgumentParser(description="EDURIDE Live GPS Telematics Simulator")
    parser.add_argument("--base-url", default="http://localhost:8000", help="FastAPI Base URL")
    parser.add_argument("--trip-id", type=int, required=True, help="Trip ID to simulate")
    parser.add_argument("--email", default="driver@school.com", help="Driver email")
    parser.add_argument("--password", default="driver123", help="Driver password")
    parser.add_argument("--speed-kmh", type=float, default=32.0, help="Simulated bus speed in km/h")
    parser.add_argument("--step-seconds", type=float, default=2.0, help="Seconds between GPS pings")
    parser.add_argument("--trigger-speeding", action="store_true", help="Simulate speed > 65 km/h to test warnings")
    parser.add_argument("--trigger-sos", action="store_true", help="Trigger driver SOS midway")
    args = parser.parse_args()

    print(f"🚌 EDURIDE GPS Telematics Simulator")
    print(f"Connecting to {args.base_url}...")

    # Step 1: Login
    try:
        token = login_driver(args.base_url, args.email, args.password)
        print(f"✅ Driver authenticated successfully. Token received.")
    except Exception as e:
        print(f"❌ Failed to login: {e}")
        sys.exit(1)

    auth_headers = {"Authorization": f"Bearer {token}"}

    # Step 2: Fetch trip details
    trip_url = f"{args.base_url}/api/v1/driver/trips/{args.trip_id}"
    status, trip_data = make_request(trip_url, headers=auth_headers)
    if status != 200:
        print(f"❌ Failed to get trip {args.trip_id}: {trip_data}")
        sys.exit(1)

    bus_info = trip_data.get("bus", {})
    route_info = trip_data.get("route", {})
    stops = route_info.get("stops", [])

    print(f"Trip: {trip_data.get('name')} | Bus: {bus_info.get('bus_number', 'N/A')}")
    print(f"Route: {route_info.get('name', 'N/A')} with {len(stops)} stops")

    if not stops:
        # Fallback to sample coordinates if no route stops found
        print("⚠️ No route stops configured. Using sample coordinates in Kathmandu/Lalitpur.")
        coords = [(27.700769, 85.300140), (27.705000, 85.305000), (27.710000, 85.310000), (27.715000, 85.315000)]
    else:
        coords = []
        for s in stops:
            stop_obj = s.get("stop", s)
            lat = float(stop_obj.get("latitude", 0))
            lon = float(stop_obj.get("longitude", 0))
            if lat and lon:
                coords.append((lat, lon))

    # Generate interpolated driving path
    waypoints = []
    for i in range(len(coords) - 1):
        segment = interpolate_points(coords[i], coords[i + 1], num_steps=5)
        waypoints.extend(segment[:-1])
    waypoints.append(coords[-1])

    print(f"Generated {len(waypoints)} waypoint coordinates along route.")
    print("-" * 70)

    # Step 3: Stream GPS Pings
    sos_triggered = False
    for idx, (lat, lon) in enumerate(waypoints):
        current_speed = args.speed_kmh
        if args.trigger_speeding and idx >= len(waypoints) // 2:
            current_speed = 72.5  # Exceed 60 km/h threshold

        # Mid-route SOS trigger test
        if args.trigger_sos and not sos_triggered and idx == len(waypoints) // 2:
            print(f"\n🚨 TRIGGERING EMERGENCY DRIVER SOS PANIC BUTTON...")
            sos_url = f"{args.base_url}/api/v1/driver/trips/{args.trip_id}/sos"
            s_code, s_resp = make_request(sos_url, method="POST", headers=auth_headers, data={
                "latitude": lat,
                "longitude": lon,
                "emergency_type": "breakdown",
                "description": "Simulated mechanical failure / engine smoke detected"
            })
            print(f"SOS Response [{s_code}]: {s_resp.get('message', s_resp)}")
            sos_triggered = True

        ping_payload = {
            "latitude": round(lat, 6),
            "longitude": round(lon, 6),
            "speed": current_speed,
            "heading": 45.0
        }

        loc_url = f"{args.base_url}/api/v1/driver/trips/{args.trip_id}/location"
        code, resp = make_request(loc_url, method="POST", headers=auth_headers, data=ping_payload)

        status_str = f"[{idx+1}/{len(waypoints)}] Lat: {lat:.6f}, Lon: {lon:.6f} | Speed: {current_speed:.1f} km/h"
        if current_speed > 60.0:
            status_str += " ⚠️ [SPEED VIOLATION]"
        print(status_str)

        time.sleep(args.step_seconds)

    print("-" * 70)
    print("✅ All route coordinates streamed.")

    # Step 4: Verify End-of-Trip Sweep
    print("Performing mandatory End-of-Trip rear bus sweep...")
    sweep_url = f"{args.base_url}/api/v1/driver/trips/{args.trip_id}/verify-sweep"
    sw_code, sw_resp = make_request(sweep_url, method="POST", headers=auth_headers, data={
        "confirm_seats_empty": True,
        "notes": "End-of-route physical sweep complete. No children left onboard."
    })
    print(f"Sweep Check [{sw_code}]: {sw_resp.get('message', sw_resp)}")

if __name__ == "__main__":
    main()


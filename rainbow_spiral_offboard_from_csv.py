#!/usr/bin/env python3

import asyncio
import csv
import io
import sys
import anyio
from mavsdk import System
from mavsdk.offboard import PositionNedYaw, VelocityNedYaw
from mavsdk.offboard import OffboardError
from mavsdk.telemetry import LandedState
from mavsdk.lights import LightsError, LightMatrix, LightStrip

YAW_ANGLE = 0.0
TRACE_LIGHT_COLOR = 0x00FF0000  # Red color for tracing lights
LED_STRIP_LENGTH = 16  # Number of LEDs in each strip
NUM_STRIPS = 4        # Number of strips in the matrix

RAINBOW_COLORS = [
    (1.0, 0.0, 0.0),   # Red
    (1.0, 0.0, 1.0),   # Pink
    (0.0, 1.0, 0.0),   # Green
    (0.0, 0.0, 1.0),   # Blue
]

def interpolate_color(idx, total_points):
    """Return an RGB tuple interpolated along the rainbow sequence, scaled so max channel = 1.0."""
    num_segments = len(RAINBOW_COLORS) - 1
    t_total = idx / max(1, total_points - 1)
    segment_length = 1.0 / num_segments
    segment_idx = min(int(t_total / segment_length), num_segments - 1)
    t_segment = (t_total - segment_idx * segment_length) / segment_length
    c0 = RAINBOW_COLORS[segment_idx]
    c1 = RAINBOW_COLORS[segment_idx + 1]
    rgb = tuple(c0[i] + (c1[i] - c0[i]) * t_segment for i in range(3))

    # Scale so that at least one channel = 1.0
    max_channel = max(rgb)
    if max_channel > 0:
        rgb = tuple(x / max_channel for x in rgb)
    return rgb


async def run(connection_address, csv_file):
    # Define a dictionary to map mode codes to their descriptions
    mode_descriptions = {
        0: "On the ground",
        10: "Initial climbing state",
        20: "Initial holding after climb",
        30: "Moving to start point",
        40: "Holding at start point",
        50: "Tracing",
        60: "Holding at end point",
        70: "Returning to home coordinate",
        80: "Landing",
    }

    # Connect to the drone
    drone = System()
    await drone.connect(system_address=connection_address)

    # Wait for the drone to connect
    print("-- Waiting for drone to connect...")
    async for state in drone.core.connection_state():
        if state.is_connected:
            print("-- Connected to drone!")
            break

    # Wait for the drone to have a global position estimate
    print("-- Waiting for drone to have a global position estimate...")
    async for health in drone.telemetry.health():
        if health.is_global_position_ok and health.is_home_position_ok:
            print("-- Global position estimate OK")
            break

    # Arm the drone
    print("-- Arming")
    await drone.action.arm()

    # Set the initial setpoint
    print("-- Setting initial setpoint")
    startSetpoint = PositionNedYaw(0.0, 0.0, 0.0, 0.0)
    await drone.offboard.set_position_ned(startSetpoint)

    # Start offboard mode
    print("-- Starting offboard")
    try:
        await drone.offboard.start()
    except OffboardError as error:
        print(f"^^ Starting offboard mode failed with error code: {error._result.result}")
        print("-- Disarming")
        await drone.action.disarm()
        return

    # Read data from the CSV file
    async with await anyio.open_file(csv_file, "r", newline="") as csvfile:
        content = await csvfile.read()
    waypoints = [
        (
            float(row["index"]),
            float(row["px"]),
            float(row["py"]),
            float(row["pz"]),
            int(row["mode"]),
        )
        for row in csv.DictReader(io.StringIO(content))
    ]

    print("-- Performing trajectory")
    last_mode = 0
    lights_on = False

    total_waypoints = len(waypoints)

    print("-- Starting trajectory")

    for i, waypoint in enumerate(waypoints):
        position = waypoint[1:4]
        mode_code = waypoint[-1]

        if last_mode != mode_code:
            print("## Mode number: " + f"{mode_code}, Description: {mode_descriptions[mode_code]}")
            last_mode = mode_code

            if mode_code == 50 and not lights_on:
                print("-- Turning on tracing lights")
                lights_on = True
            elif mode_code != 50 and lights_on:
                print("-- Lights to follow flight mode")
                await drone.lights.follow_flight_mode(True)
                lights_on = False

        if mode_code == 50 and i % 10 == 0:
            rgb = interpolate_color(i, total_waypoints)
            color_int = (int(rgb[0]*255)<<16) | (int(rgb[1]*255)<<8) | (int(rgb[2]*255)<<0)
            strip = LightStrip([color_int for _ in range(LED_STRIP_LENGTH)])
            matrix = LightMatrix([strip for _ in range(NUM_STRIPS)])
            try:
                await drone.lights.set_matrix(matrix)
            except LightsError as error:
                print(f"^^ Setting lights failed: {error._result.result}")

        await drone.offboard.set_position_ned(PositionNedYaw(*position, YAW_ANGLE))
        await asyncio.sleep(0.1)

    print("-- Landing")
    await drone.action.land()

    async for state in drone.telemetry.landed_state():
        if state == LandedState.ON_GROUND:
            break

    print("-- Stopping offboard")
    try:
        await drone.offboard.stop()
    except Exception as error:
        print(f"^^ Stopping offboard mode failed with error: {error}")

    print("-- Disarming")
    await drone.action.disarm()


if __name__ == "__main__":
    # Parse command-line arguments
    connection_address = sys.argv[1] if len(sys.argv) > 1 else "tcpout://daniel.adelodun.uk:5760"
    csv_file = sys.argv[2] if len(sys.argv) > 2 else "spiral.csv"
    
    # Run the asyncio loop
    asyncio.run(run(connection_address, csv_file))

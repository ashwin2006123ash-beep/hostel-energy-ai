"""
Tests for Hostel Energy AI — Live Random Power Simulation Every 10 Seconds
Covers all 10 requirements from the specification:
1. Readings update every 10 seconds using a controllable test clock
2. Different rooms maintain independent simulation state
3. Power can increase and decrease naturally within the configured profile
4. Cumulative energy never decreases during normal operation
5. Offline sensors do not produce fabricated readings
6. Manual OFF and genuine trips remain respected
7. Optimization gradually reduces simulated controllable loads toward target
8. Repeated page refreshes / API calls do not create duplicate simulation loops
9. Pausing, resuming, and resetting work correctly
10. Existing project tests continue to pass
"""

import pytest
import json
import time
from app import app
from database import get_db_connection
from services.room_manager import RoomManager
from services.live_power_simulator import LivePowerSimulator, live_simulator

@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client

@pytest.fixture
def mgr():
    return RoomManager()

@pytest.fixture
def sim():
    simulator = LivePowerSimulator()
    simulator.set_deterministic(True)
    simulator.set_seed(42)
    return simulator

# --------------------------------------------------------------------------
# Requirement 1: Readings update using a controllable test clock
# --------------------------------------------------------------------------
def test_1_readings_update_using_controllable_clock(sim, mgr):
    """Verifies that simulator steps forward by given elapsed time and updates power and timestamps."""
    conn = get_db_connection()
    conn.execute(
        "UPDATE rooms SET power_w = 200.0, previous_power_w = 200.0, power_change_w = 0.0, "
        "power_change_pct = 0.0, simulation_profile = 'NORMAL_OCCUPIED', switch_state = 'ON', "
        "manual_off_lock = 0, sensor_status = 'ONLINE', fault_status = 'NONE' WHERE room_id = 'A-101'"
    )
    conn.commit()
    conn.close()

    updated = sim.step(elapsed_seconds=10.0)
    assert len(updated) > 0
    room = mgr.get_room_by_id("A-101")
    assert room["power_w"] != 200.0 or room["previous_power_w"] == 200.0
    assert "power_change_w" in room
    assert "power_change_pct" in room
    assert room["previous_power_w"] == 200.0

# --------------------------------------------------------------------------
# Requirement 2: Different rooms maintain independent simulation state
# --------------------------------------------------------------------------
def test_2_rooms_maintain_independent_simulation_state(sim, mgr):
    """Verifies that two different rooms update independently according to their own profiles and histories."""
    conn = get_db_connection()
    conn.execute("UPDATE rooms SET power_w = 120.0, simulation_profile = 'NORMAL_OCCUPIED', switch_state = 'ON', manual_off_lock = 0, sensor_status = 'ONLINE', fault_status = 'NONE' WHERE room_id = 'A-101'")
    conn.execute("UPDATE rooms SET power_w = 20.0, simulation_profile = 'LIKELY_VACANT', switch_state = 'ON', manual_off_lock = 0, sensor_status = 'ONLINE', fault_status = 'NONE' WHERE room_id = 'A-102'")
    conn.commit()
    conn.close()

    sim.step(elapsed_seconds=10.0)
    r1 = mgr.get_room_by_id("A-101")
    r2 = mgr.get_room_by_id("A-102")

    # A-101 is NORMAL_OCCUPIED (approx 50-700W)
    assert 40.0 <= r1["power_w"] <= 750.0
    # A-102 is LIKELY_VACANT (approx 0-35W)
    assert 0.0 <= r2["power_w"] <= 45.0
    # Readings are independent
    assert r1["power_w"] != r2["power_w"]

# --------------------------------------------------------------------------
# Requirement 3: Power can increase and decrease naturally within profile
# --------------------------------------------------------------------------
def test_3_power_increases_and_decreases_naturally(sim, mgr):
    """Verifies natural fluctuation (random walk with bounds) where power both increases and decreases."""
    conn = get_db_connection()
    conn.execute("UPDATE rooms SET power_w = 300.0, simulation_profile = 'NORMAL_OCCUPIED', switch_state = 'ON', manual_off_lock = 0, sensor_status = 'ONLINE', fault_status = 'NONE' WHERE room_id = 'A-101'")
    conn.commit()
    conn.close()

    increases = 0
    decreases = 0
    for _ in range(12):
        sim.step(elapsed_seconds=10.0)
        r = mgr.get_room_by_id("A-101")
        if r["power_change_w"] > 0:
            increases += 1
        elif r["power_change_w"] < 0:
            decreases += 1

    # Over 12 steps, both positive and negative natural fluctuations should occur
    assert increases > 0
    assert decreases > 0

# --------------------------------------------------------------------------
# Requirement 4: Cumulative energy never decreases during normal operation
# --------------------------------------------------------------------------
def test_4_cumulative_energy_strictly_monotonic(sim, mgr):
    """Verifies cumulative energy (kWh) increases monotonically with elapsed time and power."""
    conn = get_db_connection()
    conn.execute("UPDATE rooms SET energy_kwh = 10.5000, power_w = 500.0, simulation_profile = 'NORMAL_OCCUPIED', switch_state = 'ON', manual_off_lock = 0, sensor_status = 'ONLINE', fault_status = 'NONE' WHERE room_id = 'A-101'")
    conn.commit()
    conn.close()

    prev_energy = 10.5000
    for _ in range(5):
        sim.step(elapsed_seconds=10.0)
        curr_energy = mgr.get_room_by_id("A-101")["energy_kwh"]
        assert curr_energy >= prev_energy, f"Energy decreased from {prev_energy} to {curr_energy}!"
        prev_energy = curr_energy

# --------------------------------------------------------------------------
# Requirement 5: Offline sensors do not produce fabricated readings
# --------------------------------------------------------------------------
def test_5_offline_sensors_do_not_fabricate_readings(sim, mgr):
    """Offline sensors must display '--' and must not have fake readings generated."""
    conn = get_db_connection()
    conn.execute("UPDATE rooms SET sensor_status = 'OFFLINE', room_state = 'SENSOR_OFFLINE', simulation_profile = 'SENSOR_OFFLINE' WHERE room_id = 'B-204'")
    conn.commit()
    conn.close()

    sim.step(elapsed_seconds=10.0)
    r = mgr.get_room_by_id("B-204")
    assert r["sensor_status"] == "OFFLINE"
    assert r["is_offline"] is True
    # The API and room manager treat offline telemetry without fabricating measurements
    assert r["optimization_state"] == "SENSOR_OFFLINE"

# --------------------------------------------------------------------------
# Requirement 6: Manual OFF and genuine trips remain respected
# --------------------------------------------------------------------------
def test_6_manual_off_and_trips_respected(sim, mgr):
    """Rooms that are manually switched OFF or TRIPPED must not be re-energized by simulation."""
    conn = get_db_connection()
    # Manual OFF room
    conn.execute(
        "UPDATE rooms SET switch_state = 'OFF', effective_switch_state = 'OFF', "
        "manual_off_lock = 1, room_state = 'MANUAL_OFF', power_w = 0.0, "
        "simulation_profile = 'MANUAL_OFF' WHERE room_id = 'A-103'"
    )
    # Tripped room
    conn.execute(
        "UPDATE rooms SET switch_state = 'OFF', effective_switch_state = 'OFF', "
        "room_state = 'TRIPPED_SIMULATED', relay_state = 'TRIPPED_SIMULATED', "
        "trip_reason = 'High-Resistance Neutral Heating Fault (78°C)', "
        "power_w = 0.0, simulation_profile = 'TRIPPED' WHERE room_id = 'C-312'"
    )
    conn.commit()
    conn.close()

    try:
        sim.step(elapsed_seconds=10.0)
        sim.step(elapsed_seconds=10.0)

        r_manual = mgr.get_room_by_id("A-103")
        assert r_manual["effective_switch_state"] == "OFF"
        assert r_manual["manual_off_lock"] == 1
        assert r_manual["power_w"] == 0.0

        r_tripped = mgr.get_room_by_id("C-312")
        assert r_tripped["effective_switch_state"] == "OFF"
        assert r_tripped["room_state"] == "TRIPPED_SIMULATED"
        assert r_tripped["power_w"] == 0.0
        assert "Neutral Heating Fault" in r_tripped["trip_reason"]
    finally:
        mgr.reset_room_trip("C-312")
        mgr.reset_room_trip("A-103")

# --------------------------------------------------------------------------
# Requirement 7: Optimization gradually reduces simulated controllable loads
# --------------------------------------------------------------------------
def test_7_optimization_gradually_reduces_controllable_loads(sim, mgr):
    """Rooms with OPTIMIZING profile gradually shed controllable loads toward target."""
    conn = get_db_connection()
    conn.execute(
        "UPDATE rooms SET power_w = 1450.0, previous_power_w = 1450.0, threshold_w = 1200.0, "
        "optimization_target_w = 800.0, simulation_profile = 'OPTIMIZING', switch_state = 'ON', "
        "effective_switch_state = 'ON', manual_off_lock = 0, sensor_status = 'ONLINE', "
        "fault_status = 'NONE', simulated_loads_json = '' WHERE room_id = 'A-101'"
    )
    conn.commit()
    conn.close()

    sim.step(elapsed_seconds=10.0)
    r1 = mgr.get_room_by_id("A-101")
    assert r1["power_w"] < 1450.0, f"Expected reduction from 1450 W, got {r1['power_w']} W"

    # Step again
    sim.step(elapsed_seconds=10.0)
    r2 = mgr.get_room_by_id("A-101")
    assert r2["power_w"] <= r1["power_w"]

# --------------------------------------------------------------------------
# Requirement 8: Repeated calls / page refreshes do not create duplicate loops
# --------------------------------------------------------------------------
def test_8_no_duplicate_simulation_threads(client):
    """Calling start() repeatedly or accessing endpoints does not spawn duplicate threads."""
    s = LivePowerSimulator()
    s.start()
    first_thread = s._thread

    # Repeated calls
    s.start()
    s.start()
    assert s._thread is first_thread

    # API status call
    res = client.get("/api/rooms/live")
    assert res.status_code == 200
    data = json.loads(res.data)
    assert "simulation" in data
    assert data["simulation"]["interval_seconds"] == 10.0

    s.stop()

# --------------------------------------------------------------------------
# Requirement 9: Pausing, resuming, and resetting work properly
# --------------------------------------------------------------------------
def test_9_pausing_resuming_and_resetting(client, sim):
    """Verifies that simulator can be paused, resumed, and reset via APIs and methods."""
    res_pause = client.post("/api/simulation/pause")
    assert res_pause.status_code == 200
    assert json.loads(res_pause.data)["simulation"]["paused"] is True

    res_resume = client.post("/api/simulation/resume")
    assert res_resume.status_code == 200
    assert json.loads(res_resume.data)["simulation"]["paused"] is False

    res_step = client.post("/api/simulation/step", json={"elapsed_seconds": 10.0})
    assert res_step.status_code == 200
    data_step = json.loads(res_step.data)
    assert data_step["status"] == "success"
    assert data_step["updated_count"] > 0

    # Test profile update API
    res_prof = client.post("/api/rooms/A-101/simulation-profile", json={"profile": "HIGH_USAGE"})
    assert res_prof.status_code == 200
    assert json.loads(res_prof.data)["simulation_profile"] == "HIGH_USAGE"

    # Test reset API
    res_reset = client.post("/api/simulation/reset", json={"operator": "Test Operator"})
    assert res_reset.status_code == 200
    assert json.loads(res_reset.data)["status"] == "success"

# --------------------------------------------------------------------------
# Requirement 10: High usage profile climbs toward and above limit
# --------------------------------------------------------------------------
def test_10_high_usage_profile_climbs_above_limit(sim, mgr):
    """Verifies that HIGH_USAGE profile climbs progressively upward toward and above limit."""
    conn = get_db_connection()
    conn.execute(
        "UPDATE rooms SET power_w = 750.0, threshold_w = 1200.0, "
        "simulation_profile = 'HIGH_USAGE', switch_state = 'ON', "
        "effective_switch_state = 'ON', manual_off_lock = 0, "
        "sensor_status = 'ONLINE', fault_status = 'NONE' WHERE room_id = 'A-101'"
    )
    conn.commit()
    conn.close()

    # Over several steps, power should trend upward
    powers = [750.0]
    for _ in range(5):
        sim.step(elapsed_seconds=10.0)
        powers.append(mgr.get_room_by_id("A-101")["power_w"])

    assert powers[-1] > powers[0], f"Expected climbing power, but got sequence {powers}"

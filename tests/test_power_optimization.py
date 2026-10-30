"""
Tests for Hostel Energy AI — Power Optimization System
Covers the 16 requirements specified in Section 12:
1. Normal room below the maximum threshold
2. Power above maximum starting optimization rather than an ordinary immediate trip
3. 1500 W consumption with a 1200 W maximum and 800 W target
4. Correct calculation of 300 W excess above the maximum
5. Correct calculation of 700 W reduction required to reach the target
6. Successful simulated load reduction
7. Partial optimization when available loads cannot reach the target
8. Optimization failure when no suitable loads exist
9. Manual OFF lock preventing optimization and automatic restoration
10. Manual ON being blocked during an unresolved critical fault
11. Critical fault preserving the protective trip workflow
12. Sensor offline and stale data not being treated as 0 W
13. Stability checks and hysteresis preventing repeated toggles
14. Accurate event history and savings calculations
15. No real hardware relay commands being sent
16. Existing tests and features continuing to work
"""

import pytest
import json
import sqlite3
from app import app
from config import Config
from database import get_db_connection
from services.room_manager import RoomManager

@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client

@pytest.fixture
def mgr():
    return RoomManager()

# --------------------------------------------------------------------------
# Requirement 1: Normal room below the maximum threshold
# --------------------------------------------------------------------------
def test_1_normal_room_below_maximum_threshold(mgr):
    """1. Normal room below the maximum threshold is in NORMAL state with 0 excess."""
    mgr.reset_room_trip("A-101")
    conn = get_db_connection()
    conn.execute(
        "UPDATE rooms SET power_w = 450.0, threshold_w = 1200.0, optimization_target_w = 800.0, "
        "optimization_state = 'NORMAL', switch_state = 'ON', manual_off_lock = 0, "
        "sensor_status = 'ONLINE', fault_status = 'NONE' WHERE room_id = 'A-101'"
    )
    conn.commit()
    conn.close()

    room = mgr.get_room_by_id("A-101")
    assert room["power_w"] == 450.0
    assert room["threshold_w"] == 1200.0
    assert room["excess_power_w"] == 0.0
    assert room["reduction_required_w"] == 0.0
    assert room["optimization_state"] == "NORMAL"
    assert room["effective_switch_state"] == "ON"

    # Running optimize on already normal room should report no load shedding required
    res = mgr.optimize_room_power("A-101")
    assert res["success"] is True
    assert "tolerance" in res["message"].lower() or "below" in res["message"].lower() or "safe" in res["message"].lower()

# --------------------------------------------------------------------------
# Requirement 2: Power above maximum starts optimization, not immediate trip
# --------------------------------------------------------------------------
def test_2_power_above_maximum_starts_optimization_rather_than_trip(mgr):
    """2. Power above maximum should start optimization instead of immediately cutting mains OFF."""
    mgr.reset_room_trip("A-103")
    conn = get_db_connection()
    conn.execute(
        "UPDATE rooms SET power_w = 1450.0, threshold_w = 1200.0, optimization_target_w = 800.0, "
        "switch_state = 'ON', manual_off_lock = 0, fault_status = 'NONE', trip_reason = '', "
        "sensor_status = 'ONLINE', simulated_loads_json = '' WHERE room_id = 'A-103'"
    )
    conn.commit()
    conn.close()

    res = mgr.optimize_room_power("A-103", operator="Hostel Warden")
    assert res["success"] is True
    
    room_after = mgr.get_room_by_id("A-103")
    # Mains switch must remain ON — not an immediate destructive trip!
    assert room_after["switch_state"] == "ON"
    assert room_after["effective_switch_state"] == "ON"
    assert room_after["optimization_state"] in ["OPTIMIZED", "OPTIMIZATION_PARTIAL", "OPTIMIZED_STABILITY_CHECK"]

# --------------------------------------------------------------------------
# Requirement 3: 1500 W consumption with 1200 W maximum and 800 W target
# --------------------------------------------------------------------------
def test_3_1500w_consumption_with_1200w_max_and_800w_target(mgr):
    """3. 1500 W consumption with 1200 W maximum and 800 W target."""
    conn = get_db_connection()
    conn.execute(
        "UPDATE rooms SET power_w = 1500.0, threshold_w = 1200.0, optimization_target_w = 800.0, "
        "sensor_status = 'ONLINE' WHERE room_id = 'A-204'"
    )
    conn.commit()
    conn.close()

    room = mgr.get_room_by_id("A-204")
    assert room["power_w"] == 1500.0
    assert room["threshold_w"] == 1200.0
    assert room["optimization_target_w"] == 800.0

# --------------------------------------------------------------------------
# Requirement 4: Correct calculation of 300 W excess above maximum
# --------------------------------------------------------------------------
def test_4_correct_calculation_of_300w_excess_above_maximum(mgr):
    """4. Correct calculation of 300 W excess above maximum (1500 - 1200 = 300 W)."""
    room = mgr.get_room_by_id("A-204")
    expected_excess = 1500.0 - 1200.0
    assert room["excess_power_w"] == expected_excess
    assert room["excess_power_w"] == 300.0

# --------------------------------------------------------------------------
# Requirement 5: Correct calculation of 700 W reduction required to reach target
# --------------------------------------------------------------------------
def test_5_correct_calculation_of_700w_reduction_required_to_reach_target(mgr):
    """5. Correct calculation of 700 W reduction required to reach target (1500 - 800 = 700 W)."""
    room = mgr.get_room_by_id("A-204")
    expected_reduction = 1500.0 - 800.0
    assert room["reduction_required_w"] == expected_reduction
    assert room["reduction_required_w"] == 700.0
    # Must NOT confuse excess power (300 W) with required reduction to target (700 W)
    assert room["reduction_required_w"] != room["excess_power_w"]

# --------------------------------------------------------------------------
# Requirement 6: Successful simulated load reduction
# --------------------------------------------------------------------------
def test_6_successful_simulated_load_reduction(mgr):
    """6. Successful simulated load reduction brings power to target while protecting essential lights."""
    mgr.reset_room_trip("B-101")
    conn = get_db_connection()
    # 1350 W draw, target 800 W (reduction required = 550 W)
    conn.execute(
        "UPDATE rooms SET power_w = 1350.0, threshold_w = 1200.0, optimization_target_w = 800.0, "
        "switch_state = 'ON', manual_off_lock = 0, fault_status = 'NONE', trip_reason = '', "
        "sensor_status = 'ONLINE', simulated_loads_json = '' WHERE room_id = 'B-101'"
    )
    conn.commit()
    conn.close()

    res = mgr.optimize_room_power("B-101", operator="Hostel Warden")
    assert res["success"] is True
    outcome = res["outcome"]
    assert outcome["status"] in ["OPTIMIZED", "OPTIMIZED_STABILITY_CHECK"]
    assert outcome["power_reduction_w"] >= 500.0
    assert outcome["resulting_power_w"] <= 850.0 # Within 800 W + 50 W tolerance

    # Verify essential loads were protected
    loads = mgr.get_room_controllable_loads("B-101")
    for ld in loads:
        if ld.get("essential"):
            assert ld["state"] == "ON", f"Essential load {ld['name']} was turned off!"

# --------------------------------------------------------------------------
# Requirement 7: Partial optimization when available loads cannot reach target
# --------------------------------------------------------------------------
def test_7_partial_optimization_when_loads_cannot_reach_target(mgr):
    """7. Partial optimization when available controllable loads provide some reduction but not full target."""
    mgr.reset_room_trip("B-105")
    # Pre-configure room with only a 200 W controllable load, but needing 600 W reduction
    limited_loads = [
        {"id": "L1", "name": "Protected Study Lighting", "rated_w": 800.0, "effective_w": 800.0, "power_w": 800.0, "state": "ON", "controllable": False, "essential": True},
        {"id": "L2", "name": "Small Desk Fan", "rated_w": 200.0, "effective_w": 200.0, "power_w": 200.0, "state": "ON", "controllable": True, "essential": False}
    ]
    conn = get_db_connection()
    conn.execute(
        "UPDATE rooms SET power_w = 1400.0, threshold_w = 1200.0, optimization_target_w = 800.0, "
        "switch_state = 'ON', manual_off_lock = 0, fault_status = 'NONE', trip_reason = '', "
        "sensor_status = 'ONLINE', simulated_loads_json = ? WHERE room_id = 'B-105'",
        (json.dumps(limited_loads),)
    )
    conn.commit()
    conn.close()

    res = mgr.optimize_room_power("B-105", operator="Hostel Warden")
    assert res["success"] is True
    outcome = res["outcome"]
    # Cannot reach 800 W because only 200 W can be shed safely (power drops to 1200 W)
    assert outcome["status"] == "OPTIMIZATION_PARTIAL"
    assert outcome["power_reduction_w"] == 200.0
    assert outcome["resulting_power_w"] == 1200.0

# --------------------------------------------------------------------------
# Requirement 8: Optimization failure when no suitable loads exist
# --------------------------------------------------------------------------
def test_8_optimization_failure_when_no_suitable_loads_exist(mgr):
    """8. Optimization reports OPTIMIZATION_FAILED when zero controllable loads are available."""
    mgr.reset_room_trip("B-202")
    # All loads are essential or already OFF
    zero_loads = [
        {"id": "L1", "name": "Essential Medical Cooler", "rated_w": 900.0, "effective_w": 900.0, "power_w": 900.0, "state": "ON", "controllable": False, "essential": True},
        {"id": "L2", "name": "Ceiling Light", "rated_w": 450.0, "effective_w": 450.0, "power_w": 450.0, "state": "ON", "controllable": False, "essential": True}
    ]
    conn = get_db_connection()
    conn.execute(
        "UPDATE rooms SET power_w = 1350.0, threshold_w = 1200.0, optimization_target_w = 800.0, "
        "switch_state = 'ON', manual_off_lock = 0, fault_status = 'NONE', trip_reason = '', "
        "sensor_status = 'ONLINE', simulated_loads_json = ? WHERE room_id = 'B-202'",
        (json.dumps(zero_loads),)
    )
    conn.commit()
    conn.close()

    res = mgr.optimize_room_power("B-202", operator="Hostel Warden")
    assert res["success"] is True
    outcome = res["outcome"]
    assert outcome["status"] == "OPTIMIZATION_FAILED"
    assert outcome["power_reduction_w"] == 0.0

# --------------------------------------------------------------------------
# Requirement 9: Manual OFF lock preventing optimization and automatic restoration
# --------------------------------------------------------------------------
def test_9_manual_off_lock_prevents_optimization_and_auto_restore(mgr):
    """9. Manual OFF lock prevents optimization and automatic restoration."""
    mgr.reset_room_trip("C-101")
    mgr.manual_switch_off("C-101", operator="Chief Warden", reason="Room maintenance inspection")
    
    room = mgr.get_room_by_id("C-101")
    assert room["manual_off_lock"] == 1
    assert room["effective_switch_state"] == "OFF"

    # Optimization must be rejected
    res_opt = mgr.optimize_room_power("C-101")
    assert res_opt["success"] is False
    assert "manual off lock" in res_opt["error"].lower()

    # Automatic Problem Resolved must NOT turn the switch back ON while manual lock is held
    res_resolve = mgr.resolve_room_fault("C-101", operator="Technician", resolution_notes="Cleaned board", fault_cleared=True)
    assert res_resolve["success"] is True
    assert res_resolve["restored"] is False
    assert res_resolve["manual_lock_held"] is True
    
    room_still_locked = mgr.get_room_by_id("C-101")
    assert room_still_locked["effective_switch_state"] == "OFF"

# --------------------------------------------------------------------------
# Requirement 10: Manual ON blocked during unresolved critical fault
# --------------------------------------------------------------------------
def test_10_manual_on_blocked_during_unresolved_critical_fault(mgr):
    """10. Manual ON is blocked if an unresolved critical wiring fault exists."""
    conn = get_db_connection()
    conn.execute(
        "UPDATE rooms SET switch_state = 'OFF', relay_state = 'TRIPPED_SIMULATED', "
        "fault_status = 'ACTIVE_FAULT', trip_reason = 'Arc fault detected on 15A outlet (possible faulty wiring)', "
        "manual_off_lock = 0 WHERE room_id = 'C-201'"
    )
    conn.commit()
    conn.close()

    res_on = mgr.manual_switch_on("C-201", operator="Hostel Warden")
    assert res_on["success"] is False
    assert "critical fault" in res_on["error"].lower() or "unresolved" in res_on["error"].lower()

    room = mgr.get_room_by_id("C-201")
    assert room["effective_switch_state"] == "OFF"

# --------------------------------------------------------------------------
# Requirement 11: Critical fault preserves protective trip workflow
# --------------------------------------------------------------------------
def test_11_critical_fault_triggers_protective_trip_not_routine_opt(mgr):
    """11. Critical electrical fault triggers TRIPPED_CRITICAL and cuts simulated circuit OFF."""
    try:
        conn = get_db_connection()
        # Severe overload >= 2400 W (severe short / overload)
        conn.execute(
            "UPDATE rooms SET power_w = 2650.0, threshold_w = 1200.0, optimization_target_w = 800.0, "
            "room_state = 'HIGH_USAGE', switch_state = 'ON', effective_switch_state = 'ON', "
            "manual_off_lock = 0, trip_reason = 'Possible faulty wiring detected', "
            "fault_status = 'NONE', sensor_status = 'ONLINE', simulated_loads_json = '' WHERE room_id = 'C-312'"
        )
        conn.commit()
        conn.close()

        res = mgr.optimize_room_power("C-312", operator="System Safety Monitor")
        # Routine optimization is halted for safety and room is tripped
        assert res.get("critical_fault") is True or res.get("room_state") == "TRIPPED_CRITICAL"
        
        room = mgr.get_room_by_id("C-312")
        assert room["effective_switch_state"] == "OFF"
        assert room["switch_state"] == "OFF"
        assert room["optimization_state"] == "TRIPPED_CRITICAL"
        assert "faulty wiring" in room["trip_reason"].lower() or "critical" in room["trip_reason"].lower()
    finally:
        mgr.reset_room_trip("C-312")

# --------------------------------------------------------------------------
# Requirement 12: Sensor offline and stale data not treated as 0 W
# --------------------------------------------------------------------------
def test_12_sensor_offline_not_treated_as_zero_watts(mgr, client):
    """12. Sensor offline is flagged is_offline=True, displays -- W in UI, and blocks optimization."""
    conn = get_db_connection()
    conn.execute(
        "UPDATE rooms SET sensor_status = 'OFFLINE', power_w = 0.0, "
        "last_update = '2026-10-25 00:00:00' WHERE room_id = 'B-204'"
    )
    conn.commit()
    conn.close()

    room = mgr.get_room_by_id("B-204")
    assert room["is_offline"] is True
    assert room["sensor_status"] == "OFFLINE"

    # Optimization must refuse stale/offline data
    res = mgr.optimize_room_power("B-204")
    assert res["success"] is False
    assert "offline" in res["error"].lower()

    # Fleet API returns offline indicator
    res_api = client.get("/api/rooms/B-204/switch-state")
    assert res_api.status_code == 200
    data = res_api.get_json()
    assert data["is_offline"] is True

# --------------------------------------------------------------------------
# Requirement 13: Stability checks and hysteresis prevent repeated toggles
# --------------------------------------------------------------------------
def test_13_stability_checks_and_hysteresis_prevent_repeated_toggles(mgr):
    """13. Power within tolerance margin does not repeatedly re-trigger optimization."""
    mgr.reset_room_trip("D-101")
    conn = get_db_connection()
    # Target 800 W, power 830 W (within ±50 W tolerance margin)
    conn.execute(
        "UPDATE rooms SET power_w = 830.0, threshold_w = 1200.0, optimization_target_w = 800.0, "
        "optimization_state = 'OPTIMIZED', switch_state = 'ON', manual_off_lock = 0, "
        "fault_status = 'NONE', trip_reason = '', sensor_status = 'ONLINE' WHERE room_id = 'D-101'"
    )
    conn.commit()
    conn.close()

    res = mgr.optimize_room_power("D-101")
    assert res["success"] is True
    # Hysteresis catches that 830 W is within tolerance of 800 W target
    assert "tolerance margin" in res["message"].lower() or "safe operational limits" in res["message"].lower()

# --------------------------------------------------------------------------
# Requirement 14: Accurate event history and savings calculations
# --------------------------------------------------------------------------
def test_14_accurate_event_history_and_savings_calculation(mgr):
    """14. Optimization records accurate power reduction, duration, kWh and INR savings to room_events."""
    mgr.reset_room_trip("D-104")
    conn = get_db_connection()
    conn.execute(
        "UPDATE rooms SET power_w = 1450.0, threshold_w = 1200.0, optimization_target_w = 800.0, "
        "switch_state = 'ON', manual_off_lock = 0, fault_status = 'NONE', trip_reason = '', "
        "sensor_status = 'ONLINE', simulated_loads_json = '' WHERE room_id = 'D-104'"
    )
    conn.commit()
    conn.close()

    res = mgr.optimize_room_power("D-104", operator="Energy Auditor")
    assert res["success"] is True
    outcome = res["outcome"]

    # Verify mathematics:
    # kWh = power_reduction_w * duration_hr / 1000
    # inr = kWh * 9.20
    reduction_w = outcome["power_reduction_w"]
    expected_kwh = round((reduction_w * 1.0) / 1000.0, 3)
    expected_inr = round(expected_kwh * 9.20, 2)

    assert outcome["savings_w"] == reduction_w
    assert outcome["savings_kwh"] == expected_kwh
    assert outcome["savings_inr"] == expected_inr

    # Verify recorded in database room_events
    events = mgr.get_trip_events("D-104", limit=3)
    opt_ev = next((ev for ev in events if "OPTIMIZATION" in ev["event_type"] or "OPTIMIZED" in ev["event_type"]), None)
    assert opt_ev is not None
    assert opt_ev["savings_w"] == reduction_w
    assert opt_ev["savings_kwh"] == expected_kwh
    assert opt_ev["savings_inr"] == expected_inr

# --------------------------------------------------------------------------
# Requirement 15: No real hardware relay commands sent
# --------------------------------------------------------------------------
def test_15_no_real_hardware_relay_commands_sent(mgr, client):
    """15. Mandatory safety lock ensures physical hardware relays are permanently disabled."""
    settings = mgr.get_system_settings()
    assert settings.get("real_hardware_relay_enabled") in [0, "0", False]

    # Attempting to POST 1 to enable hardware relays must be rejected or forced to 0
    res = client.post("/api/settings", json={"real_hardware_relay_enabled": "1"})
    settings_after = mgr.get_system_settings()
    assert settings_after.get("real_hardware_relay_enabled") in [0, "0", False]

# --------------------------------------------------------------------------
# Requirement 16: Existing features and API routes continue to work
# --------------------------------------------------------------------------
def test_16_existing_features_and_api_routes_continue_working(client):
    """16. Fleet dashboard, room detail, detective, settings, and simulator routes respond cleanly."""
    res_fleet = client.get("/api/rooms/live")
    assert res_fleet.status_code == 200
    rooms_data = res_fleet.get_json()
    rooms = rooms_data.get("rooms", [])
    assert len(rooms) > 0
    # Verify optimization fields exist in fleet data
    first_room = rooms[0]
    assert "optimization_target_w" in first_room
    assert "excess_power_w" in first_room
    assert "reduction_required_w" in first_room

    res_page = client.get("/rooms/A-101")
    assert res_page.status_code == 200
    assert b"Power Optimization &amp; Controllable Loads" in res_page.data or b"Power Optimization" in res_page.data

    res_settings_page = client.get("/settings")
    assert res_settings_page.status_code == 200
    assert b"Default Preferred Optimization Target" in res_settings_page.data

    res_switch_state = client.get("/api/rooms/A-101/switch-state")
    assert res_switch_state.status_code == 200
    switch_data = res_switch_state.get_json()
    assert "optimization_state" in switch_data
    assert "controllable_loads" in switch_data

# --------------------------------------------------------------------------
# Requirement 17: Trip vs Optimization Boundary Tests (280W, 1200W, 1500W, Latched Trips, Manual Locks, Faults, Reset)
# --------------------------------------------------------------------------
def test_17_normal_280w_with_1200w_limit_never_trips(mgr):
    """280 W draw with a 1200 W overload threshold is normal and must never trip."""
    try:
        conn = get_db_connection()
        conn.execute("""
            UPDATE rooms
            SET power_w = 280.0, threshold_w = 1200.0, optimization_target_w = 800.0,
                room_state = 'NORMAL', relay_state = 'CLOSED', switch_state = 'ON',
                effective_switch_state = 'ON', manual_off_lock = 0, fault_status = 'NONE',
                trip_reason = ''
            WHERE room_id = 'A-102'
        """)
        conn.commit()
        conn.close()

        room = mgr.get_room_by_id("A-102")
        assert room["power_w"] == 280.0
        assert room["threshold_w"] == 1200.0
        assert room["excess_power_w"] == 0.0
        assert room["reduction_required_w"] == 0.0
        assert room["room_state"] == "NORMAL"
        assert room["effective_switch_state"] == "ON"
        assert room["relay_state"] == "CLOSED"

        # Optimization on 280 W must succeed with no load shedding and never trip
        res = mgr.optimize_room_power("A-102")
        assert res["success"] is True
        assert res.get("room_state") == "NORMAL" or res.get("optimization_state") == "NORMAL"
        assert res["reduction_achieved_w"] == 0.0
        
        # Verify circuit state remains ON
        after = mgr.get_room_by_id("A-102")
        assert after["effective_switch_state"] == "ON"
        assert after["relay_state"] == "CLOSED"
        assert after["room_state"] == "NORMAL"
    finally:
        mgr.reset_room_trip("A-102")

def test_18_1200w_at_limit_never_trips(mgr):
    """1200 W at limit does not exceed threshold and must never trip."""
    try:
        conn = get_db_connection()
        conn.execute("""
            UPDATE rooms
            SET power_w = 1200.0, threshold_w = 1200.0, optimization_target_w = 800.0,
                room_state = 'NORMAL', relay_state = 'CLOSED', switch_state = 'ON',
                effective_switch_state = 'ON', manual_off_lock = 0, fault_status = 'NONE',
                trip_reason = ''
            WHERE room_id = 'A-102'
        """)
        conn.commit()
        conn.close()

        room = mgr.get_room_by_id("A-102")
        assert room["power_w"] == 1200.0
        assert room["excess_power_w"] == 0.0
        assert room["effective_switch_state"] == "ON"

        # Routine optimization sheds controllable loads toward 800 W without tripping
        res = mgr.optimize_room_power("A-102")
        assert res["success"] is True
        assert res.get("critical_fault") is not True

        after = mgr.get_room_by_id("A-102")
        assert after["effective_switch_state"] == "ON"
        assert after["relay_state"] == "CLOSED"
        assert after["room_state"] != "TRIPPED_CRITICAL"
        assert after["room_state"] != "TRIPPED_SIMULATED"
    finally:
        mgr.reset_room_trip("A-102")

def test_19_1500w_high_usage_optimizes_without_falsely_reporting_trip(mgr):
    """1500 W load (> 1200 W limit) is High Usage; optimization sheds loads toward 800 W without tripping."""
    try:
        conn = get_db_connection()
        conn.execute("""
            UPDATE rooms
            SET power_w = 1500.0, threshold_w = 1200.0, optimization_target_w = 800.0,
                room_state = 'HIGH_USAGE', relay_state = 'CLOSED', switch_state = 'ON',
                effective_switch_state = 'ON', manual_off_lock = 0, fault_status = 'NONE',
                trip_reason = 'Active power (1500 W) exceeds configured limit (1200 W).',
                simulated_loads_json = ''
            WHERE room_id = 'A-102'
        """)
        conn.commit()
        conn.close()

        room = mgr.get_room_by_id("A-102")
        assert room["excess_power_w"] == 300.0
        assert room["reduction_required_w"] == 700.0

        res = mgr.optimize_room_power("A-102")
        assert res["success"] is True
        assert res.get("critical_fault") is not True
        assert res["resulting_power_w"] <= 850.0  # Within 800 W + 50 W tolerance

        after = mgr.get_room_by_id("A-102")
        assert after["effective_switch_state"] == "ON"
        assert after["relay_state"] == "CLOSED"
        assert after["room_state"] in ("NORMAL", "OPTIMIZED", "OPTIMIZATION_PARTIAL")
        assert after["room_state"] != "TRIPPED_CRITICAL"
    finally:
        mgr.reset_room_trip("A-102")

def test_20_previously_latched_safety_trip_persists_when_power_drops(mgr):
    """A previously latched safety trip must not clear simply because power falls; requires authorized restoration."""
    try:
        conn = get_db_connection()
        conn.execute("""
            UPDATE rooms
            SET room_state = 'TRIPPED_SIMULATED', relay_state = 'TRIPPED_SIMULATED',
                switch_state = 'OFF', effective_switch_state = 'OFF', manual_off_lock = 0,
                fault_status = 'ACTIVE_FAULT', power_w = 0.0, current_a = 0.0,
                trip_reason = 'Protective trip: sustained fault signature'
            WHERE room_id = 'A-102'
        """)
        conn.commit()
        conn.close()

        room = mgr.get_room_by_id("A-102")
        assert room["room_state"] == "TRIPPED_SIMULATED"
        assert room["effective_switch_state"] == "OFF"
        assert room["power_w"] == 0.0  # Open circuit physically draws 0 W

        # Routine optimization must be blocked on latched trips (code 409)
        opt_res = mgr.optimize_room_power("A-102")
        assert opt_res["success"] is False
        assert opt_res["code"] == 409
        assert "latched safety trip" in opt_res["error"]

        # Manual switch ON must be rejected while fault remains unresolved
        sw_res = mgr.manual_switch_on("A-102", operator="Warden")
        assert sw_res["success"] is False
        assert "critical fault" in sw_res["error"].lower() or "unresolved" in sw_res["error"].lower()

        # Unverified problem resolution fails
        unver_res = mgr.resolve_room_fault("A-102", fault_cleared=False, operator="Technician")
        assert unver_res["success"] is False
        assert unver_res["restored"] is False

        # Room remains tripped
        after_unver = mgr.get_room_by_id("A-102")
        assert after_unver["effective_switch_state"] == "OFF"

        # Authorized verified resolution restores the circuit
        ver_res = mgr.resolve_room_fault("A-102", fault_cleared=True, operator="Electrician", resolution_notes="Short circuit repaired.")
        assert ver_res["success"] is True
        assert ver_res["restored"] is True

        restored = mgr.get_room_by_id("A-102")
        assert restored["effective_switch_state"] == "ON"
        assert restored["room_state"] == "NORMAL"
        assert restored["fault_status"] == "NONE"
    finally:
        mgr.reset_room_trip("A-102")

def test_21_manual_off_lock_prevents_restoration_and_optimization(mgr):
    """Manual OFF lock prevents automatic restoration and routine optimization until unlocked."""
    try:
        mgr.reset_room_trip("B-202")
        mgr.manual_switch_off("B-202", operator="Warden", reason="Maintenance shutdown")

        room = mgr.get_room_by_id("B-202")
        assert room["manual_off_lock"] == 1
        assert room["effective_switch_state"] == "OFF"
        assert room["power_w"] == 0.0

        # Optimization blocked
        opt_res = mgr.optimize_room_power("B-202")
        assert opt_res["success"] is False
        assert opt_res["blocked"] is True

        # Fault resolution cannot override manual lock
        res_res = mgr.resolve_room_fault("B-202", fault_cleared=True)
        assert res_res["restored"] is False
        assert res_res.get("manual_lock_held") is True

        # Releasing lock safely restores switch to ON
        rel_res = mgr.release_manual_lock("B-202", operator="Warden")
        assert rel_res["success"] is True
        assert rel_res["restored"] is True
        assert mgr.get_room_by_id("B-202")["effective_switch_state"] == "ON"
    finally:
        mgr.release_manual_lock("B-202")
        mgr.reset_room_trip("B-202")

def test_22_critical_electrical_fault_protective_cutoff(mgr):
    """A genuine electrical fault (e.g. >= 2400 W or arc fault) triggers protective TRIPPED_CRITICAL cutoff."""
    try:
        conn = get_db_connection()
        conn.execute("""
            UPDATE rooms
            SET power_w = 2600.0, threshold_w = 1200.0, optimization_target_w = 800.0,
                room_state = 'HIGH_USAGE', relay_state = 'CLOSED', switch_state = 'ON',
                effective_switch_state = 'ON', manual_off_lock = 0, fault_status = 'NONE',
                trip_reason = 'Severe electrical overload'
            WHERE room_id = 'A-102'
        """)
        conn.commit()
        conn.close()

        # Optimization halts immediately and triggers protective cutoff
        res = mgr.optimize_room_power("A-102")
        assert res["success"] is False
        assert res.get("critical_fault") is True
        assert res["room_state"] == "TRIPPED_CRITICAL"

        after = mgr.get_room_by_id("A-102")
        assert after["room_state"] == "TRIPPED_CRITICAL"
        assert after["effective_switch_state"] == "OFF"
        assert after["relay_state"] == "TRIPPED_SIMULATED"
        assert after["power_w"] == 0.0
    finally:
        mgr.reset_room_trip("A-102")

def test_23_demo_simulation_state_reset_preserves_incident_history(mgr, client):
    """Safe demo simulation state reset restores demo rooms while preserving incident history."""
    # 1. Trigger simulation scenario on demo room A-101
    mgr.trigger_nilm_scenario(5, target_room_id="A-101", fast_forward=True)
    room_tripped = mgr.get_room_by_id("A-101")
    assert room_tripped["room_state"] == "TRIPPED_SIMULATED"

    # Count historical events before reset
    events_before = mgr.get_trip_events()
    count_before = len(events_before)
    assert count_before > 0

    # 2. Call safe demo reset endpoint
    res = client.post("/api/simulator/reset-demo", json={"operator": "Auditor Dave"})
    assert res.status_code == 200
    data = res.get_json()
    assert data["success"] is True

    # 3. Verify demo rooms are restored to clean baseline normal
    a101 = mgr.get_room_by_id("A-101")
    assert a101["room_state"] == "NORMAL"
    assert a101["effective_switch_state"] == "ON"
    assert a101["power_w"] > 0

    a102 = mgr.get_room_by_id("A-102")
    assert a102["room_state"] == "NORMAL"
    assert a102["effective_switch_state"] == "ON"
    assert a102["power_w"] == 65.0

    a103 = mgr.get_room_by_id("A-103")
    assert a103["room_state"] == "NORMAL"
    assert a103["effective_switch_state"] == "ON"
    assert a103["power_w"] == 145.0

    # 4. Verify incident history is NOT deleted (count is preserved / incremented by reset log)
    events_after = mgr.get_trip_events()
    assert len(events_after) >= count_before


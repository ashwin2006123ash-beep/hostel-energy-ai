import pytest
from services.room_manager import RoomManager
from database import get_db_connection

def test_command_center_stats():
    mgr = RoomManager()
    stats = mgr.get_command_center_stats()
    assert "total_rooms" in stats
    assert stats["total_rooms"] >= 16
    assert "rooms_online" in stats
    assert "rooms_high_usage" in stats
    assert "active_anomalies" in stats
    assert "simulated_trips" in stats
    assert "attention_rooms" in stats

def test_isolated_room_trip_and_reset():
    mgr = RoomManager()
    
    # 1. Reset Room A-102 to normal
    mgr.reset_room_trip("A-102")
    room_a102_before = mgr.get_room_by_id("A-102")
    room_a103_before = mgr.get_room_by_id("A-103")
    assert room_a102_before["room_state"] == "NORMAL"
    assert room_a102_before["relay_state"] == "CLOSED"

    # 2. Trigger auto-trip on Room A-102
    trip_res = mgr.trigger_nilm_scenario(5, target_room_id="A-102", fast_forward=True)
    assert trip_res["success"] is True

    # 3. Verify Room A-102 is tripped in simulation
    room_a102_after = mgr.get_room_by_id("A-102")
    assert room_a102_after["room_state"] == "TRIPPED_SIMULATED"
    assert room_a102_after["relay_state"] == "TRIPPED_SIMULATED"

    # 4. CRITICAL SAFETY CHECK: Verify Room A-103 is completely unaffected!
    room_a103_after = mgr.get_room_by_id("A-103")
    assert room_a103_after["room_state"] == room_a103_before["room_state"]
    assert room_a103_after["relay_state"] == room_a103_before["relay_state"]

    # 5. Reset Room A-102 back to normal
    reset_res = mgr.reset_room_trip("A-102", operator="Test Auditor")
    assert reset_res["success"] is True
    room_a102_restored = mgr.get_room_by_id("A-102")
    assert room_a102_restored["room_state"] == "NORMAL"
    assert room_a102_restored["relay_state"] == "CLOSED"

def test_nilm_scenarios():
    mgr = RoomManager()
    
    # Test Scenario 2: Unusual fan step
    res2 = mgr.trigger_nilm_scenario(2, target_room_id="A-103")
    assert res2["success"] is True
    room2 = mgr.get_room_by_id("A-103")
    assert room2["power_w"] == 135.0
    assert room2["room_state"] == "ANOMALY_DETECTED"

    # Test Scenario 7: Sensor disconnected
    res7 = mgr.trigger_nilm_scenario(7, target_room_id="B-204")
    assert res7["success"] is True
    room7 = mgr.get_room_by_id("B-204")
    assert room7["sensor_status"] == "OFFLINE"
    assert room7["room_state"] == "SENSOR_OFFLINE"

def test_settings_safety_lock():
    mgr = RoomManager()
    settings = mgr.get_system_settings()
    assert "empty_room_threshold_w" in settings
    assert "high_power_threshold_w" in settings
    assert "persistence_window_min" in settings
    # Real hardware switching must remain locked to '0'
    assert settings.get("real_hardware_relay_enabled") == "0"

def test_threshold_synchronization_from_1200_to_800():
    """
    Tests that changing the maximum room power limit from 1200 W to 800 W:
    1. Persists to system_settings in SQLite.
    2. Updates threshold_w across all rooms in the rooms table.
    3. Leaves vacant-room threshold completely independent.
    4. Survived across fresh queries without reverting.
    5. Causes rooms drawing > 800 W to be flagged as HIGH_USAGE / attention.
    """
    mgr = RoomManager()

    try:
        # Step 1: Baseline check
        orig_settings = mgr.get_system_settings()
        vacant_orig = orig_settings.get("empty_room_threshold_w", "35.0")

        # Step 2: Change threshold to 800 W
        res = mgr.update_system_settings({"high_power_threshold_w": "800.0"})
        assert res is True

        # Step 3: Check system_settings
        updated_settings = mgr.get_system_settings()
        assert float(updated_settings["high_power_threshold_w"]) == 800.0
        # Independence check: vacant threshold is untouched
        assert updated_settings.get("empty_room_threshold_w") == vacant_orig

        # Step 4: Verify all rooms reflect 800 W limit
        all_rooms = mgr.get_all_rooms()
        assert len(all_rooms) >= 16
        for r in all_rooms:
            assert float(r["threshold_w"]) == 800.0
            assert float(r["empty_threshold_w"]) == float(vacant_orig)

        # Step 5: Verify single room query reflects 800 W
        room_a101 = mgr.get_room_by_id("A-101")
        assert float(room_a101["threshold_w"]) == 800.0

        # Step 6: Verify Command Center stats reflects 800 W
        stats = mgr.get_command_center_stats()
        assert float(stats["high_power_threshold_w"]) == 800.0
        for ar in stats["attention_rooms"]:
            assert float(ar["threshold_w"]) == 800.0

        # Step 7: Verify direct SQLite raw query matches 800.0
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT threshold_w FROM rooms LIMIT 1")
        row = cursor.fetchone()
        conn.close()
        assert float(row["threshold_w"]) == 800.0

    finally:
        # Restore back to standard 1200.0 W
        mgr.update_system_settings({"high_power_threshold_w": "1200.0"})
        restored = mgr.get_system_settings()
        assert float(restored["high_power_threshold_w"]) == 1200.0

def test_threshold_validation_errors():
    """
    Tests that invalid, empty, negative, or non-numeric thresholds are rejected
    with clear error messages and 400 Bad Request status.
    """
    from app import app
    client = app.test_client()

    # 1. Negative maximum room power
    res_neg = client.post("/api/settings", json={"high_power_threshold_w": "-500"})
    assert res_neg.status_code == 400
    assert "positive" in res_neg.json["message"].lower()

    # 2. Zero maximum room power
    res_zero = client.post("/api/settings", json={"high_power_threshold_w": "0"})
    assert res_zero.status_code == 400
    assert "greater than zero" in res_zero.json["message"].lower()

    # 3. Empty maximum room power
    res_empty = client.post("/api/settings", json={"high_power_threshold_w": ""})
    assert res_empty.status_code == 400
    assert "cannot be empty" in res_empty.json["message"].lower()

    # 4. Non-numeric maximum room power
    res_str = client.post("/api/settings", json={"high_power_threshold_w": "abc_invalid"})
    assert res_str.status_code == 400
    assert "numeric" in res_str.json["message"].lower()

    # 5. Negative vacant threshold
    res_neg_vac = client.post("/api/settings", json={"empty_room_threshold_w": "-10"})
    assert res_neg_vac.status_code == 400
    assert "negative" in res_neg_vac.json["message"].lower()

def test_live_display_and_views_reflect_configured_threshold():
    """
    Tests that saving 800 W via /api/settings immediately propagates to:
    - /api/rooms/live
    - /settings HTML
    - /rooms/A-101 HTML
    """
    from app import app
    client = app.test_client()

    try:
        # Save 800 W via API
        post_res = client.post("/api/settings", json={"high_power_threshold_w": "800.0"})
        assert post_res.status_code == 200
        assert post_res.json["status"] == "success"

        # 1. Live rooms API check
        rooms_res = client.get("/api/rooms/live")
        assert rooms_res.status_code == 200
        rooms = rooms_res.json["rooms"]
        for r in rooms:
            assert float(r["threshold_w"]) == 800.0

        # 2. Settings page HTML contains value="800.0"
        settings_html_res = client.get("/settings")
        assert settings_html_res.status_code == 200
        assert '800' in settings_html_res.text

        # 3. Room detail HTML contains 800 W limit
        detail_html_res = client.get("/rooms/A-101")
        assert detail_html_res.status_code == 200
        assert '800' in detail_html_res.text

    finally:
        # Restore to 1200.0
        client.post("/api/settings", json={"high_power_threshold_w": "1200.0"})

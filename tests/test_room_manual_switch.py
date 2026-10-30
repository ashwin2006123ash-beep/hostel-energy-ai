import pytest
from app import app
from services.room_manager import RoomManager
from database import get_db_connection

@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client

def test_1_manual_off_changes_simulated_state_to_off():
    """1. Manual OFF changes the simulated state to OFF."""
    mgr = RoomManager()
    # Ensure room B-101 is normal first
    mgr.reset_room_trip("B-101")
    room_before = mgr.get_room_by_id("B-101")
    assert room_before["effective_switch_state"] == "ON"
    
    # Perform Manual OFF
    res = mgr.manual_switch_off("B-101", operator="Chief Warden", reason="Scheduled corridor testing")
    assert res["success"] is True
    assert res["switch_state"] == "OFF"
    assert res["effective_switch_state"] == "OFF"
    assert res["manual_off_lock"] == 1
    
    # Verify in DB query
    room_after = mgr.get_room_by_id("B-101")
    assert room_after["switch_state"] == "OFF"
    assert room_after["effective_switch_state"] == "OFF"
    assert room_after["manual_off_lock"] == 1
    assert room_after["power_w"] == 0.0
    assert room_after["room_state"] == "MANUAL_OFF"
    assert "Chief Warden" in room_after["last_switch_by"]

def test_2_manual_on_works_when_restoration_allowed():
    """2. Manual ON works when restoration is allowed."""
    mgr = RoomManager()
    # Room C-101 is normal, release any lock
    mgr.reset_room_trip("C-101")
    room = mgr.get_room_by_id("C-101")
    assert room["effective_switch_state"] == "ON"
    
    # Switch OFF
    mgr.manual_switch_off("C-101")
    # Release lock
    mgr.release_manual_lock("C-101")
    
    # Manual ON
    res_on = mgr.manual_switch_on("C-101", operator="Duty Officer")
    assert res_on["success"] is True
    assert res_on["effective_switch_state"] == "ON"
    
    room_after = mgr.get_room_by_id("C-101")
    assert room_after["effective_switch_state"] == "ON"
    assert room_after["room_state"] == "NORMAL"
    assert room_after["relay_state"] == "CLOSED"
    assert room_after["power_w"] > 0

def test_3_manual_on_rejected_while_critical_fault_remains():
    """3. Manual ON is rejected while a critical fault remains."""
    mgr = RoomManager()
    # Trigger auto-trip on Room A-102
    mgr.trigger_nilm_scenario(5, target_room_id="A-102", fast_forward=True)
    room = mgr.get_room_by_id("A-102")
    assert room["fault_status"] == "ACTIVE_FAULT"
    assert room["effective_switch_state"] == "OFF"
    
    # Attempt Manual ON while fault remains unresolved
    res = mgr.manual_switch_on("A-102", operator="Hostel Warden")
    assert res["success"] is False
    assert "critical fault" in res["error"].lower() or "unresolved" in res["error"].lower()
    
    # Verify switch remains OFF
    room_check = mgr.get_room_by_id("A-102")
    assert room_check["effective_switch_state"] == "OFF"

def test_4_automatic_trip_sets_room_to_off():
    """4. Automatic trip sets the room to OFF."""
    mgr = RoomManager()
    # Reset room D-101 first
    mgr.reset_room_trip("D-101")
    before = mgr.get_room_by_id("D-101")
    assert before["effective_switch_state"] == "ON"
    
    # Trigger automatic trip scenario 5
    res = mgr.trigger_nilm_scenario(5, target_room_id="D-101", fast_forward=True)
    assert res["success"] is True
    
    after = mgr.get_room_by_id("D-101")
    assert after["effective_switch_state"] == "OFF"
    assert after["switch_state"] == "OFF"
    assert after["room_state"] == "TRIPPED_SIMULATED"
    assert after["fault_status"] == "ACTIVE_FAULT"
    assert "Auto-Trip" in after["last_switch_by"]

def test_5_problem_resolved_triggers_restoration_checks():
    """5. Problem Resolved triggers the restoration checks."""
    mgr = RoomManager()
    # 5a: Tripped room without manual lock -> Problem Resolved restores power
    mgr.trigger_nilm_scenario(5, target_room_id="A-103", fast_forward=True)
    res_resolved = mgr.resolve_room_fault("A-103", operator="Hostel Electrician", resolution_notes="Heater unplugged and socket tested.")
    assert res_resolved["success"] is True
    assert res_resolved["restored"] is True
    assert res_resolved["switch_state"] == "ON"
    
    room_a103 = mgr.get_room_by_id("A-103")
    assert room_a103["effective_switch_state"] == "ON"
    assert room_a103["room_state"] == "NORMAL"
    assert room_a103["fault_status"] == "NONE"
    
    # 5b: If active dangerous fault remains (e.g. fault_cleared is False) -> restoration check fails!
    mgr.trigger_nilm_scenario(5, target_room_id="A-103", fast_forward=True)
    res_failed = mgr.resolve_room_fault("A-103", operator="Inspector", resolution_notes="Damage still observed", fault_cleared=False)
    assert res_failed["success"] is False
    assert res_failed["restored"] is False
    assert "failed" in res_failed["error"].lower() or "danger" in res_failed["error"].lower()
    
    room_a103_failed = mgr.get_room_by_id("A-103")
    assert room_a103_failed["effective_switch_state"] == "OFF"

def test_6_manual_off_lock_prevents_automatic_restoration():
    """6. A manual OFF lock prevents automatic restoration."""
    mgr = RoomManager()
    mgr.reset_room_trip("B-202")
    
    # Warden manually switches OFF room B-202 (engaging manual lock)
    mgr.manual_switch_off("B-202", operator="Head Warden")
    room = mgr.get_room_by_id("B-202")
    assert room["manual_off_lock"] == 1
    
    # Attempt Problem Resolved while manual lock is active
    res = mgr.resolve_room_fault("B-202", operator="Floor Prefect", resolution_notes="Inspected room.")
    assert res["success"] is True
    assert res["restored"] is False  # Must NOT restore power!
    assert res.get("manual_lock_held") is True
    
    # Confirm room remains OFF
    room_after = mgr.get_room_by_id("B-202")
    assert room_after["effective_switch_state"] == "OFF"
    assert room_after["manual_off_lock"] == 1

def test_7_releasing_manual_off_lock_allows_restoration_only_when_safe():
    """7. Releasing the manual OFF lock allows restoration only when safety checks pass."""
    mgr = RoomManager()
    # 7a: Safe room with manual lock -> releasing lock auto-restores to ON
    mgr.reset_room_trip("C-312")
    mgr.manual_switch_off("C-312", operator="Warden")
    res_rel = mgr.release_manual_lock("C-312", operator="Warden")
    assert res_rel["success"] is True
    assert res_rel["restored"] is True
    room_c312 = mgr.get_room_by_id("C-312")
    assert room_c312["effective_switch_state"] == "ON"
    assert room_c312["manual_off_lock"] == 0
    
    # 7b: Room with unresolved trip/fault AND manual lock -> releasing lock keeps power OFF
    mgr.trigger_nilm_scenario(5, target_room_id="C-312", fast_forward=True)
    mgr.manual_switch_off("C-312", operator="Warden")
    # Mark fault active
    conn = get_db_connection()
    conn.execute("UPDATE rooms SET fault_status = 'ACTIVE_FAULT' WHERE room_id = 'C-312'")
    conn.commit()
    conn.close()
    
    res_rel_hazard = mgr.release_manual_lock("C-312", operator="Warden")
    assert res_rel_hazard["success"] is True
    assert res_rel_hazard["lock_released"] is True
    assert res_rel_hazard["restored"] is False  # Held OFF because fault remains!
    room_c312_haz = mgr.get_room_by_id("C-312")
    assert room_c312_haz["effective_switch_state"] == "OFF"

def test_8_events_are_persisted_and_visible_after_refresh():
    """8. Events are persisted and visible after page refresh."""
    mgr = RoomManager()
    mgr.reset_room_trip("D-202")
    
    # Trigger sequence of actions
    mgr.manual_switch_off("D-202", operator="Auditor Alpha", reason="Testing persistence")
    mgr.release_manual_lock("D-202", operator="Auditor Beta")
    
    # Query fresh room details
    room = mgr.get_room_by_id("D-202")
    events = room.get("events", [])
    event_types = [e["event_type"] for e in events]
    
    assert "MANUAL_OFF" in event_types
    assert "RELEASE_LOCK" in event_types or "AUTO_RESTORE" in event_types

def test_9_invalid_room_ids_and_requests_rejected(client):
    """9. Invalid room IDs and unauthorized/malformed requests are rejected."""
    # 1. Invalid room ID in manual switch OFF
    res_404_off = client.post("/api/rooms/NON-EXISTENT-999/switch-off", json={})
    assert res_404_off.status_code == 404
    assert "not found" in res_404_off.json["error"].lower()
    
    # 2. Invalid room ID in manual switch ON
    res_404_on = client.post("/api/rooms/NON-EXISTENT-999/switch-on", json={})
    assert res_404_on.status_code == 404
    
    # 3. Invalid room ID in problem-resolved
    res_404_res = client.post("/api/rooms/NON-EXISTENT-999/problem-resolved", json={})
    assert res_404_res.status_code == 404
    
    # 4. Invalid room ID in switch-state GET
    res_404_state = client.get("/api/rooms/NON-EXISTENT-999/switch-state")
    assert res_404_state.status_code == 404

def test_10_existing_room_telemetry_and_dashboard_work(client):
    """10. Existing room telemetry and dashboard functionality continue to work."""
    # 1. Command center stats endpoint returns expected structure
    res_stats = client.get("/api/command-center/stats")
    assert res_stats.status_code == 200
    data = res_stats.json
    assert data["status"] == "success"
    assert "total_rooms" in data
    assert "rooms_switched_off" in data
    assert "manual_off_locked" in data
    
    # 2. Live rooms grid returns all 16 rooms
    res_rooms = client.get("/api/rooms/live")
    assert res_rooms.status_code == 200
    assert len(res_rooms.json["rooms"]) >= 16
    
    # 3. Filtering by switch_state works
    res_filter_on = client.get("/api/rooms/live?switch_state=ON")
    assert res_filter_on.status_code == 200
    for r in res_filter_on.json["rooms"]:
        assert r["effective_switch_state"] == "ON"

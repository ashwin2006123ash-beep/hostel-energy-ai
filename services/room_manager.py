import json
import uuid
from datetime import datetime, timedelta
from database import get_db_connection

class RoomManager:
    """
    Hostel Energy AI - Room-Level Electricity & State Machine Manager.
    Manages individual room telemetry, isolated simulated trip states,
    NILM fault scenarios, and event logging.
    """

    def get_system_settings(self):
        """Retrieves configurable operational energy thresholds and policies."""
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT key, value, description FROM system_settings")
        rows = cursor.fetchall()
        conn.close()
        settings = {r["key"]: r["value"] for r in rows}
        return settings

    def update_system_settings(self, settings_dict):
        """
        Updates operational energy policies in SQLite.
        Synchronizes rooms table and room states with the saved configuration.
        """
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            for k, v in settings_dict.items():
                cursor.execute("UPDATE system_settings SET value = ? WHERE key = ?", (str(v), k))

            # Synchronize maximum room power limit across rooms table and re-evaluate states
            if "high_power_threshold_w" in settings_dict:
                high_val = float(settings_dict["high_power_threshold_w"])
                cursor.execute("UPDATE rooms SET threshold_w = ?", (high_val,))

                # Any room drawing more than the configured limit transitions to HIGH_USAGE
                cursor.execute("""
                    UPDATE rooms
                    SET room_state = 'HIGH_USAGE',
                        trip_reason = 'Active power (' || ROUND(power_w, 1) || ' W) exceeds configured limit (' || ROUND(threshold_w, 1) || ' W).'
                    WHERE power_w > threshold_w
                      AND room_state = 'NORMAL'
                """)

                # Rooms that no longer exceed the threshold revert back to NORMAL
                cursor.execute("""
                    UPDATE rooms
                    SET room_state = 'NORMAL',
                        trip_reason = ''
                    WHERE power_w <= threshold_w
                      AND room_state = 'HIGH_USAGE'
                      AND (trip_reason LIKE '%exceeds%limit%' OR trip_reason LIKE '%exceeds%threshold%' OR trip_reason LIKE '%abrupt appliance spike%')
                """)

            # Synchronize vacant room wattage threshold across rooms table independently
            if "empty_room_threshold_w" in settings_dict:
                empty_val = float(settings_dict["empty_room_threshold_w"])
                cursor.execute("UPDATE rooms SET empty_threshold_w = ?", (empty_val,))

            conn.commit()
            return True
        finally:
            conn.close()

    def get_all_rooms(self, block_id=None, room_state=None, occupancy_state=None):
        """Retrieves list of all monitored rooms with live electrical & state telemetry."""
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            settings = self.get_system_settings()
            active_high_threshold = float(settings.get("high_power_threshold_w", 1200.0))
            active_empty_threshold = float(settings.get("empty_room_threshold_w", 35.0))

            query = "SELECT * FROM rooms WHERE 1=1"
            params = []

            if block_id and block_id != "all":
                query += " AND block_id = ?"
                params.append(block_id)
            if room_state and room_state != "all":
                query += " AND room_state = ?"
                params.append(room_state)
            if occupancy_state and occupancy_state != "all":
                query += " AND occupancy_state = ?"
                params.append(occupancy_state)

            query += " ORDER BY block_id ASC, room_number ASC"
            cursor.execute(query, params)
            rows = []
            for r in cursor.fetchall():
                rd = dict(r)
                rd["threshold_w"] = active_high_threshold
                rd["empty_threshold_w"] = active_empty_threshold
                rows.append(rd)
            return rows
        finally:
            conn.close()

    def get_room_by_id(self, room_id):
        """Retrieves full details and recent event history for a single room."""
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM rooms WHERE room_id = ?", (room_id,))
            room = cursor.fetchone()
            if not room:
                return None
            room_dict = dict(room)

            settings = self.get_system_settings()
            room_dict["threshold_w"] = float(settings.get("high_power_threshold_w", room_dict["threshold_w"]))
            room_dict["empty_threshold_w"] = float(settings.get("empty_room_threshold_w", room_dict["empty_threshold_w"]))

            # Fetch recent events for this room
            cursor.execute("SELECT * FROM room_events WHERE room_id = ? ORDER BY id DESC LIMIT 10", (room_id,))
            events = [dict(e) for e in cursor.fetchall()]

            room_dict["events"] = events
            return room_dict
        finally:
            conn.close()

    def get_command_center_stats(self):
        """Calculates primary stats and rooms requiring attention directly from SQLite."""
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            settings = self.get_system_settings()
            active_high_threshold = float(settings.get("high_power_threshold_w", 1200.0))
            active_empty_threshold = float(settings.get("empty_room_threshold_w", 35.0))

            # All rooms count
            cursor.execute("SELECT COUNT(*) FROM rooms")
            total_rooms = cursor.fetchone()[0]

            # Online rooms
            cursor.execute("SELECT COUNT(*) FROM rooms WHERE sensor_status = 'ONLINE'")
            rooms_online = cursor.fetchone()[0]

            # High consumption rooms (either room_state is HIGH_USAGE/TRIP_PENDING or power exceeds configured limit)
            cursor.execute("SELECT COUNT(*) FROM rooms WHERE room_state IN ('HIGH_USAGE', 'TRIP_PENDING') OR power_w > ?", (active_high_threshold,))
            rooms_high_usage = cursor.fetchone()[0]

            # Active anomaly alerts
            cursor.execute("SELECT COUNT(*) FROM rooms WHERE room_state IN ('ANOMALY_DETECTED', 'HIGH_USAGE', 'TRIP_PENDING', 'DATA_STALE') OR power_w > ?", (active_high_threshold,))
            active_anomalies = cursor.fetchone()[0]

            # Simulated power trips
            cursor.execute("SELECT COUNT(*) FROM rooms WHERE room_state = 'TRIPPED_SIMULATED' OR relay_state = 'TRIPPED_SIMULATED'")
            simulated_trips = cursor.fetchone()[0]

            # Total live power (W) across campus rooms
            cursor.execute("SELECT SUM(power_w) as total_w, SUM(energy_kwh) as total_kwh FROM rooms")
            p_row = cursor.fetchone()
            campus_live_watts = round(float(p_row["total_w"] or 0.0), 1)
            campus_energy_kwh = round(float(p_row["total_kwh"] or 0.0), 2)

            # Rooms requiring immediate attention
            cursor.execute("""
                SELECT * FROM rooms 
                WHERE room_state IN ('TRIPPED_SIMULATED', 'TRIP_PENDING', 'HIGH_USAGE', 'ANOMALY_DETECTED', 'DATA_STALE', 'SENSOR_OFFLINE')
                   OR power_w > ?
                ORDER BY 
                    CASE room_state 
                        WHEN 'TRIPPED_SIMULATED' THEN 1 
                        WHEN 'TRIP_PENDING' THEN 2 
                        WHEN 'HIGH_USAGE' THEN 3 
                        WHEN 'ANOMALY_DETECTED' THEN 4 
                        ELSE 5 
                    END,
                    power_w DESC
            """, (active_high_threshold,))
            attention_rows = [dict(r) for r in cursor.fetchall()]

            # Build clean explanation & next steps for each attention room
            attention_list = []
            for r in attention_rows:
                reason = r["trip_reason"]
                action = "Dispatch floor prefect to inspect room and check appliances."
                if r["room_state"] == "TRIPPED_SIMULATED":
                    action = "Inspect physical circuit, verify room safety, then perform manual simulation reset."
                    if not reason:
                        reason = f"Simulated auto-trip triggered: power exceeded applicable threshold for {r['persistence_minutes']} min."
                elif r["room_state"] == "TRIP_PENDING":
                    action = "Urgent: room is nearing persistence cutoff timeout. Check room immediately."
                    if not reason:
                        reason = f"Power at {r['power_w']} W exceeds limit ({active_high_threshold} W) for {r['persistence_minutes']} min."
                elif r["room_state"] == "SENSOR_OFFLINE":
                    reason = "Hardware node communication lost. Sensor offline."
                    action = "Verify corridor hub power and check ESP32 node connectivity."
                elif r["room_state"] == "DATA_STALE":
                    reason = "Telemetry timeout: no heartbeat received in > 30 minutes."
                    action = "Check wireless link and sensor heartbeat."
                elif not reason or "threshold" in reason or "limit" in reason:
                    reason = f"Observed {r['power_w']} W vs configured {active_high_threshold} W limit."

                attention_list.append({
                    "room_id": r["room_id"],
                    "block_id": r["block_id"],
                    "room_number": r["room_number"],
                    "power_w": r["power_w"],
                    "threshold_w": active_high_threshold,
                    "empty_threshold_w": active_empty_threshold,
                    "duration_minutes": r["persistence_minutes"],
                    "occupancy_state": r["occupancy_state"],
                    "room_state": r["room_state"] if (r["room_state"] != "NORMAL" or r["power_w"] <= active_high_threshold) else "HIGH_USAGE",
                    "relay_state": r["relay_state"],
                    "reason": reason,
                    "recommended_action": action
                })

            return {
                "total_rooms": total_rooms,
                "rooms_online": rooms_online,
                "rooms_high_usage": rooms_high_usage,
                "active_anomalies": active_anomalies,
                "simulated_trips": simulated_trips,
                "campus_live_watts": campus_live_watts,
                "campus_energy_kwh": campus_energy_kwh,
                "high_power_threshold_w": active_high_threshold,
                "empty_room_threshold_w": active_empty_threshold,
                "attention_rooms": attention_list
            }
        finally:
            conn.close()

    def reset_room_trip(self, room_id, operator="Hostel Warden"):
        """
        Resets an isolated simulated room trip.
        Changes ONLY the selected room. Leaves all other rooms untouched.
        Prevents resetting non-tripped rooms needlessly.
        """
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM rooms WHERE room_id = ?", (room_id,))
            room = cursor.fetchone()
            if not room:
                return {"success": False, "error": f"Room {room_id} not found."}

            # Safe reset baseline power
            occ = room["occupancy_state"]
            reset_power = 65.0 if occ == "Occupied" else 20.0
            reset_current = round(reset_power / 230.0, 2)
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # Update ONLY this room in SQLite
            cursor.execute("""
                UPDATE rooms
                SET room_state = 'NORMAL',
                    relay_state = 'CLOSED',
                    power_w = ?,
                    current_a = ?,
                    persistence_minutes = 0,
                    trip_reason = '',
                    last_update = ?
                WHERE room_id = ?
            """, (reset_power, reset_current, timestamp, room_id))

            # Log reset event in SQLite with collision-proof unique event_id
            event_id = f"EVT-RESET-{room_id.replace('-', '')}-{datetime.now().strftime('%Y%m%d%H%M%S%f')[:17]}-{uuid.uuid4().hex[:6]}"
            cursor.execute("""
                INSERT INTO room_events (
                    event_id, room_id, block_id, room_number, event_type,
                    observed_power_w, threshold_w, duration_minutes,
                    occupancy_state, explanation, action_taken, outcome, simulated
                ) VALUES (?, ?, ?, ?, 'RESET', ?, ?, 0, ?, ?, ?, 'Restored to Normal', 1)
            """, (
                event_id, room_id, room["block_id"], room["room_number"],
                reset_power, room["threshold_w"], occ,
                f"Manual simulation reset performed by {operator}. Room relay state restored to CLOSED.",
                f"Simulated power restored by {operator}."
            ))

            conn.commit()
            return {
                "success": True,
                "room_id": room_id,
                "new_state": "NORMAL",
                "new_relay_state": "CLOSED",
                "message": f"Room {room_id} simulated power cutoff successfully reset to NORMAL. Other rooms remain unaffected."
            }
        finally:
            conn.close()

    def trigger_nilm_scenario(self, scenario_id, target_room_id=None, fast_forward=True):
        """
        Executes one of the 10 NILM fault / trip simulation scenarios.
        Updates ONLY the targeted room in SQLite and logs the event.
        """
        conn = get_db_connection()
        try:
            return self._execute_nilm_scenario(conn, scenario_id, target_room_id, fast_forward)
        finally:
            conn.close()

    def _execute_nilm_scenario(self, conn, scenario_id, target_room_id=None, fast_forward=True):
        cursor = conn.cursor()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Defaults based on scenario_id
        if scenario_id == 1:
            # 1. Normal fan switching (Room A-102)
            rid = target_room_id or "A-102"
            cursor.execute("""
                UPDATE rooms
                SET power_w = 60.0, current_a = 0.28, voltage_v = 230.2, power_factor = 0.94,
                    occupancy_state = 'Occupied', sensor_status = 'ONLINE', room_state = 'NORMAL',
                    relay_state = 'CLOSED', trip_reason = 'Normal fan speed regulation (60W).',
                    persistence_minutes = 0, last_update = ?
                WHERE room_id = ?
            """, (timestamp, rid))
            msg = f"Room {rid}: Normal ceiling fan speed stepped to 60W. Normal baseline power."
            evt_type = "NORMAL"

        elif scenario_id == 2:
            # 2. Unusual fan-like power step (Room A-103)
            rid = target_room_id or "A-103"
            cursor.execute("""
                UPDATE rooms
                SET power_w = 135.0, current_a = 0.62, voltage_v = 229.8, power_factor = 0.91,
                    occupancy_state = 'Occupied', sensor_status = 'ONLINE', room_state = 'ANOMALY_DETECTED',
                    trip_reason = 'NILM Step Anomaly: Fan load unexpectedly high (135W vs 60W rated). Possible mechanical bearing drag or faulty run capacitor.',
                    persistence_minutes = 14, last_update = ?
                WHERE room_id = ?
            """, (timestamp, rid))
            msg = f"Room {rid}: Step anomaly detected: Fan drawing 135W (+75W abnormal step). Suspected bearing friction."
            evt_type = "ANOMALY_DETECTED"

        elif scenario_id == 3:
            # 3. Continuous geyser-like high-power load (Room C-201)
            rid = target_room_id or "C-201"
            dur = 55 if fast_forward else 15
            cursor.execute("""
                UPDATE rooms
                SET power_w = 2050.0, current_a = 9.15, voltage_v = 226.5, power_factor = 1.0,
                    occupancy_state = 'Likely Vacant', sensor_status = 'ONLINE', room_state = 'ANOMALY_DETECTED',
                    trip_reason = 'Continuous 2050W geyser load active for > 45 minutes. Welded relay contactor suspected.',
                    persistence_minutes = ?, last_update = ?
                WHERE room_id = ?
            """, (dur, timestamp, rid))
            msg = f"Room {rid}: Continuous geyser load active for {dur} minutes. Anomaly alert triggered."
            evt_type = "ANOMALY_DETECTED"

        elif scenario_id == 4:
            # 4. High-power appliance spike above threshold (Room B-105)
            rid = target_room_id or "B-105"
            settings = self.get_system_settings()
            configured_limit = float(settings.get("high_power_threshold_w", 1200.0))
            cursor.execute("""
                UPDATE rooms
                SET power_w = 1850.0, current_a = 8.12, voltage_v = 227.4, power_factor = 0.99,
                    occupancy_state = 'Occupied', sensor_status = 'ONLINE', room_state = 'HIGH_USAGE',
                    trip_reason = 'Abrupt appliance spike: 1850W draw exceeds ' || ROUND(?, 0) || 'W room limit. Unauthorized induction cooker or iron suspected.',
                    persistence_minutes = 8, last_update = ?
                WHERE room_id = ?
            """, (configured_limit, timestamp, rid))
            msg = f"Room {rid}: High power spike of 1850W (> {int(configured_limit)}W threshold) detected."
            evt_type = "HIGH_USAGE"

        elif scenario_id == 5:
            # 5. Room likely vacant with continued consumption (Room A-101) -> AUTO-TRIP SIMULATION!
            rid = target_room_id or "A-101"
            settings = self.get_system_settings()
            vacant_limit = float(settings.get("empty_room_threshold_w", 35.0))
            p_win = int(float(settings.get("persistence_window_min", 15)))
            dur = (p_win + 3) if fast_forward else 5
            cursor.execute("""
                UPDATE rooms
                SET power_w = 280.0, current_a = 1.25, voltage_v = 230.0, power_factor = 0.97,
                    occupancy_state = 'Likely Vacant', sensor_status = 'ONLINE', room_state = 'TRIPPED_SIMULATED',
                    relay_state = 'TRIPPED_SIMULATED',
                    trip_reason = 'Simulated Auto-Trip: Room vacant during daytime with 280W load persistent > ' || ? || ' minutes (standby limit ' || ROUND(?, 0) || 'W). Cutoff relay opened (SIMULATION ONLY).',
                    persistence_minutes = ?, last_update = ?
                WHERE room_id = ?
            """, (p_win, vacant_limit, dur, timestamp, rid))
            msg = f"Room {rid}: Simulated auto-trip triggered! 280W draw in vacant room exceeded {p_win}-min persistence window."
            evt_type = "TRIP_SIMULATED"

        elif scenario_id == 6:
            # 6. Occupied room with normal consumption (Room D-104)
            rid = target_room_id or "D-104"
            cursor.execute("""
                UPDATE rooms
                SET power_w = 110.0, current_a = 0.49, voltage_v = 230.1, power_factor = 0.95,
                    occupancy_state = 'Occupied', sensor_status = 'ONLINE', room_state = 'NORMAL',
                    relay_state = 'CLOSED', trip_reason = 'Normal daytime occupancy: laptop and desk lamp.',
                    persistence_minutes = 0, last_update = ?
                WHERE room_id = ?
            """, (timestamp, rid))
            msg = f"Room {rid}: Normal verified operating state (110W, Occupied)."
            evt_type = "NORMAL"

        elif scenario_id == 7:
            # 7. Sensor disconnected (Room B-204)
            rid = target_room_id or "B-204"
            cursor.execute("""
                UPDATE rooms
                SET sensor_status = 'OFFLINE', room_state = 'SENSOR_OFFLINE',
                    power_w = 0.0, current_a = 0.0, voltage_v = 0.0,
                    trip_reason = 'Sensor telemetry link disconnected. Node communication lost.',
                    last_update = ?
                WHERE room_id = ?
            """, (timestamp, rid))
            msg = f"Room {rid}: Sensor disconnected. Sensor offline alert generated."
            evt_type = "SENSOR_FAULT"

        elif scenario_id == 8:
            # 8. Stale telemetry (Room C-102)
            rid = target_room_id or "C-102"
            old_time = (datetime.now() - timedelta(minutes=45)).strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute("""
                UPDATE rooms
                SET sensor_status = 'STALE', room_state = 'DATA_STALE',
                    trip_reason = 'Telemetry heartbeat timeout (> 35 min). Data marked stale.',
                    last_update = ?
                WHERE room_id = ?
            """, (old_time, rid))
            msg = f"Room {rid}: Telemetry heartbeat delayed by > 35 minutes. Stale data warning issued."
            evt_type = "DATA_STALE"

        elif scenario_id == 9:
            # 9. Repeated anomaly matching verified incident (Room A-204)
            rid = target_room_id or "A-204"
            cursor.execute("""
                UPDATE rooms
                SET power_w = 1520.0, current_a = 6.65, voltage_v = 228.5, power_factor = 0.99,
                    occupancy_state = 'Likely Vacant', sensor_status = 'ONLINE', room_state = 'TRIP_PENDING',
                    trip_reason = 'High 1520W heater signature matching Incident #1 in memory. Trip pending in 3 minutes.',
                    persistence_minutes = 12, last_update = ?
                WHERE room_id = ?
            """, (timestamp, rid))
            msg = f"Room {rid}: Anomaly matched historical Incident #1 (Unattended 1500W room heater). Trip pending."
            evt_type = "WARNING"

        elif scenario_id == 10:
            # 10. Reset all simulated scenarios back to clean benchmark
            cursor.execute("""
                UPDATE rooms
                SET room_state = 'NORMAL', relay_state = 'CLOSED', sensor_status = 'ONLINE',
                    trip_reason = '', persistence_minutes = 0, last_update = ?
                WHERE room_id NOT IN ('A-101', 'D-205')
            """, (timestamp,))
            msg = "All room simulation test states have been reset to benchmark."
            evt_type = "RESET"
            rid = "ALL"

        # Log event to SQLite if single room affected
        if scenario_id != 10:
            cursor.execute("SELECT block_id, room_number, power_w, threshold_w, occupancy_state FROM rooms WHERE room_id = ?", (rid,))
            r_info = cursor.fetchone()
            if r_info:
                event_id = f"EVT-NILM-{rid.replace('-', '')}-{datetime.now().strftime('%Y%m%d%H%M%S%f')[:17]}-{uuid.uuid4().hex[:6]}"
                cursor.execute("""
                    INSERT INTO room_events (
                        event_id, room_id, block_id, room_number, event_type,
                        observed_power_w, threshold_w, duration_minutes,
                        occupancy_state, explanation, action_taken, outcome, simulated
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, 'Simulated', 1)
                """, (
                    event_id, rid, r_info["block_id"], r_info["room_number"], evt_type,
                    r_info["power_w"], r_info["threshold_w"], r_info["occupancy_state"],
                    msg, f"NILM Scenario #{scenario_id} triggered."
                ))

            conn.commit()
            return {
                "success": True,
                "scenario_id": scenario_id,
                "affected_room_id": rid,
                "event_type": evt_type,
                "message": msg
            }

    def get_trip_events(self, room_id=None, limit=50):
        """Retrieves history of simulated trip, reset, and anomaly events."""
        conn = get_db_connection()
        cursor = conn.cursor()
        query = "SELECT * FROM room_events WHERE 1=1"
        params = []
        if room_id and room_id != "all":
            query += " AND room_id = ?"
            params.append(room_id)
        query += " ORDER BY id DESC LIMIT ?"
        params.append(limit)

        cursor.execute(query, params)
        rows = [dict(r) for r in cursor.fetchall()]
        conn.close()
        return rows

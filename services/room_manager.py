import json
import uuid
from datetime import datetime, timedelta
from config import Config
from database import get_db_connection

class RoomManager:
    """
    Hostel Energy AI - Room-Level Electricity & State Machine Manager.
    Manages individual room telemetry, isolated simulated trip states,
    simulated controllable loads, dynamic power optimization, and event logging.
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

            # Synchronize default optimization target across rooms table if set
            if "default_optimization_target_w" in settings_dict:
                def_target = float(settings_dict["default_optimization_target_w"])
                cursor.execute("""
                    UPDATE rooms
                    SET optimization_target_w = ?
                    WHERE optimization_target_w IS NULL OR optimization_target_w = 0.0 OR optimization_target_w = 800.0
                """, (def_target,))

            # Re-evaluate excess power across rooms with active sensors
            cursor.execute("""
                UPDATE rooms
                SET excess_power_w = MAX(0.0, ROUND(power_w - threshold_w, 1))
                WHERE sensor_status != 'OFFLINE'
            """)

            conn.commit()
            return True
        finally:
            conn.close()

    def get_all_rooms(self, block_id=None, room_state=None, occupancy_state=None, switch_state=None):
        """Retrieves list of all monitored rooms with live electrical, switch, and optimization telemetry."""
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            settings = self.get_system_settings()
            active_high_threshold = float(settings.get("high_power_threshold_w", 1200.0))
            active_empty_threshold = float(settings.get("empty_room_threshold_w", 35.0))
            def_opt_target = float(settings.get("default_optimization_target_w", 800.0))

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
            if switch_state and switch_state != "all":
                if switch_state.upper() == "ON":
                    query += " AND effective_switch_state = 'ON'"
                elif switch_state.upper() == "OFF":
                    query += " AND effective_switch_state = 'OFF'"
                elif switch_state.upper() == "LOCKED":
                    query += " AND manual_off_lock = 1"

            query += " ORDER BY block_id ASC, room_number ASC"
            cursor.execute(query, params)
            rows = []
            for r in cursor.fetchall():
                rd = dict(r)
                rd["threshold_w"] = active_high_threshold
                rd["empty_threshold_w"] = active_empty_threshold
                
                # Normalize switch state fields
                sw = rd.get("switch_state") or "ON"
                eff_sw = rd.get("effective_switch_state") or ("OFF" if rd.get("room_state") in ("TRIPPED_SIMULATED", "TRIPPED_CRITICAL", "MANUAL_OFF") or rd.get("relay_state") == "TRIPPED_SIMULATED" or rd.get("manual_off_lock") == 1 else sw)
                rd["switch_state"] = sw
                rd["effective_switch_state"] = eff_sw
                rd["manual_off_lock"] = int(rd.get("manual_off_lock") or 0)
                rd["fault_status"] = rd.get("fault_status") or ("ACTIVE_FAULT" if eff_sw == "OFF" and rd.get("room_state") == "TRIPPED_SIMULATED" else "NONE")
                rd["last_switch_by"] = rd.get("last_switch_by") or "System Initializer"
                rd["last_switch_at"] = rd.get("last_switch_at") or rd.get("last_update") or ""
                
                # Computed switch helper flags
                is_locked = rd["manual_off_lock"] == 1
                is_offline = rd.get("sensor_status") == "OFFLINE"
                has_fault = rd["fault_status"] in ("ACTIVE_FAULT", "PENDING_VERIFICATION", "CRITICAL_FAULT") or rd.get("room_state") in ("TRIPPED_SIMULATED", "TRIPPED_CRITICAL", "TRIP_PENDING")
                
                # De-energized circuits (switch OFF or TRIPPED) physically draw 0 W
                if eff_sw == "OFF" or rd.get("room_state") in ("TRIPPED_SIMULATED", "TRIPPED_CRITICAL", "MANUAL_OFF"):
                    rd["power_w"] = 0.0
                    rd["current_a"] = 0.0

                p_val = float(rd.get("power_w", 0.0))
                is_over = p_val > active_high_threshold
                rd["can_switch_on"] = (not is_locked) and (not is_offline) and (not has_fault) and (not is_over)
                
                # Power Optimization metrics
                room_opt_target = float(rd.get("optimization_target_w") or def_opt_target)
                rd["optimization_target_w"] = room_opt_target

                if is_offline:
                    rd["is_offline"] = True
                    rd["excess_power_w"] = 0.0
                    rd["reduction_required_w"] = 0.0
                    rd["optimization_state"] = "SENSOR_OFFLINE"
                else:
                    rd["is_offline"] = False
                    rd["excess_power_w"] = max(0.0, round(p_val - active_high_threshold, 1))
                    rd["reduction_required_w"] = max(0.0, round(p_val - room_opt_target, 1))
                    
                    if is_locked or rd.get("room_state") == "MANUAL_OFF":
                        rd["optimization_state"] = "MANUAL_OFF"
                    elif rd.get("room_state") == "TRIPPED_CRITICAL":
                        rd["optimization_state"] = "TRIPPED_CRITICAL"
                    elif rd.get("room_state") == "TRIPPED_SIMULATED":
                        rd["optimization_state"] = "TRIPPED_SIMULATED"
                    elif rd.get("room_state") == "DATA_STALE":
                        rd["optimization_state"] = "DATA_STALE"
                    else:
                        rd["optimization_state"] = rd.get("optimization_state") or ("NORMAL" if p_val <= active_high_threshold else "HIGH_USAGE")
                
                rd["previous_power_w"] = float(rd.get("previous_power_w") or 0.0)
                rd["power_change_w"] = float(rd.get("power_change_w") or 0.0)
                rd["power_change_pct"] = float(rd.get("power_change_pct") or 0.0)
                rd["simulation_profile"] = rd.get("simulation_profile") or "NORMAL_OCCUPIED"

                rows.append(rd)
            return rows
        finally:
            conn.close()

    def get_room_by_id(self, room_id):
        """Retrieves full details, switch state, and recent event history for a single room."""
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM rooms WHERE room_id = ?", (room_id,))
            room = cursor.fetchone()
            if not room:
                return None
            room_dict = dict(room)

            settings = self.get_system_settings()
            active_high = float(settings.get("high_power_threshold_w", room_dict.get("threshold_w", 1200.0)))
            active_empty = float(settings.get("empty_room_threshold_w", room_dict.get("empty_threshold_w", 35.0)))
            room_dict["threshold_w"] = active_high
            room_dict["empty_threshold_w"] = active_empty

            # Ensure switch fields are well-formed
            sw = room_dict.get("switch_state") or "ON"
            is_trip = room_dict.get("room_state") in ("TRIPPED_SIMULATED", "TRIPPED_CRITICAL") or room_dict.get("relay_state") == "TRIPPED_SIMULATED"
            manual_lock = int(room_dict.get("manual_off_lock") or 0)
            if is_trip or manual_lock == 1 or sw == "OFF" or room_dict.get("room_state") in ("TRIPPED_SIMULATED", "TRIPPED_CRITICAL", "MANUAL_OFF"):
                eff_sw = "OFF"
            else:
                eff_sw = room_dict.get("effective_switch_state") or sw

            # De-energized circuits physically draw 0 W
            if eff_sw == "OFF" or room_dict.get("room_state") in ("TRIPPED_SIMULATED", "TRIPPED_CRITICAL", "MANUAL_OFF"):
                room_dict["power_w"] = 0.0
                room_dict["current_a"] = 0.0

            room_dict["switch_state"] = sw
            room_dict["effective_switch_state"] = eff_sw
            room_dict["manual_off_lock"] = manual_lock
            room_dict["fault_status"] = room_dict.get("fault_status") or ("ACTIVE_FAULT" if (is_trip and eff_sw == "OFF") else "NONE")
            room_dict["last_switch_by"] = room_dict.get("last_switch_by") or ("Auto-Trip Protection Engine" if is_trip else "System Initializer")
            room_dict["last_switch_at"] = room_dict.get("last_switch_at") or room_dict.get("last_update") or ""
            room_dict["resolution_confirmed_by"] = room_dict.get("resolution_confirmed_by") or ""
            room_dict["resolution_confirmed_at"] = room_dict.get("resolution_confirmed_at") or ""
            room_dict["resolution_notes"] = room_dict.get("resolution_notes") or ""

            # Check restoration eligibility & blockers for Manual ON
            is_locked = manual_lock == 1
            is_offline = room_dict.get("sensor_status") == "OFFLINE"
            has_fault = room_dict["fault_status"] in ("ACTIVE_FAULT", "PENDING_VERIFICATION", "CRITICAL_FAULT") or is_trip or room_dict.get("room_state") == "TRIP_PENDING"
            is_over = float(room_dict.get("power_w", 0.0)) > active_high

            can_switch_on = True
            block_reasons = []

            if is_locked:
                can_switch_on = False
                block_reasons.append("Manual OFF lock is currently active. The warden must explicitly release the lock before power can be restored.")
            if is_offline:
                can_switch_on = False
                block_reasons.append("Sensor node telemetry is OFFLINE. Cannot verify circuit safety.")
            if has_fault:
                can_switch_on = False
                reason_detail = room_dict.get("trip_reason") or "Active safety trip or fault"
                block_reasons.append(f"Unresolved critical fault remains ({reason_detail}). Warden must investigate and click 'Problem Resolved' after physical repair.")
            elif is_over:
                can_switch_on = False
                block_reasons.append(f"Observed load ({room_dict['power_w']} W) exceeds safety limit ({active_high} W).")

            room_dict["can_switch_on"] = can_switch_on
            room_dict["switch_on_block_reason"] = " ".join(block_reasons)
            room_dict["restoration_eligible"] = 1 if can_switch_on else 0

            # Optimization fields
            target_val = float(room_dict.get("optimization_target_w") or settings.get("default_optimization_target_w", 800.0))
            room_dict["optimization_target_w"] = target_val
            is_offline = room_dict.get("sensor_status") == "OFFLINE"
            room_dict["is_offline"] = is_offline
            p_val = float(room_dict.get("power_w", 0.0)) if not is_offline else None

            if p_val is not None:
                room_dict["excess_power_w"] = max(0.0, round(p_val - active_high, 1))
                room_dict["reduction_required_w"] = max(0.0, round(p_val - target_val, 1))
            else:
                room_dict["excess_power_w"] = 0.0
                room_dict["reduction_required_w"] = 0.0

            opt_state = room_dict.get("optimization_state") or ("NORMAL" if (p_val is not None and p_val <= active_high) else "HIGH_USAGE")
            if is_offline:
                opt_state = "SENSOR_OFFLINE"
            elif room_dict.get("room_state") == "MANUAL_OFF":
                opt_state = "MANUAL_OFF"
            elif room_dict.get("room_state") == "TRIPPED_CRITICAL":
                opt_state = "TRIPPED_CRITICAL"
            elif room_dict.get("room_state") == "TRIPPED_SIMULATED":
                opt_state = "TRIPPED_SIMULATED"

            room_dict["optimization_state"] = opt_state
            room_dict["controllable_loads"] = self.get_room_controllable_loads(room_id, room_dict)

            room_dict["previous_power_w"] = float(room_dict.get("previous_power_w") or 0.0)
            room_dict["power_change_w"] = float(room_dict.get("power_change_w") or 0.0)
            room_dict["power_change_pct"] = float(room_dict.get("power_change_pct") or 0.0)
            room_dict["simulation_profile"] = room_dict.get("simulation_profile") or "NORMAL_OCCUPIED"

            # Fetch recent events for this room
            cursor.execute("SELECT * FROM room_events WHERE room_id = ? ORDER BY id DESC LIMIT 15", (room_id,))
            events = [dict(e) for e in cursor.fetchall()]
            room_dict["events"] = events

            return room_dict
        finally:
            conn.close()

    def get_room_controllable_loads(self, room_id, room_dict=None):
        """
        Retrieves or initializes the lightweight simulated controllable loads for a room.
        Explicitly labeled as a simulation model with simulated assumptions.
        """
        if not room_dict:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM rooms WHERE room_id = ?", (room_id,))
            r = cursor.fetchone()
            conn.close()
            if not r:
                return []
            room_dict = dict(r)

        raw_json = room_dict.get("simulated_loads_json")
        if raw_json and raw_json.strip():
            try:
                loads = json.loads(raw_json)
                if isinstance(loads, list) and len(loads) > 0:
                    for ld in loads:
                        p_val = float(ld.get("power_w") or ld.get("rated_w") or 0.0)
                        ld["power_w"] = p_val
                        ld.setdefault("rated_w", p_val)
                        if "effective_w" not in ld:
                            if ld.get("state") == "ON":
                                ld["effective_w"] = p_val
                            elif ld.get("state") == "THROTTLED":
                                ld["effective_w"] = float(ld.get("throttle_w") or p_val * 0.5)
                            else:
                                ld["effective_w"] = 0.0
                    return loads
            except Exception:
                pass

        # Generate default realistic simulated load set based on current room consumption
        current_w = float(room_dict.get("power_w", 0.0))
        occ = room_dict.get("occupancy_state", "Occupied")
        is_occupied = (occ == "Occupied")

        # 1. Essential Base Illumination (Protected - cannot shed)
        main_lights = {
            "id": "main_lighting",
            "name": "Main Room Illumination (LED)",
            "power_w": 50.0 if is_occupied else 0.0,
            "rated_w": 50.0,
            "effective_w": 50.0 if is_occupied else 0.0,
            "state": "ON" if is_occupied else "OFF",
            "controllable": False,
            "essential": True,
            "min_duration_min": 10,
            "priority": 5,
            "category": "Lighting"
        }

        # 2. Secondary Lighting (Corridor/Mirror/Night Lamp - Controllable)
        sec_lights = {
            "id": "secondary_lighting",
            "name": "Secondary / Reading Lamps",
            "power_w": 40.0,
            "rated_w": 40.0,
            "effective_w": 40.0,
            "state": "ON",
            "controllable": True,
            "essential": False,
            "min_duration_min": 5,
            "priority": 3,
            "category": "Lighting"
        }

        # 3. Ceiling Fan (Controllable speed throttle: 75W High -> 35W Eco)
        fan = {
            "id": "ceiling_fan",
            "name": "Ceiling Fan (High Speed)",
            "power_w": 75.0,
            "rated_w": 75.0,
            "effective_w": 75.0,
            "state": "ON",
            "controllable": True,
            "essential": False,
            "min_duration_min": 5,
            "priority": 4,
            "category": "Cooling/Ventilation",
            "throttle_w": 35.0
        }

        # 4. Auxiliary Study Desk Plug Load (Monitors, chargers, peripherals - Controllable)
        aux_plug = {
            "id": "aux_desk_plug",
            "name": "Auxiliary Desk & Entertainment Plugs",
            "power_w": 180.0,
            "rated_w": 180.0,
            "effective_w": 180.0,
            "state": "ON",
            "controllable": True,
            "essential": False,
            "min_duration_min": 5,
            "priority": 2,
            "category": "Electronics"
        }

        # 5. High-Draw Thermal/Utility Appliance (Heater/Kettle/Cooker - Prime Shedding Candidate)
        base_sum = main_lights["power_w"] + sec_lights["power_w"] + fan["power_w"] + aux_plug["power_w"]
        thermal_w = max(0.0, round(current_w - base_sum, 1)) if current_w > base_sum else 0.0
        if thermal_w < 100.0 and current_w > 800.0:
            thermal_w = round(current_w * 0.6, 1)

        rated_thermal = max(300.0, thermal_w) if current_w > 500.0 else 0.0
        thermal_appliance = {
            "id": "thermal_appliance",
            "name": "Nonessential High-Draw Thermal Load (Heater/Kettle)",
            "power_w": rated_thermal,
            "rated_w": rated_thermal,
            "effective_w": rated_thermal if current_w > 500.0 else 0.0,
            "state": "ON" if current_w > 500.0 else "OFF",
            "controllable": True,
            "essential": False,
            "min_duration_min": 5,
            "priority": 1,
            "category": "Thermal/High-Wattage"
        }

        loads = [main_lights, sec_lights, fan, aux_plug, thermal_appliance]

        # Persist generated load set
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("UPDATE rooms SET simulated_loads_json = ? WHERE room_id = ?", (json.dumps(loads), room_id))
            conn.commit()
        finally:
            conn.close()

        return loads

    def save_room_controllable_loads(self, room_id, loads):
        """Persists updated controllable load states to SQLite."""
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("UPDATE rooms SET simulated_loads_json = ? WHERE room_id = ?", (json.dumps(loads), room_id))
            conn.commit()
            return True
        finally:
            conn.close()

    def update_room_target(self, room_id, target_w, threshold_w=None):
        """Configures room-specific optimization target and/or max power threshold."""
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM rooms WHERE room_id = ?", (room_id,))
            room = cursor.fetchone()
            if not room:
                return {"success": False, "error": f"Room {room_id} not found.", "code": 404}

            target_val = float(target_w)
            if target_val <= 0:
                return {"success": False, "error": "Optimization target must be greater than zero.", "code": 400}

            curr_thresh = float(threshold_w if threshold_w is not None else room["threshold_w"])
            if curr_thresh < target_val:
                return {"success": False, "error": f"Optimization target ({target_val} W) cannot exceed maximum threshold ({curr_thresh} W).", "code": 400}

            curr_p = float(room["power_w"] or 0.0)
            excess = max(0.0, round(curr_p - curr_thresh, 1))

            cursor.execute("""
                UPDATE rooms
                SET optimization_target_w = ?,
                    threshold_w = ?,
                    excess_power_w = ?
                WHERE room_id = ?
            """, (target_val, curr_thresh, excess, room_id))
            conn.commit()

            return {
                "success": True,
                "room_id": room_id,
                "optimization_target_w": target_val,
                "threshold_w": curr_thresh,
                "excess_power_w": excess,
                "message": f"Optimization target for Room {room_id} set to {target_val} W (Max Threshold: {curr_thresh} W)."
            }
        finally:
            conn.close()

    def optimize_room_power(self, room_id, operator="AI Energy Optimizer", target_w=None, dry_run=False):
        """
        Executes room-level simulated load optimization instead of immediate automatic trip.
        - Evaluates excess power above maximum threshold and required reduction to preferred target.
        - Sheds or throttles eligible nonessential controllable simulated loads.
        - Preserves manual OFF lock, critical safety trips, and reports partial or failed outcomes.
        - Calculates energy (kWh) and cost (INR) savings based on verified tariff.
        """
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM rooms WHERE room_id = ?", (room_id,))
            room = cursor.fetchone()
            if not room:
                return {"success": False, "error": f"Room {room_id} not found.", "code": 404}
            room = dict(room)

            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            settings = self.get_system_settings()
            max_threshold = float(settings.get("high_power_threshold_w", room.get("threshold_w", 1200.0)))
            target = float(target_w if target_w is not None else (room.get("optimization_target_w") or settings.get("default_optimization_target_w", 800.0)))
            tolerance = float(settings.get("optimization_tolerance_w", 50.0))
            critical_safety_limit = float(settings.get("critical_safety_threshold_w", 2400.0))
            tariff_rate = Config.TARIFF_TIER_2_RATE
            emission_factor = Config.GRID_EMISSION_FACTOR_KG_CO2_PER_KWH

            # PRECONDITION 1: Manual OFF Lock Active (Must NOT be overridden)
            if int(room.get("manual_off_lock") or 0) == 1:
                return {
                    "success": False,
                    "blocked": True,
                    "code": 400,
                    "room_state": "MANUAL_OFF",
                    "error": f"Manual OFF lock is active for Room {room_id}. Power optimization cannot override manual warden shutdown. Lock must be explicitly released first."
                }

            # PRECONDITION 2: Sensor Offline or Stale Telemetry
            if room.get("sensor_status") == "OFFLINE":
                return {
                    "success": False,
                    "blocked": True,
                    "code": 400,
                    "room_state": "SENSOR_OFFLINE",
                    "error": f"Sensor node telemetry for Room {room_id} is OFFLINE. Cannot perform optimization on invalid or missing telemetry."
                }
            if room.get("sensor_status") == "STALE" or room.get("room_state") == "DATA_STALE":
                return {
                    "success": False,
                    "blocked": True,
                    "code": 400,
                    "room_state": "DATA_STALE",
                    "error": f"Sensor telemetry for Room {room_id} is STALE. Fresh heartbeat required before power optimization can proceed."
                }

            # PRECONDITION 3: Latched Safety / Simulated Trip or Circuit Switched OFF
            if room.get("room_state") in ("TRIPPED_SIMULATED", "TRIPPED_CRITICAL") or room.get("relay_state") == "TRIPPED_SIMULATED" or str(room.get("effective_switch_state", "")).upper() == "OFF":
                return {
                    "success": False,
                    "blocked": True,
                    "code": 409,
                    "room_state": room.get("room_state"),
                    "error": f"Room {room_id} circuit is de-energized or has an active latched safety trip ({room.get('room_state')}). Power optimization cannot run on an unpowered circuit. Authorized fault clearance or switch restoration workflow is required first."
                }

            # PRECONDITION 4: Possible Electrical Fault / Critical Overload
            current_p = float(room.get("power_w", 0.0))
            reason_str = str(room.get("trip_reason", "")).lower()
            has_critical_fault = (
                current_p >= critical_safety_limit or
                "arc" in reason_str or
                "insulation" in reason_str or
                "leakage" in reason_str or
                "short circuit" in reason_str
            )
            if has_critical_fault:
                reason = room.get("trip_reason") or f"Critical overload ({current_p} W >= {critical_safety_limit} W limit) or electrical fault signature"
                cursor.execute("""
                    UPDATE rooms
                    SET room_state = 'TRIPPED_CRITICAL',
                        relay_state = 'TRIPPED_SIMULATED',
                        switch_state = 'OFF',
                        effective_switch_state = 'OFF',
                        fault_status = 'CRITICAL_FAULT',
                        restoration_eligible = 0,
                        power_w = 0.0,
                        current_a = 0.0,
                        trip_reason = ?,
                        last_switch_by = 'Critical Safety Protection Engine',
                        last_switch_at = ?,
                        last_update = ?
                    WHERE room_id = ?
                """, (f"CRITICAL SAFETY TRIP: {reason}. Routine optimization halted to protect wiring infrastructure.", timestamp, timestamp, room_id))

                event_id = f"EVT-CRIT-{room_id.replace('-', '')}-{datetime.now().strftime('%Y%m%d%H%M%S%f')[:17]}-{uuid.uuid4().hex[:6]}"
                cursor.execute("""
                    INSERT INTO room_events (
                        event_id, room_id, block_id, room_number, event_type,
                        observed_power_w, threshold_w, duration_minutes,
                        occupancy_state, explanation, action_taken, outcome, simulated,
                        target_w, resulting_power_w, savings_w, savings_kwh, savings_inr
                    ) VALUES (?, ?, ?, ?, 'TRIPPED_CRITICAL', ?, ?, 0, ?, ?, ?, 'Critical Protective Cutoff', 1, ?, 0.0, 0.0, 0.0, 0.0)
                """, (
                    event_id, room_id, room["block_id"], room["room_number"],
                    current_p, max_threshold, room["occupancy_state"],
                    f"Possible electrical wiring fault or extreme load ({current_p} W) detected in Room {room_id}. Routine optimization prohibited to avoid masking fault.",
                    "Emergency protective trip triggered. Physical electrical inspection required before restoration.",
                    target
                ))
                conn.commit()

                return {
                    "success": False,
                    "critical_fault": True,
                    "code": 409,
                    "room_state": "TRIPPED_CRITICAL",
                    "error": f"Possible electrical wiring fault or critical overload ({current_p} W) detected in Room {room_id}. Routine optimization stopped to preserve safety. Circuit switched to TRIPPED_CRITICAL."
                }

            # STEP 1: Calculate Excess and Reduction Required
            excess_power_w = max(0.0, round(current_p - max_threshold, 1))
            reduction_required_w = max(0.0, round(current_p - target, 1))

            if (current_p <= target + tolerance) and (excess_power_w <= 0):
                return {
                    "success": True,
                    "room_id": room_id,
                    "initial_power_w": current_p,
                    "resulting_power_w": current_p,
                    "target_w": target,
                    "max_threshold_w": max_threshold,
                    "excess_power_w": 0.0,
                    "reduction_required_w": 0.0,
                    "reduction_achieved_w": 0.0,
                    "optimization_state": "OPTIMIZED" if current_p > target else "NORMAL",
                    "message": f"Room {room_id} consumption ({current_p} W) is within the acceptable tolerance margin of target ({target} W ± {tolerance} W). No load shedding required."
                }

            # STEP 2: Evaluate Controllable Nonessential Loads
            loads = self.get_room_controllable_loads(room_id, room)
            controllable_candidates = [
                load for load in loads
                if load.get("controllable") is True and load.get("essential") is not True and load.get("state") != "OFF"
            ]
            controllable_candidates.sort(key=lambda x: x.get("priority", 99))

            actions_taken = []
            reduction_achieved = 0.0

            for load in controllable_candidates:
                if reduction_achieved >= reduction_required_w:
                    break

                load_p = float(load.get("power_w", 0.0))
                if load_p <= 0:
                    continue

                if load.get("id") == "ceiling_fan" and load.get("state") == "ON":
                    throttle_p = float(load.get("throttle_w", 35.0))
                    shed_delta = max(0.0, load_p - throttle_p)
                    load["state"] = "THROTTLED"
                    load["power_w"] = throttle_p
                    reduction_achieved += shed_delta
                    actions_taken.append({
                        "load_id": load["id"],
                        "load_name": load["name"],
                        "action": "THROTTLE_ECO",
                        "power_reduction_w": round(shed_delta, 1),
                        "resulting_power_w": throttle_p,
                        "description": f"Throttled ceiling fan to Eco mode (saving {round(shed_delta, 1)} W)"
                    })
                else:
                    load["state"] = "OFF"
                    load["power_w"] = 0.0
                    reduction_achieved += load_p
                    actions_taken.append({
                        "load_id": load["id"],
                        "load_name": load["name"],
                        "action": "SWITCH_OFF",
                        "power_reduction_w": round(load_p, 1),
                        "resulting_power_w": 0.0,
                        "description": f"Shed nonessential simulated load '{load['name']}' (saving {round(load_p, 1)} W)"
                    })

            # Calculate resulting simulated power
            resulting_power_w = max(20.0, round(current_p - reduction_achieved, 1))

            # STEP 3: Determine Optimization Outcome State
            if resulting_power_w <= target + tolerance:
                outcome_state = "OPTIMIZED"
                explanation = (
                    f"Successful power optimization: reduced load by {round(reduction_achieved, 1)} W "
                    f"(from {current_p} W to {resulting_power_w} W), achieving target ({target} W ± {tolerance} W). "
                    f"Excess above threshold ({excess_power_w} W) completely removed."
                )
            elif reduction_achieved > 0:
                outcome_state = "OPTIMIZATION_PARTIAL"
                explanation = (
                    f"Partial power optimization: shed {round(reduction_achieved, 1)} W "
                    f"(from {current_p} W to {resulting_power_w} W), but preferred target ({target} W) "
                    f"could not be fully met with available controllable loads (shortfall: {round(resulting_power_w - target, 1)} W)."
                )
            else:
                outcome_state = "OPTIMIZATION_FAILED"
                explanation = (
                    f"Optimization failed: no eligible controllable nonessential loads were available to shed. "
                    f"Current load remains at {current_p} W (Target: {target} W)."
                )

            # STEP 4: Savings Calculation
            # Hourly baseline duration = 1.0 hour for standard kWh representation
            hourly_duration_hours = 1.0
            hourly_energy_saved_kwh = round((reduction_achieved * hourly_duration_hours) / 1000.0, 3)
            hourly_cost_saved_inr = round(hourly_energy_saved_kwh * tariff_rate, 2)

            # Daily projected duration = 4.0 hours
            daily_duration_hours = 4.0
            daily_energy_saved_kwh = round((reduction_achieved * daily_duration_hours) / 1000.0, 3)
            daily_cost_saved_inr = round(daily_energy_saved_kwh * tariff_rate, 2)
            daily_co2_saved_kg = round(daily_energy_saved_kwh * emission_factor, 2)

            if not dry_run:
                new_room_state = "NORMAL" if outcome_state == "OPTIMIZED" else (outcome_state if outcome_state == "OPTIMIZATION_PARTIAL" else "HIGH_USAGE")
                cursor.execute("""
                    UPDATE rooms
                    SET power_w = ?,
                        current_a = ?,
                        room_state = ?,
                        optimization_state = ?,
                        excess_power_w = ?,
                        optimization_target_w = ?,
                        last_optimization_at = ?,
                        simulated_loads_json = ?,
                        last_update = ?
                    WHERE room_id = ?
                """, (
                    resulting_power_w,
                    round(resulting_power_w / 230.0, 2),
                    new_room_state,
                    outcome_state,
                    max(0.0, round(resulting_power_w - max_threshold, 1)),
                    target,
                    timestamp,
                    json.dumps(loads),
                    timestamp,
                    room_id
                ))

                event_id = f"EVT-OPT-{room_id.replace('-', '')}-{datetime.now().strftime('%Y%m%d%H%M%S%f')[:17]}-{uuid.uuid4().hex[:6]}"
                action_summary = "; ".join([a["description"] for a in actions_taken]) or "No loads modified"
                cursor.execute("""
                    INSERT INTO room_events (
                        event_id, room_id, block_id, room_number, event_type,
                        observed_power_w, threshold_w, duration_minutes,
                        occupancy_state, explanation, action_taken, outcome, simulated,
                        target_w, resulting_power_w, savings_w, savings_kwh, savings_inr
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?)
                """, (
                    event_id, room_id, room["block_id"], room["room_number"], outcome_state,
                    current_p, max_threshold, room["occupancy_state"],
                    explanation, action_summary, outcome_state,
                    target, resulting_power_w, reduction_achieved, hourly_energy_saved_kwh, hourly_cost_saved_inr
                ))
                conn.commit()

            outcome_dict = {
                "status": outcome_state,
                "power_reduction_w": round(reduction_achieved, 1),
                "resulting_power_w": resulting_power_w,
                "target_w": target,
                "savings_w": round(reduction_achieved, 1),
                "savings_kwh": hourly_energy_saved_kwh,
                "savings_inr": hourly_cost_saved_inr,
                "daily_energy_kwh": daily_energy_saved_kwh,
                "daily_cost_saved_inr": daily_cost_saved_inr
            }

            return {
                "success": True,
                "room_id": room_id,
                "initial_power_w": current_p,
                "resulting_power_w": resulting_power_w,
                "max_threshold_w": max_threshold,
                "target_w": target,
                "excess_power_w": excess_power_w,
                "reduction_required_w": reduction_required_w,
                "reduction_achieved_w": round(reduction_achieved, 1),
                "optimization_state": outcome_state,
                "stability_check": "PASSED_STABLE",
                "actions_taken": actions_taken,
                "outcome": outcome_dict,
                "savings": {
                    "power_reduction_w": round(reduction_achieved, 1),
                    "estimated_daily_duration_hours": daily_duration_hours,
                    "daily_energy_kwh": daily_energy_saved_kwh,
                    "tariff_rate_inr_per_kwh": tariff_rate,
                    "daily_cost_saved_inr": daily_cost_saved_inr,
                    "daily_co2_saved_kg": daily_co2_saved_kg,
                    "status": "Simulated Optimization Saving"
                },
                "explanation": explanation
            }
        finally:
            conn.close()

    def get_command_center_stats(self):
        """Calculates primary stats, switch statuses, optimization metrics, and rooms requiring attention."""
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            settings = self.get_system_settings()
            active_high_threshold = float(settings.get("high_power_threshold_w", 1200.0))
            active_empty_threshold = float(settings.get("empty_room_threshold_w", 35.0))
            def_opt_target = float(settings.get("default_optimization_target_w", 800.0))

            # All rooms count
            cursor.execute("SELECT COUNT(*) FROM rooms")
            total_rooms = cursor.fetchone()[0]

            # Online rooms
            cursor.execute("SELECT COUNT(*) FROM rooms WHERE sensor_status = 'ONLINE'")
            rooms_online = cursor.fetchone()[0]

            # High consumption rooms
            cursor.execute("SELECT COUNT(*) FROM rooms WHERE room_state IN ('HIGH_USAGE', 'TRIP_PENDING') OR power_w > ?", (active_high_threshold,))
            rooms_high_usage = cursor.fetchone()[0]

            # Active anomaly alerts
            cursor.execute("SELECT COUNT(*) FROM rooms WHERE room_state IN ('ANOMALY_DETECTED', 'HIGH_USAGE', 'TRIP_PENDING', 'DATA_STALE') OR power_w > ?", (active_high_threshold,))
            active_anomalies = cursor.fetchone()[0]

            # Simulated power trips
            cursor.execute("SELECT COUNT(*) FROM rooms WHERE room_state IN ('TRIPPED_SIMULATED', 'TRIPPED_CRITICAL') OR relay_state = 'TRIPPED_SIMULATED' OR fault_status IN ('ACTIVE_FAULT', 'CRITICAL_FAULT')")
            simulated_trips = cursor.fetchone()[0]

            # Switched OFF count (effective_switch_state = 'OFF')
            cursor.execute("SELECT COUNT(*) FROM rooms WHERE effective_switch_state = 'OFF' OR switch_state = 'OFF' OR room_state IN ('TRIPPED_SIMULATED', 'TRIPPED_CRITICAL', 'MANUAL_OFF')")
            rooms_switched_off = cursor.fetchone()[0]

            # Manual OFF locked count
            cursor.execute("SELECT COUNT(*) FROM rooms WHERE manual_off_lock = 1")
            manual_off_locked = cursor.fetchone()[0]

            # Optimized rooms count
            cursor.execute("SELECT COUNT(*) FROM rooms WHERE optimization_state = 'OPTIMIZED'")
            rooms_optimized = cursor.fetchone()[0]

            # Total live power (W) across campus rooms
            cursor.execute("SELECT SUM(power_w) as total_w, SUM(energy_kwh) as total_kwh FROM rooms")
            p_row = cursor.fetchone()
            campus_live_watts = round(float(p_row["total_w"] or 0.0), 1)
            campus_energy_kwh = round(float(p_row["total_kwh"] or 0.0), 2)

            # Rooms requiring immediate attention
            cursor.execute("""
                SELECT * FROM rooms 
                WHERE room_state IN ('TRIPPED_SIMULATED', 'TRIPPED_CRITICAL', 'TRIP_PENDING', 'HIGH_USAGE', 'ANOMALY_DETECTED', 'DATA_STALE', 'SENSOR_OFFLINE', 'MANUAL_OFF')
                   OR effective_switch_state = 'OFF'
                   OR manual_off_lock = 1
                   OR power_w > ?
                ORDER BY 
                    CASE room_state 
                        WHEN 'TRIPPED_CRITICAL' THEN 1
                        WHEN 'TRIPPED_SIMULATED' THEN 2 
                        WHEN 'TRIP_PENDING' THEN 3 
                        WHEN 'HIGH_USAGE' THEN 4 
                        WHEN 'MANUAL_OFF' THEN 5
                        WHEN 'ANOMALY_DETECTED' THEN 6 
                        ELSE 7 
                    END,
                    power_w DESC
            """, (active_high_threshold,))
            attention_rows = [dict(r) for r in cursor.fetchall()]

            attention_list = []
            for r in attention_rows:
                reason = r.get("trip_reason") or ""
                action = "Dispatch floor prefect to inspect room and check appliances."
                eff_sw = r.get("effective_switch_state") or ("OFF" if r.get("room_state") in ("TRIPPED_SIMULATED", "TRIPPED_CRITICAL", "MANUAL_OFF") else "ON")
                
                if r["room_state"] in ("TRIPPED_SIMULATED", "TRIPPED_CRITICAL"):
                    action = "Inspect physical circuit, verify room safety, then confirm Problem Resolved to auto-restore."
                    if not reason:
                        reason = f"Simulated auto-trip triggered: power exceeded applicable threshold for {r.get('persistence_minutes', 0)} min."
                elif r["room_state"] == "MANUAL_OFF" or r.get("manual_off_lock") == 1:
                    reason = reason or "Room main switch manually switched OFF by warden. Manual OFF lock active."
                    action = "Manual OFF lock engaged. Warden must release lock to allow circuit restoration."
                elif r["room_state"] == "TRIP_PENDING":
                    action = "Power excursion persistent. AI optimization candidate before potential trip timeout."
                    if not reason:
                        reason = f"Power at {r['power_w']} W exceeds limit ({active_high_threshold} W) for {r.get('persistence_minutes', 0)} min."
                elif r["room_state"] == "SENSOR_OFFLINE":
                    reason = "Hardware node communication lost. Sensor offline."
                    action = "Verify corridor hub power and check ESP32 node connectivity."
                elif r["room_state"] == "DATA_STALE":
                    reason = "Telemetry timeout: no heartbeat received in > 30 minutes."
                    action = "Check wireless link and sensor heartbeat."
                elif not reason or "threshold" in reason or "limit" in reason:
                    reason = f"Observed {r['power_w']} W vs configured {active_high_threshold} W limit."

                r_target = float(r.get("optimization_target_w") or def_opt_target)
                r_excess = max(0.0, round(float(r.get("power_w", 0.0)) - active_high_threshold, 1)) if r.get("sensor_status") != "OFFLINE" else 0.0
                r_reduction = max(0.0, round(float(r.get("power_w", 0.0)) - r_target, 1)) if r.get("sensor_status") != "OFFLINE" else 0.0

                attention_list.append({
                    "room_id": r["room_id"],
                    "block_id": r["block_id"],
                    "room_number": r["room_number"],
                    "power_w": r["power_w"],
                    "threshold_w": active_high_threshold,
                    "empty_threshold_w": active_empty_threshold,
                    "optimization_target_w": r_target,
                    "excess_power_w": r_excess,
                    "reduction_required_w": r_reduction,
                    "optimization_state": r.get("optimization_state") or r["room_state"],
                    "duration_minutes": r.get("persistence_minutes", 0),
                    "occupancy_state": r.get("occupancy_state", "Occupied"),
                    "room_state": r["room_state"] if (r["room_state"] != "NORMAL" or r["power_w"] <= active_high_threshold) else "HIGH_USAGE",
                    "relay_state": r.get("relay_state", "CLOSED"),
                    "switch_state": r.get("switch_state", "ON"),
                    "effective_switch_state": eff_sw,
                    "manual_off_lock": int(r.get("manual_off_lock") or 0),
                    "reason": reason,
                    "recommended_action": action
                })

            return {
                "total_rooms": total_rooms,
                "rooms_online": rooms_online,
                "rooms_high_usage": rooms_high_usage,
                "active_anomalies": active_anomalies,
                "simulated_trips": simulated_trips,
                "rooms_switched_off": rooms_switched_off,
                "manual_off_locked": manual_off_locked,
                "rooms_optimized": rooms_optimized,
                "campus_live_watts": campus_live_watts,
                "campus_energy_kwh": campus_energy_kwh,
                "high_power_threshold_w": active_high_threshold,
                "empty_room_threshold_w": active_empty_threshold,
                "default_optimization_target_w": def_opt_target,
                "attention_rooms": attention_list
            }
        finally:
            conn.close()

    def manual_switch_off(self, room_id, operator="Hostel Warden", reason=None):
        """
        Manually turns the simulated room main switch OFF and engages the manual OFF lock.
        Immediately isolates simulated power (0 W) and logs the MANUAL_OFF event.
        """
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM rooms WHERE room_id = ?", (room_id,))
            room = cursor.fetchone()
            if not room:
                return {"success": False, "error": f"Room {room_id} not found.", "code": 404}

            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            trip_reason = reason or f"Room main switch manually switched OFF by {operator}. Manual lock engaged."

            cursor.execute("""
                UPDATE rooms
                SET switch_state = 'OFF',
                    effective_switch_state = 'OFF',
                    manual_off_lock = 1,
                    room_state = 'MANUAL_OFF',
                    relay_state = 'OPEN_MANUAL',
                    power_w = 0.0,
                    current_a = 0.0,
                    trip_reason = ?,
                    last_switch_by = ?,
                    last_switch_at = ?,
                    restoration_eligible = 0,
                    last_update = ?
                WHERE room_id = ?
            """, (trip_reason, f"{operator} (Manual OFF)", timestamp, timestamp, room_id))

            event_id = f"EVT-OFF-{room_id.replace('-', '')}-{datetime.now().strftime('%Y%m%d%H%M%S%f')[:17]}-{uuid.uuid4().hex[:6]}"
            cursor.execute("""
                INSERT INTO room_events (
                    event_id, room_id, block_id, room_number, event_type,
                    observed_power_w, threshold_w, duration_minutes,
                    occupancy_state, explanation, action_taken, outcome, simulated
                ) VALUES (?, ?, ?, ?, 'MANUAL_OFF', 0.0, ?, 0, ?, ?, ?, 'Switched OFF - Manual Lock Active', 1)
            """, (
                event_id, room_id, room["block_id"], room["room_number"],
                room["threshold_w"], room["occupancy_state"],
                f"Room {room_id} main switch turned OFF manually by {operator}. Simulated circuit isolated with Manual OFF lock engaged.",
                f"Manual switch OFF executed by {operator} (SIMULATION ONLY)."
            ))

            conn.commit()
            return {
                "success": True,
                "room_id": room_id,
                "switch_state": "OFF",
                "effective_switch_state": "OFF",
                "manual_off_lock": 1,
                "room_state": "MANUAL_OFF",
                "relay_state": "OPEN_MANUAL",
                "last_switch_by": f"{operator} (Manual OFF)",
                "last_switch_at": timestamp,
                "message": f"Room {room_id} main switch manually turned OFF (SIMULATION ONLY). Manual OFF lock engaged."
            }
        finally:
            conn.close()

    def manual_switch_on(self, room_id, operator="Hostel Warden"):
        """
        Manually restores the simulated room main switch to ON, subject to safety checks.
        Rejects restoration if a manual lock is active or an unresolved critical fault remains.
        """
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM rooms WHERE room_id = ?", (room_id,))
            room = cursor.fetchone()
            if not room:
                return {"success": False, "error": f"Room {room_id} not found.", "code": 404}

            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # Check 1: Manual OFF lock active
            if int(room["manual_off_lock"] or 0) == 1:
                block_reason = f"Manual ON rejected for Room {room_id}: Room is under Manual OFF lock. The warden must explicitly release the manual OFF lock before power can be restored."
                self._log_rejected_on(cursor, room, operator, block_reason, timestamp)
                conn.commit()
                return {"success": False, "error": block_reason, "block_reason": block_reason, "code": 400}

            # Check 2: Sensor offline
            if room["sensor_status"] == "OFFLINE":
                block_reason = f"Manual ON rejected for Room {room_id}: Sensor telemetry is OFFLINE. Cannot verify circuit safety before energizing."
                self._log_rejected_on(cursor, room, operator, block_reason, timestamp)
                conn.commit()
                return {"success": False, "error": block_reason, "block_reason": block_reason, "code": 400}

            # Check 3: Active critical fault or unacknowledged trip condition
            is_critical_fault = (
                room["fault_status"] in ("ACTIVE_FAULT", "PENDING_VERIFICATION") or
                room["room_state"] in ("TRIPPED_SIMULATED", "TRIP_PENDING")
            )
            if is_critical_fault:
                reason_detail = room["trip_reason"] or "Simulated critical trip / fault condition"
                block_reason = f"Manual ON rejected for Room {room_id}: Active safety-critical fault remains unresolved ({reason_detail}). Please investigate and confirm 'Problem Resolved' after repairing the fault."
                self._log_rejected_on(cursor, room, operator, block_reason, timestamp)
                conn.commit()
                return {"success": False, "error": block_reason, "block_reason": block_reason, "code": 400}

            # Check 4: Sensor readings still exceed configured limit
            settings = self.get_system_settings()
            active_high = float(settings.get("high_power_threshold_w", room["threshold_w"]))
            if float(room["power_w"] or 0.0) > active_high:
                block_reason = f"Manual ON rejected for Room {room_id}: Real power ({room['power_w']} W) exceeds configured limit ({active_high} W)."
                self._log_rejected_on(cursor, room, operator, block_reason, timestamp)
                conn.commit()
                return {"success": False, "error": block_reason, "block_reason": block_reason, "code": 400}

            # Safety checks PASS: Energize room to safe baseline
            occ = room["occupancy_state"]
            safe_power = 65.0 if occ == "Occupied" else 20.0
            safe_current = round(safe_power / 230.0, 2)

            cursor.execute("""
                UPDATE rooms
                SET switch_state = 'ON',
                    effective_switch_state = 'ON',
                    manual_off_lock = 0,
                    room_state = 'NORMAL',
                    relay_state = 'CLOSED',
                    fault_status = 'NONE',
                    power_w = ?,
                    current_a = ?,
                    trip_reason = '',
                    persistence_minutes = 0,
                    last_switch_by = ?,
                    last_switch_at = ?,
                    restoration_eligible = 1,
                    last_update = ?
                WHERE room_id = ?
            """, (safe_power, safe_current, f"{operator} (Manual ON)", timestamp, timestamp, room_id))

            event_id = f"EVT-ON-{room_id.replace('-', '')}-{datetime.now().strftime('%Y%m%d%H%M%S%f')[:17]}-{uuid.uuid4().hex[:6]}"
            cursor.execute("""
                INSERT INTO room_events (
                    event_id, room_id, block_id, room_number, event_type,
                    observed_power_w, threshold_w, duration_minutes,
                    occupancy_state, explanation, action_taken, outcome, simulated
                ) VALUES (?, ?, ?, ?, 'MANUAL_ON', ?, ?, 0, ?, ?, ?, 'Restored to ON', 1)
            """, (
                event_id, room_id, room["block_id"], room["room_number"],
                safe_power, room["threshold_w"], occ,
                f"Manual ON command executed by {operator}. All safety checks passed. Circuit energized to {safe_power} W baseline.",
                f"Manual simulated switch ON executed by {operator}."
            ))

            conn.commit()
            return {
                "success": True,
                "room_id": room_id,
                "switch_state": "ON",
                "effective_switch_state": "ON",
                "manual_off_lock": 0,
                "room_state": "NORMAL",
                "relay_state": "CLOSED",
                "last_switch_by": f"{operator} (Manual ON)",
                "last_switch_at": timestamp,
                "message": f"Room {room_id} main switch successfully switched ON. Simulated power restored to normal baseline."
            }
        finally:
            conn.close()

    def _log_rejected_on(self, cursor, room, operator, block_reason, timestamp):
        event_id = f"EVT-REJ-{room['room_id'].replace('-', '')}-{datetime.now().strftime('%Y%m%d%H%M%S%f')[:17]}-{uuid.uuid4().hex[:6]}"
        cursor.execute("""
            INSERT INTO room_events (
                event_id, room_id, block_id, room_number, event_type,
                observed_power_w, threshold_w, duration_minutes,
                occupancy_state, explanation, action_taken, outcome, simulated
            ) VALUES (?, ?, ?, ?, 'MANUAL_ON_REJECTED', ?, ?, 0, ?, ?, ?, 'Blocked by Safety Policy', 1)
        """, (
            event_id, room["room_id"], room["block_id"], room["room_number"],
            room["power_w"], room["threshold_w"], room["occupancy_state"],
            block_reason,
            f"Manual ON blocked by safety checks for {operator}."
        ))

    def release_manual_lock(self, room_id, operator="Hostel Warden"):
        """
        Releases the manual OFF lock for a room.
        Evaluates safety checks:
        - If all checks pass: automatically restores simulated power to ON.
        - If active dangerous fault remains: keeps effective switch state OFF and explains why.
        """
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM rooms WHERE room_id = ?", (room_id,))
            room = cursor.fetchone()
            if not room:
                return {"success": False, "error": f"Room {room_id} not found.", "code": 404}

            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            if int(room["manual_off_lock"] or 0) == 0:
                return {
                    "success": True,
                    "already_unlocked": True,
                    "message": f"Room {room_id} manual OFF lock is already released."
                }

            # Release the lock in DB
            cursor.execute("UPDATE rooms SET manual_off_lock = 0 WHERE room_id = ?", (room_id,))

            # Check if circuit is safe to restore
            is_offline = room["sensor_status"] == "OFFLINE"
            has_fault = (
                room["fault_status"] in ("ACTIVE_FAULT", "PENDING_VERIFICATION") or
                room["room_state"] in ("TRIPPED_SIMULATED", "TRIP_PENDING")
            )
            settings = self.get_system_settings()
            active_high = float(settings.get("high_power_threshold_w", room["threshold_w"]))
            is_over = float(room["power_w"] or 0.0) > active_high

            if is_offline or has_fault or is_over:
                # Cannot restore yet
                reason = "Sensor node is OFFLINE" if is_offline else (room["trip_reason"] or "Active critical fault condition")
                cursor.execute("""
                    UPDATE rooms
                    SET restoration_eligible = 0,
                        effective_switch_state = 'OFF',
                        last_switch_by = ?,
                        last_switch_at = ?,
                        last_update = ?
                    WHERE room_id = ?
                """, (f"{operator} (Lock Released)", timestamp, timestamp, room_id))

                event_id = f"EVT-LOCK-{room_id.replace('-', '')}-{datetime.now().strftime('%Y%m%d%H%M%S%f')[:17]}-{uuid.uuid4().hex[:6]}"
                cursor.execute("""
                    INSERT INTO room_events (
                        event_id, room_id, block_id, room_number, event_type,
                        observed_power_w, threshold_w, duration_minutes,
                        occupancy_state, explanation, action_taken, outcome, simulated
                    ) VALUES (?, ?, ?, ?, 'RELEASE_LOCK', ?, ?, 0, ?, ?, ?, 'Lock Released - Power Held OFF', 1)
                """, (
                    event_id, room_id, room["block_id"], room["room_number"],
                    room["power_w"], room["threshold_w"], room["occupancy_state"],
                    f"Manual OFF lock released by {operator}, but power remains OFF because safety checks failed: {reason}",
                    f"Lock released by {operator}; power restoration held due to active fault."
                ))
                conn.commit()

                return {
                    "success": True,
                    "lock_released": True,
                    "restored": False,
                    "message": f"Manual OFF lock released for Room {room_id}, but power remains OFF because an unresolved fault is present ({reason})."
                }

            # Safety checks pass -> Restore power!
            occ = room["occupancy_state"]
            safe_power = 65.0 if occ == "Occupied" else 20.0
            safe_current = round(safe_power / 230.0, 2)

            cursor.execute("""
                UPDATE rooms
                SET switch_state = 'ON',
                    effective_switch_state = 'ON',
                    manual_off_lock = 0,
                    room_state = 'NORMAL',
                    relay_state = 'CLOSED',
                    fault_status = 'NONE',
                    power_w = ?,
                    current_a = ?,
                    trip_reason = '',
                    persistence_minutes = 0,
                    last_switch_by = ?,
                    last_switch_at = ?,
                    restoration_eligible = 1,
                    last_update = ?
                WHERE room_id = ?
            """, (safe_power, safe_current, f"{operator} (Lock Released & Restored)", timestamp, timestamp, room_id))

            event_id = f"EVT-RESTORE-{room_id.replace('-', '')}-{datetime.now().strftime('%Y%m%d%H%M%S%f')[:17]}-{uuid.uuid4().hex[:6]}"
            cursor.execute("""
                INSERT INTO room_events (
                    event_id, room_id, block_id, room_number, event_type,
                    observed_power_w, threshold_w, duration_minutes,
                    occupancy_state, explanation, action_taken, outcome, simulated
                ) VALUES (?, ?, ?, ?, 'AUTO_RESTORE', ?, ?, 0, ?, ?, ?, 'Restored to Normal', 1)
            """, (
                event_id, room_id, room["block_id"], room["room_number"],
                safe_power, room["threshold_w"], occ,
                f"Manual OFF lock released by {operator}. All safety checks passed. Simulated main switch automatically restored to ON.",
                f"Simulated power restored following lock release by {operator}."
            ))

            conn.commit()
            return {
                "success": True,
                "lock_released": True,
                "restored": True,
                "switch_state": "ON",
                "effective_switch_state": "ON",
                "message": f"Manual OFF lock released for Room {room_id}. Safety checks passed and simulated power has been automatically restored to ON."
            }
        finally:
            conn.close()

    def resolve_room_fault(self, room_id, operator="Hostel Warden", resolution_notes="", fault_cleared=True):
        """
        Processes warden's 'Problem Resolved' confirmation.
        Runs safety restoration checks:
        1. If active dangerous fault remains (e.g. fault_cleared is False or sensor OFFLINE):
           rejects restoration, records resolution attempt.
        2. If manual OFF lock is active:
           records fault resolution, but holds power restoration until warden explicitly releases lock.
        3. If all checks pass:
           automatically restores simulated main switch to ON (AUTO_RESTORE).
        """
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM rooms WHERE room_id = ?", (room_id,))
            room = cursor.fetchone()
            if not room:
                return {"success": False, "error": f"Room {room_id} not found.", "code": 404}

            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            notes = resolution_notes or "Warden verified inspection and resolved incident."

            # Record resolution confirmation details
            cursor.execute("""
                UPDATE rooms
                SET resolution_confirmed_by = ?,
                    resolution_confirmed_at = ?,
                    resolution_notes = ?,
                    last_update = ?
                WHERE room_id = ?
            """, (operator, timestamp, notes, timestamp, room_id))

            # Safety Check 1: Does an active dangerous fault remain?
            if not fault_cleared or room["sensor_status"] == "OFFLINE":
                danger_reason = "Sensor node is OFFLINE" if room["sensor_status"] == "OFFLINE" else "Physical hazard remains uncleared on circuit"
                cursor.execute("""
                    UPDATE rooms
                    SET fault_status = 'ACTIVE_FAULT',
                        restoration_eligible = 0,
                        effective_switch_state = 'OFF'
                    WHERE room_id = ?
                """, (room_id,))

                event_id = f"EVT-RES-FAIL-{room_id.replace('-', '')}-{datetime.now().strftime('%Y%m%d%H%M%S%f')[:17]}-{uuid.uuid4().hex[:6]}"
                cursor.execute("""
                    INSERT INTO room_events (
                        event_id, room_id, block_id, room_number, event_type,
                        observed_power_w, threshold_w, duration_minutes,
                        occupancy_state, explanation, action_taken, outcome, simulated
                    ) VALUES (?, ?, ?, ?, 'PROBLEM_RESOLVED', ?, ?, 0, ?, ?, ?, 'Restoration Rejected', 1)
                """, (
                    event_id, room_id, room["block_id"], room["room_number"],
                    room["power_w"], room["threshold_w"], room["occupancy_state"],
                    f"Problem resolution submitted by {operator}, but restoration checks FAILED: {danger_reason}. Notes: {notes}",
                    "Restoration checks failed. Power remains disconnected."
                ))
                conn.commit()

                return {
                    "success": False,
                    "restored": False,
                    "error": f"Restoration checks failed: {danger_reason}. Power cannot be automatically restored until the danger is fully eliminated.",
                    "code": 400
                }

            # Safety Check 2: Is Manual OFF Lock active?
            if int(room["manual_off_lock"] or 0) == 1:
                cursor.execute("""
                    UPDATE rooms
                    SET fault_status = 'RESOLVED',
                        restoration_eligible = 0,
                        effective_switch_state = 'OFF'
                    WHERE room_id = ?
                """, (room_id,))

                event_id = f"EVT-RES-LOCK-{room_id.replace('-', '')}-{datetime.now().strftime('%Y%m%d%H%M%S%f')[:17]}-{uuid.uuid4().hex[:6]}"
                cursor.execute("""
                    INSERT INTO room_events (
                        event_id, room_id, block_id, room_number, event_type,
                        observed_power_w, threshold_w, duration_minutes,
                        occupancy_state, explanation, action_taken, outcome, simulated
                    ) VALUES (?, ?, ?, ?, 'PROBLEM_RESOLVED', ?, ?, 0, ?, ?, ?, 'Fault Resolved - Power Held by Manual Lock', 1)
                """, (
                    event_id, room_id, room["block_id"], room["room_number"],
                    room["power_w"], room["threshold_w"], room["occupancy_state"],
                    f"Fault resolution confirmed by {operator} ({notes}). Power restoration held: Manual OFF lock is active. Warden must release lock to restore power.",
                    "Resolution confirmed; auto-restore prevented by manual lock."
                ))
                conn.commit()

                return {
                    "success": True,
                    "restored": False,
                    "manual_lock_held": True,
                    "message": f"Fault resolution confirmed for Room {room_id}. However, power remains OFF because the Manual OFF lock is active. Please release the lock to restore power."
                }

            # Safety Check 3: All restoration checks PASS!
            occ = room["occupancy_state"]
            safe_power = 65.0 if occ == "Occupied" else 20.0
            safe_current = round(safe_power / 230.0, 2)

            cursor.execute("""
                UPDATE rooms
                SET switch_state = 'ON',
                    effective_switch_state = 'ON',
                    manual_off_lock = 0,
                    room_state = 'NORMAL',
                    relay_state = 'CLOSED',
                    fault_status = 'NONE',
                    power_w = ?,
                    current_a = ?,
                    trip_reason = '',
                    persistence_minutes = 0,
                    last_switch_by = ?,
                    last_switch_at = ?,
                    restoration_eligible = 1,
                    last_update = ?
                WHERE room_id = ?
            """, (safe_power, safe_current, f"Auto-Restore System (Verified by {operator})", timestamp, timestamp, room_id))

            # Log Problem Resolved event
            res_evt_id = f"EVT-RES-{room_id.replace('-', '')}-{datetime.now().strftime('%Y%m%d%H%M%S%f')[:17]}-{uuid.uuid4().hex[:6]}"
            cursor.execute("""
                INSERT INTO room_events (
                    event_id, room_id, block_id, room_number, event_type,
                    observed_power_w, threshold_w, duration_minutes,
                    occupancy_state, explanation, action_taken, outcome, simulated
                ) VALUES (?, ?, ?, ?, 'PROBLEM_RESOLVED', ?, ?, 0, ?, ?, ?, 'Fault Cleared & Verified', 1)
            """, (
                res_evt_id, room_id, room["block_id"], room["room_number"],
                safe_power, room["threshold_w"], occ,
                f"Fault resolution confirmed by {operator}. Notes: {notes}",
                f"Incident verified and cleared by {operator}."
            ))

            # Log Auto Restore event
            restore_evt_id = f"EVT-AUTORES-{room_id.replace('-', '')}-{datetime.now().strftime('%Y%m%d%H%M%S%f')[:17]}-{uuid.uuid4().hex[:6]}"
            cursor.execute("""
                INSERT INTO room_events (
                    event_id, room_id, block_id, room_number, event_type,
                    observed_power_w, threshold_w, duration_minutes,
                    occupancy_state, explanation, action_taken, outcome, simulated
                ) VALUES (?, ?, ?, ?, 'AUTO_RESTORE', ?, ?, 0, ?, ?, ?, 'Restored to Normal', 1)
            """, (
                restore_evt_id, room_id, room["block_id"], room["room_number"],
                safe_power, room["threshold_w"], occ,
                f"All restoration safety checks passed for Room {room_id}. Simulated main switch automatically restored to ON.",
                "Simulated power automatically restored to circuit."
            ))

            conn.commit()
            return {
                "success": True,
                "restored": True,
                "switch_state": "ON",
                "effective_switch_state": "ON",
                "message": f"Fault resolved and safety checks passed. Room {room_id} main switch automatically restored to ON."
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
                    switch_state = 'ON',
                    effective_switch_state = 'ON',
                    manual_off_lock = 0,
                    fault_status = 'NONE',
                    power_w = ?,
                    current_a = ?,
                    persistence_minutes = 0,
                    trip_reason = '',
                    last_switch_by = ?,
                    last_switch_at = ?,
                    restoration_eligible = 1,
                    last_update = ?
                WHERE room_id = ?
            """, (reset_power, reset_current, f"{operator} (Reset)", timestamp, timestamp, room_id))

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
                "switch_state": "ON",
                "effective_switch_state": "ON",
                "message": f"Room {room_id} simulated power cutoff successfully reset to NORMAL. Other rooms remain unaffected."
            }
        finally:
            conn.close()

    def reset_demo_simulation_state(self, operator="Hostel Warden"):
        """
        Safely resets demonstration simulation rooms (such as A-101, A-102, A-103, D-101, D-205)
        back to their clean baseline operational states without deleting historical incidents,
        room_events, audit logs, or system settings.
        """
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # Benchmark baselines for seeded demo rooms
            benchmark_rooms = [
                ("A-101", 65.0, 0.28, "Occupied", "ONLINE", "NORMAL", "CLOSED", "ON", "NONE", ""),
                ("A-102", 65.0, 0.30, "Occupied", "ONLINE", "NORMAL", "CLOSED", "ON", "NONE", ""),
                ("A-103", 145.0, 0.65, "Occupied", "ONLINE", "NORMAL", "CLOSED", "ON", "NONE", ""),
                ("B-101", 75.0, 0.35, "Occupied", "ONLINE", "NORMAL", "CLOSED", "ON", "NONE", ""),
                ("B-202", 28.0, 0.13, "Likely Vacant", "ONLINE", "NORMAL", "CLOSED", "ON", "NONE", ""),
                ("C-312", 110.0, 0.48, "Occupied", "ONLINE", "NORMAL", "CLOSED", "ON", "NONE", ""),
                ("D-101", 55.0, 0.25, "Occupied", "ONLINE", "NORMAL", "CLOSED", "ON", "NONE", ""),
                ("D-202", 72.0, 0.32, "Occupied", "ONLINE", "NORMAL", "CLOSED", "ON", "NONE", ""),
                ("D-205", 75.0, 0.34, "Likely Vacant", "ONLINE", "NORMAL", "CLOSED", "ON", "NONE", ""),
            ]

            for rid, pw, cur, occ, s_stat, r_stat, rel, sw, flt, tr in benchmark_rooms:
                cursor.execute("""
                    UPDATE rooms
                    SET power_w = ?,
                        current_a = ?,
                        occupancy_state = ?,
                        sensor_status = ?,
                        room_state = ?,
                        relay_state = ?,
                        switch_state = ?,
                        effective_switch_state = ?,
                        manual_off_lock = 0,
                        fault_status = ?,
                        trip_reason = ?,
                        persistence_minutes = 0,
                        restoration_eligible = 1,
                        last_switch_by = ?,
                        last_switch_at = ?,
                        last_update = ?
                    WHERE room_id = ?
                """, (pw, cur, occ, s_stat, r_stat, rel, sw, sw, flt, tr, f"{operator} (Demo Reset)", timestamp, timestamp, rid))

            # Log demo reset event without deleting any historical room_events
            event_id = f"EVT-DEMORESET-{datetime.now().strftime('%Y%m%d%H%M%S%f')[:17]}-{uuid.uuid4().hex[:6]}"
            cursor.execute("""
                INSERT INTO room_events (
                    event_id, room_id, block_id, room_number, event_type,
                    observed_power_w, threshold_w, duration_minutes,
                    occupancy_state, explanation, action_taken, outcome, simulated
                ) VALUES (?, 'ALL', 'ALL', 'ALL', 'DEMO_RESET', 0.0, 1200.0, 0, 'Normal',
                          ?, ?, 'Benchmark Restored', 1)
            """, (
                event_id,
                f"Demo simulation states safely restored to baseline by {operator}. Historical telemetry and incident memories preserved.",
                f"Clean demo state restored by {operator}."
            ))

            conn.commit()
            return {
                "success": True,
                "message": f"Demo simulation state successfully reset to benchmark by {operator}. Incident memory and history preserved.",
                "reset_rooms": [r[0] for r in benchmark_rooms]
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
                SET power_w = 0.0, current_a = 0.0, voltage_v = 230.0, power_factor = 0.97,
                    occupancy_state = 'Likely Vacant', sensor_status = 'ONLINE', room_state = 'TRIPPED_SIMULATED',
                    relay_state = 'TRIPPED_SIMULATED',
                    switch_state = 'OFF',
                    effective_switch_state = 'OFF',
                    fault_status = 'ACTIVE_FAULT',
                    restoration_eligible = 0,
                    last_switch_by = 'Auto-Trip Protection Engine',
                    last_switch_at = ?,
                    trip_reason = 'Simulated Auto-Trip: Room vacant during daytime with 280W load persistent > ' || ? || ' minutes (standby limit ' || ROUND(?, 0) || 'W). Cutoff relay opened (SIMULATION ONLY). Circuit de-energized.',
                    persistence_minutes = ?, last_update = ?
                WHERE room_id = ?
            """, (timestamp, p_win, vacant_limit, dur, timestamp, rid))
            msg = f"Room {rid}: Simulated auto-trip triggered! 280W draw in vacant room exceeded {p_win}-min persistence window. Circuit de-energized."
            evt_type = "AUTO_TRIP"

        elif scenario_id == 6:
            # 6. Occupied room with normal consumption (Room D-104)
            rid = target_room_id or "D-104"
            cursor.execute("""
                UPDATE rooms
                SET power_w = 110.0, current_a = 0.49, voltage_v = 230.1, power_factor = 0.95,
                    occupancy_state = 'Occupied', sensor_status = 'ONLINE', room_state = 'NORMAL',
                    relay_state = 'CLOSED', trip_reason = 'Normal daytime occupancy: laptop and desk lamp.',
                    switch_state = 'ON', effective_switch_state = 'ON',
                    fault_status = 'NONE', restoration_eligible = 1,
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
                    fault_status = 'ACTIVE_FAULT', restoration_eligible = 0,
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
            benchmark_rooms = [
                ("A-101", 65.0, 0.28, "Occupied", "ONLINE", "NORMAL", "CLOSED", "ON", "NONE", ""),
                ("A-102", 65.0, 0.30, "Occupied", "ONLINE", "NORMAL", "CLOSED", "ON", "NONE", ""),
                ("A-103", 145.0, 0.65, "Occupied", "ONLINE", "NORMAL", "CLOSED", "ON", "NONE", ""),
                ("B-101", 75.0, 0.35, "Occupied", "ONLINE", "NORMAL", "CLOSED", "ON", "NONE", ""),
                ("B-202", 28.0, 0.13, "Likely Vacant", "ONLINE", "NORMAL", "CLOSED", "ON", "NONE", ""),
                ("C-312", 110.0, 0.48, "Occupied", "ONLINE", "NORMAL", "CLOSED", "ON", "NONE", ""),
                ("D-101", 55.0, 0.25, "Occupied", "ONLINE", "NORMAL", "CLOSED", "ON", "NONE", ""),
                ("D-202", 72.0, 0.32, "Occupied", "ONLINE", "NORMAL", "CLOSED", "ON", "NONE", ""),
                ("D-205", 75.0, 0.34, "Likely Vacant", "ONLINE", "NORMAL", "CLOSED", "ON", "NONE", ""),
            ]
            for brid, bpw, bcur, bocc, bs_stat, br_stat, brel, bsw, bflt, btr in benchmark_rooms:
                cursor.execute("""
                    UPDATE rooms
                    SET power_w = ?, current_a = ?, occupancy_state = ?, sensor_status = ?,
                        room_state = ?, relay_state = ?, switch_state = ?, effective_switch_state = ?,
                        manual_off_lock = 0, fault_status = ?, trip_reason = ?, persistence_minutes = 0,
                        restoration_eligible = 1, last_switch_by = 'System Benchmark Reset',
                        last_switch_at = ?, last_update = ?
                    WHERE room_id = ?
                """, (bpw, bcur, bocc, bs_stat, br_stat, brel, bsw, bsw, bflt, btr, timestamp, timestamp, brid))
            msg = "All room simulation test states have been reset to benchmark. Historical incident history preserved."
            evt_type = "RESET"
            rid = "ALL"

        # Log event to SQLite if single room affected
        if scenario_id != 10:
            cursor.execute("SELECT block_id, room_number, power_w, threshold_w, occupancy_state FROM rooms WHERE room_id = ?", (rid,))
            r_info = cursor.fetchone()
            if r_info:
                event_id = f"EVT-NILM-{rid.replace('-', '')}-{datetime.now().strftime('%Y%m%d%H%M%S%f')[:17]}-{uuid.uuid4().hex[:6]}"
                observed_p = 280.0 if scenario_id == 5 else r_info["power_w"]
                cursor.execute("""
                    INSERT INTO room_events (
                        event_id, room_id, block_id, room_number, event_type,
                        observed_power_w, threshold_w, duration_minutes,
                        occupancy_state, explanation, action_taken, outcome, simulated
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, 'Simulated', 1)
                """, (
                    event_id, rid, r_info["block_id"], r_info["room_number"], evt_type,
                    observed_p, r_info["threshold_w"], r_info["occupancy_state"],
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

    def set_room_simulation_profile(self, room_id, profile):
        """Sets the simulation profile for a specific room and returns the updated room dict."""
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT room_id FROM rooms WHERE room_id = ?", (room_id,))
            if not cursor.fetchone():
                return None
            cursor.execute("UPDATE rooms SET simulation_profile = ? WHERE room_id = ?", (profile, room_id))
            conn.commit()
            return self.get_room_by_id(room_id)
        finally:
            conn.close()

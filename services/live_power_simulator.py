import json
import math
import os
import random
import threading
import time
from datetime import datetime
from config import Config
from database import get_db_connection

class LivePowerSimulator:
    """
    Authoritative Background Live Power Simulation Engine.
    Simulates realistic, dynamic room-level electrical telemetry (W, V, A, PF, kWh)
    every 10 seconds across all hostel rooms according to their operating profiles.
    
    Adheres strictly to safety requirements:
    - Pure simulation sandbox: Physical hardware relays remain permanently disabled (0).
    - Latched safety trips and manual OFF locks are never cleared by the simulation.
    - Offline sensors do not fabricate readings.
    - Cumulative energy is strictly monotonic (never randomly decreases).
    - Fully deterministic test mode supported via seed and step controls.
    """
    
    _instance = None
    _singleton_lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._singleton_lock:
            if cls._instance is None:
                cls._instance = super(LivePowerSimulator, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self, interval_seconds=10.0):
        if self._initialized:
            return
        self.interval_seconds = float(interval_seconds)
        self._running = False
        self._paused = False
        self._thread = None
        self._lock = threading.Lock()
        self._last_tick_time = time.time()
        self._tick_count = 0
        self._random = random.Random()
        self._deterministic = False
        self._seed = None
        self._initialized = True

    def set_seed(self, seed: int):
        """Sets a fixed seed for reproducible pseudorandom fluctuations."""
        with self._lock:
            self._seed = seed
            self._random.seed(seed)

    def set_deterministic(self, deterministic: bool):
        """Toggles deterministic test mode for automated test suites."""
        with self._lock:
            self._deterministic = bool(deterministic)
            if self._deterministic and self._seed is None:
                self._seed = 42
                self._random.seed(42)

    def is_running(self):
        with self._lock:
            return self._running and not self._paused

    def is_paused(self):
        with self._lock:
            return self._paused

    def get_status(self):
        with self._lock:
            now = time.time()
            elapsed_since_tick = round(now - self._last_tick_time, 1)
            next_update = max(0.0, round(self.interval_seconds - elapsed_since_tick, 1)) if (self._running and not self._paused) else self.interval_seconds
            return {
                "running": self._running,
                "paused": self._paused,
                "interval_seconds": self.interval_seconds,
                "tick_count": self._tick_count,
                "deterministic": self._deterministic,
                "next_update_seconds": next_update,
                "last_tick_time": datetime.fromtimestamp(self._last_tick_time).strftime("%Y-%m-%d %H:%M:%S") if self._last_tick_time else ""
            }

    def start(self):
        """Starts the authoritative background simulation thread (idempotent)."""
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                self._running = True
                self._paused = False
                return
            self._running = True
            self._paused = False
            self._last_tick_time = time.time()
            self._thread = threading.Thread(target=self._worker_loop, name="LivePowerSimulatorThread", daemon=True)
            self._thread.start()

    def pause(self):
        """Pauses the simulation updates without altering room states."""
        with self._lock:
            self._paused = True

    def resume(self):
        """Resumes simulation updates from current state."""
        with self._lock:
            self._paused = False
            self._last_tick_time = time.time()

    def stop(self):
        """Stops the background worker thread."""
        with self._lock:
            self._running = False

    def reset(self, operator="Hostel Warden"):
        """Safely resets demo rooms to benchmark without deleting historical events."""
        from services.room_manager import RoomManager
        mgr = RoomManager()
        res = mgr.reset_demo_simulation_state(operator=operator)
        with self._lock:
            self._last_tick_time = time.time()
            self._tick_count = 0
        return res

    def set_room_profile(self, room_id: str, profile: str):
        """Assigns an explicit simulation profile to a room."""
        valid_profiles = [
            "NORMAL_OCCUPIED", "LIKELY_VACANT", "HIGH_USAGE",
            "OPTIMIZING", "MANUAL_OFF", "TRIPPED", "SENSOR_OFFLINE"
        ]
        norm_profile = str(profile).upper().strip()
        if norm_profile not in valid_profiles:
            return {"success": False, "error": f"Invalid profile '{profile}'. Must be one of: {', '.join(valid_profiles)}"}

        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("UPDATE rooms SET simulation_profile = ? WHERE room_id = ?", (norm_profile, room_id))
            conn.commit()
            return {"success": True, "room_id": room_id, "simulation_profile": norm_profile}
        finally:
            conn.close()

    def _worker_loop(self):
        """Continuous background loop running every interval_seconds."""
        while self._running:
            try:
                if not self._paused:
                    now = time.time()
                    elapsed = now - self._last_tick_time
                    if elapsed >= self.interval_seconds:
                        self.step(elapsed_seconds=elapsed)
                        self._last_tick_time = now
            except Exception as e:
                print(f"[LivePowerSimulator] Error during background step: {e}")

            # Sleep in short increments so pause/stop is responsive
            time.sleep(0.5)

    def step(self, elapsed_seconds=None):
        """
        Executes one authoritative simulation step across all rooms.
        Can be called by background thread or synchronously during test execution.
        """
        with self._lock:
            if elapsed_seconds is None:
                elapsed_seconds = self.interval_seconds
            elapsed_seconds = max(0.1, float(elapsed_seconds))
            elapsed_hours = elapsed_seconds / 3600.0

            conn = get_db_connection()
            try:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM rooms")
                rooms = [dict(r) for r in cursor.fetchall()]
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                updated_rooms = []
                for room in rooms:
                    rid = room["room_id"]
                    updated = self._simulate_room_step(room, elapsed_hours, timestamp)
                    
                    cursor.execute("""
                        UPDATE rooms
                        SET power_w = ?,
                            previous_power_w = ?,
                            power_change_w = ?,
                            power_change_pct = ?,
                            voltage_v = ?,
                            current_a = ?,
                            power_factor = ?,
                            energy_kwh = ?,
                            room_state = ?,
                            optimization_state = ?,
                            excess_power_w = ?,
                            trip_reason = ?,
                            simulation_profile = ?,
                            last_update = ?
                        WHERE room_id = ?
                    """, (
                        updated["power_w"],
                        updated["previous_power_w"],
                        updated["power_change_w"],
                        updated["power_change_pct"],
                        updated["voltage_v"],
                        updated["current_a"],
                        updated["power_factor"],
                        updated["energy_kwh"],
                        updated["room_state"],
                        updated["optimization_state"],
                        updated["excess_power_w"],
                        updated["trip_reason"],
                        updated["simulation_profile"],
                        timestamp,
                        rid
                    ))
                    updated_rooms.append(updated)

                conn.commit()
                self._tick_count += 1
                return {
                    "success": True,
                    "tick_count": self._tick_count,
                    "elapsed_seconds": elapsed_seconds,
                    "rooms_updated": len(updated_rooms),
                    "rooms": updated_rooms
                }
            finally:
                conn.close()

    def _simulate_room_step(self, room: dict, elapsed_hours: float, timestamp: str) -> dict:
        """
        Computes the next physical electrical reading for an individual room.
        Guarantees independent state and physical consistency between V, I, W, PF, kWh.
        """
        prev_w = float(room.get("power_w") or 0.0)
        prev_v = float(room.get("voltage_v") or 230.0)
        prev_pf = float(room.get("power_factor") or 0.95)
        prev_kwh = float(room.get("energy_kwh") or 0.0)
        threshold_w = float(room.get("threshold_w") or 1200.0)
        opt_target_w = float(room.get("optimization_target_w") or 800.0)
        
        sensor_status = room.get("sensor_status") or "ONLINE"
        room_state = room.get("room_state") or "NORMAL"
        opt_state = room.get("optimization_state") or "NORMAL"
        relay_state = room.get("relay_state") or "CLOSED"
        sw_state = room.get("switch_state") or "ON"
        eff_sw_state = room.get("effective_switch_state") or sw_state
        manual_lock = int(room.get("manual_off_lock") or 0)
        stored_profile = str(room.get("simulation_profile") or "NORMAL_OCCUPIED").upper()
        trip_reason = room.get("trip_reason") or ""

        # -------------------------------------------------------------
        # 1. Condition: Sensor Offline
        # Telemetry is unavailable. Do NOT generate new sensor readings.
        # -------------------------------------------------------------
        if sensor_status == "OFFLINE":
            return {
                "room_id": room["room_id"],
                "power_w": 0.0,
                "previous_power_w": prev_w,
                "power_change_w": 0.0,
                "power_change_pct": 0.0,
                "voltage_v": 0.0,
                "current_a": 0.0,
                "power_factor": prev_pf,
                "energy_kwh": prev_kwh,
                "room_state": "SENSOR_OFFLINE",
                "optimization_state": "SENSOR_OFFLINE",
                "excess_power_w": 0.0,
                "trip_reason": trip_reason or "Sensor node telemetry offline",
                "simulation_profile": "SENSOR_OFFLINE"
            }

        # -------------------------------------------------------------
        # 2. Condition: Confirmed / Latched Trip
        # Circuit de-energized. Power must remain 0.0 W. Never auto-cleared.
        # -------------------------------------------------------------
        is_tripped = (room_state in ("TRIPPED_SIMULATED", "TRIPPED_CRITICAL") or relay_state == "TRIPPED_SIMULATED")
        if is_tripped:
            return {
                "room_id": room["room_id"],
                "power_w": 0.0,
                "previous_power_w": prev_w,
                "power_change_w": round(0.0 - prev_w, 1) if prev_w > 0 else 0.0,
                "power_change_pct": -100.0 if prev_w > 0 else 0.0,
                "voltage_v": prev_v,
                "current_a": 0.0,
                "power_factor": prev_pf,
                "energy_kwh": prev_kwh,
                "room_state": room_state,
                "optimization_state": room_state,
                "excess_power_w": 0.0,
                "trip_reason": trip_reason,
                "simulation_profile": "TRIPPED"
            }

        # -------------------------------------------------------------
        # 3. Condition: Manual OFF Lock / Circuit OFF
        # Main switch is open. Power must remain 0.0 W.
        # -------------------------------------------------------------
        if eff_sw_state == "OFF" or sw_state == "OFF" or manual_lock == 1 or room_state == "MANUAL_OFF":
            return {
                "room_id": room["room_id"],
                "power_w": 0.0,
                "previous_power_w": prev_w,
                "power_change_w": round(0.0 - prev_w, 1) if prev_w > 0 else 0.0,
                "power_change_pct": -100.0 if prev_w > 0 else 0.0,
                "voltage_v": prev_v,
                "current_a": 0.0,
                "power_factor": prev_pf,
                "energy_kwh": prev_kwh,
                "room_state": "MANUAL_OFF",
                "optimization_state": "MANUAL_OFF",
                "excess_power_w": 0.0,
                "trip_reason": trip_reason,
                "simulation_profile": "MANUAL_OFF"
            }

        # -------------------------------------------------------------
        # Active Energized Room: Determine next power via Room Profile
        # -------------------------------------------------------------
        profile = stored_profile
        # If room_state was set to HIGH_USAGE or OPTIMIZING, align profile
        if opt_state == "OPTIMIZING" or profile == "OPTIMIZING":
            profile = "OPTIMIZING"
        elif room_state == "HIGH_USAGE" or profile == "HIGH_USAGE":
            profile = "HIGH_USAGE"
        elif str(room.get("occupancy_state", "")).lower() == "likely vacant" and profile not in ("HIGH_USAGE", "OPTIMIZING"):
            profile = "LIKELY_VACANT"

        new_w = prev_w
        new_room_state = room_state
        new_opt_state = opt_state

        if profile == "LIKELY_VACANT":
            # 0 - 35 W standby range, small random walk
            if prev_w <= 0.0 or prev_w > 35.0:
                base = 18.0
            else:
                base = prev_w
            
            delta = self._get_random_delta(-2.5, 2.5)
            new_w = round(max(5.0, min(35.0, base + delta)), 1)
            new_room_state = "NORMAL"
            new_opt_state = "NORMAL"

        elif profile == "HIGH_USAGE":
            # Gradual climb through: 750W -> 920W -> 1150W -> 1320W -> 1450W
            if prev_w < 700.0:
                base = 750.0
            else:
                base = prev_w

            if base < 1550.0:
                # Step increase
                step_inc = self._get_random_delta(70.0, 150.0)
                new_w = round(min(1600.0, base + step_inc), 1)
            else:
                # High plateau with small flutter
                flutter = self._get_random_delta(-20.0, 25.0)
                new_w = round(max(1300.0, min(1650.0, base + flutter)), 1)

            if new_w > threshold_w:
                new_room_state = "HIGH_USAGE"
                new_opt_state = "HIGH_USAGE"
                trip_reason = f"Active power ({new_w} W) exceeds configured limit ({threshold_w} W)."
            else:
                new_room_state = "NORMAL"
                new_opt_state = "NORMAL"

        elif profile == "OPTIMIZING":
            # Gradual step reduction towards optimization target (e.g. 800 W)
            # Example: 1500 W -> 1320 W -> 1140 W -> 980 W -> 820 W
            if prev_w <= opt_target_w + 30.0:
                # Target achieved: settle around target
                flutter = self._get_random_delta(-15.0, 15.0)
                new_w = round(max(opt_target_w - 40.0, min(opt_target_w + 30.0, opt_target_w + flutter)), 1)
                new_room_state = "NORMAL"
                new_opt_state = "OPTIMIZED"
                profile = "NORMAL_OCCUPIED"
            else:
                # Step reduction
                step_red = self._get_random_delta(120.0, 200.0)
                new_w = round(max(opt_target_w, prev_w - step_red), 1)
                if new_w <= opt_target_w + 50.0:
                    new_room_state = "NORMAL"
                    new_opt_state = "OPTIMIZED"
                    profile = "NORMAL_OCCUPIED"
                else:
                    new_room_state = "HIGH_USAGE" if new_w > threshold_w else "NORMAL"
                    new_opt_state = "OPTIMIZATION_PARTIAL"

        else: # NORMAL_OCCUPIED
            # 50 - 700 W range, natural random walk from previous reading
            if prev_w < 50.0 or prev_w > 700.0:
                base = 95.0
            else:
                base = prev_w

            # 85% ordinary fluctuations (+/- 5 to 25W), 15% appliance step (+/- 45W)
            if self._random.random() < 0.15:
                delta = self._get_random_delta(-45.0, 45.0)
            else:
                delta = self._get_random_delta(-22.0, 22.0)

            new_w = round(max(50.0, min(700.0, base + delta)), 1)
            new_room_state = "NORMAL"
            new_opt_state = "OPTIMIZED" if (new_w <= opt_target_w and opt_state == "OPTIMIZED") else "NORMAL"

        # Calculate delta from previous power
        delta_w = round(new_w - prev_w, 1)
        if prev_w > 0:
            delta_pct = round((delta_w / prev_w) * 100.0, 1)
        else:
            delta_pct = 0.0

        # Physical Voltage calculation: slight natural fluctuation around 230V (+/- 0.4V)
        v_delta = self._get_random_delta(-0.4, 0.4)
        new_v = round(max(226.5, min(233.5, (prev_v if prev_v > 200 else 230.0) + v_delta)), 1)

        # Power Factor: realistic 0.93 to 0.98
        pf_delta = self._get_random_delta(-0.01, 0.01)
        new_pf = round(max(0.92, min(0.98, (prev_pf if prev_pf > 0.8 else 0.95) + pf_delta)), 2)

        # Physical Current calculation: I = P / (V * PF)
        if new_w > 0:
            new_a = round(new_w / (new_v * new_pf), 2)
        else:
            new_a = 0.0

        # Cumulative Energy: Strictly monotonic, E_new = E_prev + (P * dt / 1000)
        energy_inc = (new_w * elapsed_hours) / 1000.0
        new_kwh = round(prev_kwh + energy_inc, 4)

        excess_power_w = max(0.0, round(new_w - threshold_w, 1))

        return {
            "room_id": room["room_id"],
            "power_w": new_w,
            "previous_power_w": prev_w,
            "power_change_w": delta_w,
            "power_change_pct": delta_pct,
            "voltage_v": new_v,
            "current_a": new_a,
            "power_factor": new_pf,
            "energy_kwh": new_kwh,
            "room_state": new_room_state,
            "optimization_state": new_opt_state,
            "excess_power_w": excess_power_w,
            "trip_reason": trip_reason if new_w > threshold_w else (trip_reason if is_tripped else ""),
            "simulation_profile": profile
        }

    def _get_random_delta(self, min_val: float, max_val: float) -> float:
        """Returns bounded fluctuation delta, using deterministic math if enabled."""
        if self._deterministic:
            # Deterministic pseudo-variation based on tick count
            cycle = (self._tick_count % 5) / 5.0
            return min_val + (max_val - min_val) * cycle
        return self._random.uniform(min_val, max_val)

# Global singleton instance
live_simulator = LivePowerSimulator()

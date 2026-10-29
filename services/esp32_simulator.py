import json
import random
from datetime import datetime
from config import Config
from database import get_db_connection

class ESP32FanSimulator:
    """
    Virtual ESP32 Fan Controller Simulation Engine.
    Provides a safe, sandbox simulation of edge IoT fan speed regulation and occupancy-triggered
    eco-throttling without physical GPIO or hardware switching.
    """
    def __init__(self):
        self.disclaimer = (
            "VIRTUAL SIMULATION ONLY: This module runs entirely in software sandbox mode. "
            "No physical relays or electrical circuits are commanded. All telemetry, RPMs, "
            "and duty cycles are simulated."
        )

    def get_devices(self):
        """Returns list of all registered virtual ESP32 fan controllers."""
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM esp32_devices ORDER BY device_id ASC")
        rows = [dict(r) for r in cursor.fetchall()]
        conn.close()

        # Add live calculated telemetry
        for d in rows:
            speed = d["fan_speed_percent"]
            # Power curve: P = P_rated * (speed/100)^2.4 (cube/affinity law for fans)
            # 75W rated ceiling fan at 100% speed
            calc_w = round(75.0 * ((speed / 100.0) ** 2.2), 1)
            rpm = int(350 * (speed / 100.0))
            d["simulated_watts"] = calc_w
            d["simulated_rpm"] = rpm
            d["safe_simulation_flag"] = True

        return rows

    def send_command(self, device_id, command_type, value, triggered_by="USER_SIMULATION"):
        """
        Executes a simulated command on the virtual ESP32 node.
        command_type: 'SET_SPEED' (0-100), 'SET_MODE' ('ECO_MODE', 'ONLINE', 'MANUAL'), 'AUTO_TOGGLE' (1/0)
        """
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM esp32_devices WHERE device_id = ?", (device_id,))
        device = cursor.fetchone()
        if not device:
            conn.close()
            return {"success": False, "error": f"Device {device_id} not found."}

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        response_msg = ""
        new_speed = device["fan_speed_percent"]
        new_status = device["status"]
        new_auto = device["auto_mode"]

        if command_type == "SET_SPEED":
            speed_val = max(0, min(100, int(value)))
            new_speed = speed_val
            response_msg = f"Virtual PWM duty cycle set to {speed_val}% ({int(350 * speed_val/100)} RPM)."

        elif command_type == "SET_MODE":
            if value == "ECO_MODE":
                new_status = "ECO_MODE"
                new_speed = 35 # Eco duty cycle
                response_msg = "Switched to ECO_MODE (Duty cycle restricted to 35% for ambient thermal comfort)."
            elif value == "ONLINE":
                new_status = "ONLINE"
                response_msg = "Switched to standard ONLINE mode."
            elif value == "MANUAL_OVERRIDE":
                new_status = "MANUAL_OVERRIDE"
                response_msg = "Switched to MANUAL_OVERRIDE mode."

        elif command_type == "AUTO_TOGGLE":
            new_auto = 1 if int(value) == 1 else 0
            response_msg = f"Autonomous AI occupancy tracking {'enabled' if new_auto else 'disabled'}."

        # Compute updated current draw
        calc_draw_w = round(75.0 * ((new_speed / 100.0) ** 2.2), 1)

        # Update device in DB
        cursor.execute("""
            UPDATE esp32_devices
            SET fan_speed_percent = ?, status = ?, auto_mode = ?,
                last_heartbeat = ?, current_draw_w = ?
            WHERE device_id = ?
        """, (new_speed, new_status, new_auto, timestamp, calc_draw_w, device_id))

        # Log simulated action
        cursor.execute("""
            INSERT INTO esp32_logs (device_id, timestamp, command, triggered_by, response)
            VALUES (?, ?, ?, ?, ?)
        """, (device_id, timestamp, f"{command_type}:{value}", triggered_by, response_msg))

        conn.commit()
        conn.close()

        return {
            "success": True,
            "device_id": device_id,
            "new_speed_percent": new_speed,
            "new_status": new_status,
            "current_draw_w": calc_draw_w,
            "message": response_msg,
            "disclaimer": self.disclaimer
        }

    def get_logs(self, limit=25):
        """Retrieves recent simulation activity logs."""
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM esp32_logs ORDER BY id DESC LIMIT ?", (limit,))
        logs = [dict(r) for r in cursor.fetchall()]
        conn.close()
        return logs

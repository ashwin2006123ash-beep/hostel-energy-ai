import sqlite3
import os
import json
from config import Config

def get_db_connection(db_path=None):
    """Returns a SQLite connection with row_factory set to sqlite3.Row for dict-like access."""
    if db_path is None:
        db_path = Config.DATABASE_PATH
    conn = sqlite3.connect(db_path, timeout=30.0)
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA busy_timeout=30000;")
    except Exception:
        pass
    conn.row_factory = sqlite3.Row
    return conn

def init_db(db_path=None):
    """Initializes the SQLite database with all required tables, migrations and indexes."""
    if db_path is None:
        db_path = Config.DATABASE_PATH
        
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    # 1. Readings Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS readings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        block_id TEXT NOT NULL,
        floor INTEGER DEFAULT 1,
        power_kw REAL NOT NULL,
        energy_kwh REAL NOT NULL,
        occupancy INTEGER NOT NULL,
        occupancy_rate REAL NOT NULL,
        temperature REAL NOT NULL,
        humidity REAL NOT NULL,
        day_type TEXT NOT NULL,
        is_synthetic INTEGER DEFAULT 1,
        source TEXT DEFAULT 'synthetic_generator',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # 2. Anomalies Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS anomalies (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        reading_id INTEGER,
        timestamp TEXT NOT NULL,
        block_id TEXT NOT NULL,
        actual_kw REAL NOT NULL,
        expected_kw REAL NOT NULL,
        residual_kw REAL NOT NULL,
        anomaly_score REAL NOT NULL,
        severity TEXT NOT NULL,
        primary_cause TEXT NOT NULL,
        cause_ranking_json TEXT NOT NULL,
        status TEXT DEFAULT 'pending',
        notes TEXT,
        room_number TEXT DEFAULT 'Room 101',
        occupancy_status TEXT DEFAULT 'likely vacant',
        recommended_action TEXT DEFAULT 'Inspect room for unattended appliances',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (reading_id) REFERENCES readings(id)
    );
    """)

    # Migration check for anomalies table existing columns
    cursor.execute("PRAGMA table_info(anomalies)")
    existing_cols = [c[1] for c in cursor.fetchall()]
    if "room_number" not in existing_cols:
        cursor.execute("ALTER TABLE anomalies ADD COLUMN room_number TEXT DEFAULT 'Room 101'")
    if "occupancy_status" not in existing_cols:
        cursor.execute("ALTER TABLE anomalies ADD COLUMN occupancy_status TEXT DEFAULT 'likely vacant'")
    if "recommended_action" not in existing_cols:
        cursor.execute("ALTER TABLE anomalies ADD COLUMN recommended_action TEXT DEFAULT 'Inspect room for unattended appliances'")

    # Normalize old status values if present
    cursor.execute("UPDATE anomalies SET status = 'pending' WHERE status = 'New'")

    # Populate room numbers and occupancy statuses for existing records if default
    cursor.execute("SELECT id, block_id, actual_kw, expected_kw FROM anomalies WHERE room_number = 'Room 101'")
    rows_to_update = cursor.fetchall()
    for r in rows_to_update:
        aid = r["id"]
        # Generate realistic room number based on floor and id: e.g. Floor 2 -> Room 201 to 215
        floor_calc = (aid % 3) + 1
        room_num = f"Room {floor_calc * 100 + ((aid % 15) + 1):03d}"
        
        # Determine occupancy state
        # If actual_kw > 10, likely vacant with high draw; else occupied or unknown
        if r["actual_kw"] > r["expected_kw"] + 4.0:
            occ_status = "likely vacant"
        elif aid % 3 == 0:
            occ_status = "unknown"
        else:
            occ_status = "occupied"

        # Actionable recommendations
        if r["actual_kw"] > 10.0:
            action = "Dispatch floor prefect to turn off unattended room cooler or water heater."
        elif occ_status == "likely vacant":
            action = "Check for left-on lighting and ceiling fans in unoccupied room."
        else:
            action = "Routine check of high-draw study appliances and power extension boards."

        cursor.execute("""
            UPDATE anomalies
            SET room_number = ?, occupancy_status = ?, recommended_action = ?
            WHERE id = ?
        """, (room_num, occ_status, action, aid))

    # 3. Electrical Fault Early Warnings Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS fault_warnings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        block_id TEXT NOT NULL,
        pattern_type TEXT NOT NULL,
        first_detected TEXT NOT NULL,
        last_detected TEXT NOT NULL,
        persistence_days INTEGER NOT NULL,
        severity TEXT NOT NULL,
        baseline_drift_kw REAL NOT NULL,
        diagnostic_evidence TEXT NOT NULL,
        recommended_inspection TEXT NOT NULL,
        resolved INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # 4. Verified Savings Actions Table (M&V Engine)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS savings_actions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        action_title TEXT NOT NULL,
        action_type TEXT NOT NULL,
        block_id TEXT NOT NULL,
        implementation_date TEXT NOT NULL,
        baseline_period_start TEXT NOT NULL,
        baseline_period_end TEXT NOT NULL,
        post_period_start TEXT NOT NULL,
        post_period_end TEXT NOT NULL,
        weather_adjusted_baseline_kwh REAL NOT NULL,
        actual_post_kwh REAL NOT NULL,
        verified_savings_kwh REAL NOT NULL,
        verified_cost_saved_inr REAL NOT NULL,
        verified_co2_saved_kg REAL NOT NULL,
        status TEXT DEFAULT 'Verified',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # 5. Incident Memory: "Learn Once, Act Smart" Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS incident_memory (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        block_id TEXT NOT NULL,
        room_number TEXT NOT NULL,
        incident_date TEXT NOT NULL,
        anomaly_symptom TEXT NOT NULL,
        confirmed_cause TEXT NOT NULL,
        action_taken TEXT NOT NULL,
        measured_result TEXT NOT NULL,
        savings_kwh_post REAL DEFAULT 0.0,
        savings_inr_post REAL DEFAULT 0.0,
        verified_by TEXT DEFAULT 'Hostel Warden',
        status TEXT DEFAULT 'Verified',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # 6. Virtual ESP32 Fan Devices Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS esp32_devices (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        device_id TEXT UNIQUE NOT NULL,
        block_id TEXT NOT NULL,
        room_number TEXT DEFAULT 'Room 101',
        zone_name TEXT NOT NULL,
        status TEXT DEFAULT 'ONLINE',
        motion_status TEXT DEFAULT 'Motion Detected',
        voltage_v REAL DEFAULT 230.0,
        current_a REAL DEFAULT 0.35,
        fan_speed_percent INTEGER DEFAULT 60,
        auto_mode INTEGER DEFAULT 1,
        last_heartbeat TEXT NOT NULL,
        current_draw_w REAL DEFAULT 75.0,
        simulated_savings_kwh REAL DEFAULT 0.0,
        is_simulation INTEGER DEFAULT 1,
        data_source TEXT DEFAULT 'simulation'
    );
    """)

    # Migration check for esp32_devices columns
    cursor.execute("PRAGMA table_info(esp32_devices)")
    dev_cols = [c[1] for c in cursor.fetchall()]
    if "room_number" not in dev_cols:
        cursor.execute("ALTER TABLE esp32_devices ADD COLUMN room_number TEXT DEFAULT 'Room 101'")
    if "motion_status" not in dev_cols:
        cursor.execute("ALTER TABLE esp32_devices ADD COLUMN motion_status TEXT DEFAULT 'Motion Detected'")
    if "voltage_v" not in dev_cols:
        cursor.execute("ALTER TABLE esp32_devices ADD COLUMN voltage_v REAL DEFAULT 230.0")
    if "current_a" not in dev_cols:
        cursor.execute("ALTER TABLE esp32_devices ADD COLUMN current_a REAL DEFAULT 0.35")
    if "data_source" not in dev_cols:
        cursor.execute("ALTER TABLE esp32_devices ADD COLUMN data_source TEXT DEFAULT 'simulation'")

    # 7. ESP32 Simulation Logs
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS esp32_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        device_id TEXT NOT NULL,
        timestamp TEXT NOT NULL,
        command TEXT NOT NULL,
        triggered_by TEXT NOT NULL,
        response TEXT NOT NULL,
        FOREIGN KEY (device_id) REFERENCES esp32_devices(device_id)
    );
    """)

    # 8. Room-Level Monitoring Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS rooms (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        room_id TEXT UNIQUE NOT NULL,
        block_id TEXT NOT NULL,
        room_number TEXT NOT NULL,
        floor INTEGER DEFAULT 1,
        current_a REAL DEFAULT 0.0,
        voltage_v REAL DEFAULT 230.0,
        power_w REAL DEFAULT 0.0,
        energy_kwh REAL DEFAULT 0.0,
        power_factor REAL DEFAULT 0.95,
        occupancy_state TEXT DEFAULT 'Occupied',
        sensor_status TEXT DEFAULT 'ONLINE',
        room_state TEXT DEFAULT 'NORMAL',
        relay_state TEXT DEFAULT 'CLOSED',
        threshold_w REAL DEFAULT 1200.0,
        empty_threshold_w REAL DEFAULT 35.0,
        trip_reason TEXT DEFAULT '',
        persistence_minutes INTEGER DEFAULT 0,
        last_update TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        data_source TEXT DEFAULT 'simulation'
    );
    """)

    # 9. Room Trip & Anomaly Events Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS room_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id TEXT UNIQUE NOT NULL,
        room_id TEXT NOT NULL,
        block_id TEXT NOT NULL,
        room_number TEXT NOT NULL,
        event_type TEXT NOT NULL,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        observed_power_w REAL NOT NULL,
        threshold_w REAL NOT NULL,
        duration_minutes INTEGER DEFAULT 0,
        occupancy_state TEXT,
        explanation TEXT NOT NULL,
        action_taken TEXT NOT NULL,
        outcome TEXT DEFAULT 'Pending Review',
        simulated INTEGER DEFAULT 1,
        FOREIGN KEY (room_id) REFERENCES rooms(room_id)
    );
    """)

    # 10. System Threshold Settings Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS system_settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL,
        description TEXT
    );
    """)

    # Indexes for fast querying
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_readings_block_time ON readings(block_id, timestamp);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_anomalies_block_time ON anomalies(block_id, timestamp);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_anomalies_severity ON anomalies(severity);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_anomalies_status ON anomalies(status);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_rooms_block ON rooms(block_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_rooms_state ON rooms(room_state);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_room_events_room ON room_events(room_id, timestamp);")

    conn.commit()
    conn.close()

def seed_incident_memory(db_path=None):
    """Seeds verified incident memory cases to demonstrate the 'Learn Once, Act Smart' feature."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM incident_memory")
    if cursor.fetchone()[0] == 0:
        incidents = [
            (
                "Block-A",
                "Room 204",
                "2026-10-08 14:30:00",
                "High power draw (+12.5 kW) during lecture hours with vacant occupancy status",
                "Unattended 1500W electric room heater and 2 desktop monitors left running",
                "Prefect conducted floor sweep, unplugged appliances, and briefed students",
                "Power draw returned to 0.35 kW standby baseline; post-action verified stable",
                16.5,
                151.80,
                "Dr. S. Sharma (Warden, Block-A)",
                "Verified"
            ),
            (
                "Block-C",
                "Room 312",
                "2026-10-12 03:15:00",
                "Unusual late-night surge (+16.0 kW) at 03:00 AM while occupants were sleeping",
                "Common washroom water geyser thermostat stuck ON due to welded relay contacts",
                "Electrician replaced defective 25A contactor relay and installed digital timer",
                "Continuous night creep eliminated; power consumption reduced by 22.4 kWh/day",
                22.4,
                206.08,
                "Prof. K. Sen (Chief Warden)",
                "Verified"
            ),
            (
                "Block-B",
                "Room 105",
                "2026-10-18 11:20:00",
                "Continuous 2.4 kW unvarying draw on empty room circuit over weekend",
                "Gaming PC running continuous GPU machine-learning batch script without sleep timeout",
                "Configured 15-minute idle sleep mode on operating system; student advised on lab servers",
                "Consumption reduced by 11.2 kWh per weekend day",
                11.2,
                103.04,
                "R. Verma (Assistant Warden)",
                "Verified"
            )
        ]
        cursor.executemany("""
            INSERT INTO incident_memory (
                block_id, room_number, incident_date, anomaly_symptom,
                confirmed_cause, action_taken, measured_result,
                savings_kwh_post, savings_inr_post, verified_by, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, incidents)
        conn.commit()
    conn.close()

def seed_esp32_devices(db_path=None):
    """Populates initial simulated ESP32 controllers with room mapping and sensor telemetry."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM esp32_devices")
    if cursor.fetchone()[0] == 0:
        devices = [
            ("ESP32-BLK-A-R102", "Block-A", "Room 102", "Floor 1 Study Room", "ONLINE", "Motion Detected", 231.2, 0.42, 60, 1, "2026-10-29 12:25:00", 72.0, 14.5, 1, "simulation"),
            ("ESP32-BLK-A-R204", "Block-A", "Room 204", "Floor 2 Dormitory Wing", "ONLINE", "No Motion (Vacant)", 229.8, 0.21, 35, 1, "2026-10-29 12:28:15", 48.0, 26.2, 1, "simulation"),
            ("ESP32-BLK-B-R105", "Block-B", "Room 105", "Ground Floor Rec Hall", "ONLINE", "Motion Detected", 232.0, 0.55, 80, 0, "2026-10-29 12:29:00", 96.0, 8.4, 1, "simulation"),
            ("ESP32-BLK-C-R214", "Block-C", "Room 214", "Floor 2 Reading Room", "ONLINE", "No Motion (Vacant)", 230.5, 0.18, 35, 1, "2026-10-29 12:27:40", 42.0, 31.8, 1, "simulation"),
            ("ESP32-BLK-C-R312", "Block-C", "Room 312", "Floor 3 Study Wing", "ONLINE", "Motion Detected", 228.6, 0.38, 50, 1, "2026-10-29 12:29:10", 60.0, 19.3, 1, "simulation"),
            ("ESP32-BLK-D-R202", "Block-D", "Room 202", "Floor 2 Multimedia Room", "STALE", "Unknown (Signal Timeout)", 230.1, 0.45, 70, 1, "2026-10-29 11:45:00", 84.0, 12.1, 1, "simulation")
        ]
        cursor.executemany("""
            INSERT INTO esp32_devices (
                device_id, block_id, room_number, zone_name, status,
                motion_status, voltage_v, current_a, fan_speed_percent,
                auto_mode, last_heartbeat, current_draw_w, simulated_savings_kwh,
                is_simulation, data_source
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, devices)
        conn.commit()
    conn.close()

def seed_rooms(db_path=None):
    """Populates 16 distinct hostel rooms with live electrical, sensor, and state machine values."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM rooms")
    if cursor.fetchone()[0] == 0:
        rooms_data = [
            ("A-101", "Block-A", "Room 101", 1, 1.25, 230.0, 280.0, 3.42, 0.97, "Likely Vacant", "ONLINE", "TRIPPED_SIMULATED", "TRIPPED_SIMULATED", 1200.0, 35.0, "Continuous 280W draw during daytime while vacant > 15 mins. Simulated trip triggered.", 18, "simulation"),
            ("A-102", "Block-A", "Room 102", 1, 0.30, 230.2, 65.0, 1.15, 0.94, "Occupied", "ONLINE", "NORMAL", "CLOSED", 1200.0, 35.0, "", 0, "simulation"),
            ("A-103", "Block-A", "Room 103", 1, 0.65, 229.8, 145.0, 2.20, 0.96, "Occupied", "ONLINE", "NORMAL", "CLOSED", 1200.0, 35.0, "", 0, "simulation"),
            ("A-204", "Block-A", "Room 204", 2, 6.65, 228.5, 1520.0, 8.45, 0.99, "Likely Vacant", "ONLINE", "TRIP_PENDING", "CLOSED", 1200.0, 35.0, "High power excursion (1520W > 1200W threshold) running for 12 minutes.", 12, "simulation"),
            ("B-101", "Block-B", "Room 101", 1, 0.35, 231.0, 75.0, 1.30, 0.93, "Occupied", "ONLINE", "NORMAL", "CLOSED", 1200.0, 35.0, "", 0, "simulation"),
            ("B-105", "Block-B", "Room 105", 1, 8.12, 227.4, 1850.0, 10.20, 0.99, "Occupied", "ONLINE", "HIGH_USAGE", "CLOSED", 1200.0, 35.0, "Abrupt spike: 1850W induction/heater exceeding 1200W limit.", 8, "simulation"),
            ("B-202", "Block-B", "Room 202", 2, 0.13, 230.2, 28.0, 0.65, 0.90, "Likely Vacant", "ONLINE", "NORMAL", "CLOSED", 1200.0, 35.0, "", 0, "simulation"),
            ("B-204", "Block-B", "Room 204", 2, 0.00, 0.0, 0.0, 0.0, 0.0, "Unknown", "OFFLINE", "SENSOR_OFFLINE", "CLOSED", 1200.0, 35.0, "Sensor telemetry timeout; hardware disconnected.", 0, "simulation"),
            ("C-101", "Block-C", "Room 101", 1, 0.38, 230.5, 85.0, 1.45, 0.95, "Occupied", "ONLINE", "NORMAL", "CLOSED", 1200.0, 35.0, "", 0, "simulation"),
            ("C-102", "Block-C", "Room 102", 1, 0.40, 229.9, 90.0, 1.50, 0.95, "Occupied", "STALE", "DATA_STALE", "CLOSED", 1200.0, 35.0, "Last heartbeat delayed by 38 minutes.", 38, "simulation"),
            ("C-201", "Block-C", "Room 201", 2, 9.25, 226.5, 2100.0, 14.80, 1.00, "Likely Vacant", "ONLINE", "ANOMALY_DETECTED", "CLOSED", 1200.0, 35.0, "Continuous geyser-like 2100W load persistent > 45 minutes.", 52, "simulation"),
            ("C-312", "Block-C", "Room 312", 3, 0.48, 230.2, 110.0, 2.10, 0.95, "Occupied", "ONLINE", "NORMAL", "CLOSED", 1200.0, 35.0, "", 0, "simulation"),
            ("D-101", "Block-D", "Room 101", 1, 0.25, 231.4, 55.0, 0.95, 0.92, "Occupied", "ONLINE", "NORMAL", "CLOSED", 1200.0, 35.0, "", 0, "simulation"),
            ("D-104", "Block-D", "Room 104", 1, 0.51, 230.0, 115.0, 1.85, 0.96, "Occupied", "ONLINE", "NORMAL", "CLOSED", 1200.0, 35.0, "", 0, "simulation"),
            ("D-202", "Block-D", "Room 202", 2, 0.32, 230.8, 72.0, 1.25, 0.94, "Occupied", "ONLINE", "NORMAL", "CLOSED", 1200.0, 35.0, "", 0, "simulation"),
            ("D-205", "Block-D", "Room 205", 2, 5.92, 228.0, 1350.0, 9.10, 0.99, "Likely Vacant", "ONLINE", "TRIPPED_SIMULATED", "TRIPPED_SIMULATED", 1200.0, 35.0, "Sustained high load in vacant room > 15 mins. Simulated trip triggered.", 20, "simulation")
        ]
        cursor.executemany("""
            INSERT INTO rooms (
                room_id, block_id, room_number, floor, current_a, voltage_v,
                power_w, energy_kwh, power_factor, occupancy_state,
                sensor_status, room_state, relay_state, threshold_w,
                empty_threshold_w, trip_reason, persistence_minutes, data_source
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, rooms_data)
        
        # Seed initial sample events
        events = [
            ("EVT-20261029-A101-01", "A-101", "Block-A", "Room 101", "TRIP_SIMULATED", 280.0, 35.0, 18, "Likely Vacant", "Continuous 280W draw during daytime while vacant exceeded 35W threshold for 18 minutes.", "Simulated cutoff relay opened (SIMULATION ONLY)", "Tripped", 1),
            ("EVT-20261029-D205-01", "D-205", "Block-D", "Room 205", "TRIP_SIMULATED", 1350.0, 1200.0, 20, "Likely Vacant", "Sustained load of 1350W exceeded 1200W threshold in vacant room for 20 minutes.", "Simulated cutoff relay opened (SIMULATION ONLY)", "Tripped", 1),
            ("EVT-20261029-B105-01", "B-105", "Block-B", "Room 105", "HIGH_USAGE", 1850.0, 1200.0, 8, "Occupied", "Abrupt high-power appliance spike of 1850W above 1200W threshold.", "Warning alert issued to floor staff", "Under Observation", 1)
        ]
        cursor.executemany("""
            INSERT INTO room_events (
                event_id, room_id, block_id, room_number, event_type,
                observed_power_w, threshold_w, duration_minutes,
                occupancy_state, explanation, action_taken, outcome, simulated
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, events)
        conn.commit()
    conn.close()

def seed_system_settings(db_path=None):
    """Seeds configurable operational energy thresholds and duration policies."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM system_settings")
    if cursor.fetchone()[0] == 0:
        settings = [
            ("daytime_start", "07:00", "Start of daytime energy policy window (HH:MM)"),
            ("daytime_end", "18:00", "End of daytime energy policy window (HH:MM)"),
            ("empty_room_threshold_w", "35.0", "Maximum permissible continuous wattage for vacant rooms (W)"),
            ("high_power_threshold_w", "1200.0", "Maximum permissible room power before warning / trip simulation (W)"),
            ("persistence_window_min", "15", "Minimum persistence duration required to trigger vacant-room simulated trip (minutes)"),
            ("geyser_persistence_min", "45", "Continuous high-draw geyser limit before critical persistent alert (minutes)"),
            ("data_freshness_limit_min", "30", "Sensor heartbeat timeout threshold before flagging DATA STALE (minutes)"),
            ("real_hardware_relay_enabled", "0", "SAFETY LOCK: 0 = simulated relay cutoff only; physical hardware control disabled")
        ]
        cursor.executemany("INSERT INTO system_settings (key, value, description) VALUES (?, ?, ?)", settings)
        conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
    seed_incident_memory()
    seed_esp32_devices()
    seed_rooms()
    seed_system_settings()


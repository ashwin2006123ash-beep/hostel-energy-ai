import os
import random
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from config import Config

def generate_hostel_telemetry(
    start_date=None,
    num_days=30,
    interval_minutes=60,
    output_csv=None,
    seed=Config.RANDOM_SEED
):
    """
    Generates realistic, context-aware synthetic electrical telemetry for 4 campus hostel blocks.
    Clearly labelled with is_synthetic=1 and ground_truth_label annotations.
    """
    random.seed(seed)
    np.random.seed(seed)

    if start_date is None:
        # Default: 30 days prior to current date
        start_date = datetime(2026, 10, 1, 0, 0, 0)
    elif isinstance(start_date, str):
        start_date = datetime.fromisoformat(start_date)

    blocks = Config.HOSTEL_BLOCKS
    total_steps = int((num_days * 24 * 60) / interval_minutes)
    
    rows = []

    for block_id, block_info in blocks.items():
        capacity = block_info["capacity"]
        floors = block_info["floors"]
        base_power_kw = 2.5 * (capacity / 100.0) # Basal standby power: routers, security, corridor base lighting

        # Baseline drift tracker for simulating creeping electrical faults in Block-B
        creep_offset_kw = 0.0

        for step in range(total_steps):
            current_time = start_date + timedelta(minutes=step * interval_minutes)
            hour = current_time.hour
            minute = current_time.minute
            day_of_week = current_time.weekday() # 0 = Monday, 6 = Sunday
            is_weekend = day_of_week in [5, 6]
            day_num = step // (24 * (60 // interval_minutes))

            # Simulate special day types (e.g. Day 18-20 are Exam Days)
            if 18 <= day_num <= 21:
                day_type = "Exam_Day"
            elif is_weekend:
                day_type = "Weekend"
            else:
                day_type = "Weekday"

            # 1. Temperature modeling (°C)
            # Daily sinusoidal wave: min at 5 AM (22°C), max at 2 PM (34°C), plus seasonal noise
            temp_diurnal = 28.0 + 6.0 * np.sin((hour - 9) * np.pi / 12) + np.random.normal(0, 0.8)
            temperature = round(float(np.clip(temp_diurnal, 18.0, 42.0)), 1)
            humidity = round(float(np.clip(75.0 - (temperature - 22.0) * 2.2 + np.random.normal(0, 2.0), 30.0, 95.0)), 1)

            # 2. Occupancy Profile Modeling
            if day_type == "Exam_Day":
                if 0 <= hour < 4:
                    occ_ratio = 0.88 # Late night group studying
                elif 4 <= hour < 8:
                    occ_ratio = 0.70 # Sleep
                elif 8 <= hour < 14:
                    occ_ratio = 0.35 # In exam hall
                elif 14 <= hour < 20:
                    occ_ratio = 0.85 # Returning to study
                else:
                    occ_ratio = 0.95
            elif day_type == "Weekend":
                if 0 <= hour < 9:
                    occ_ratio = 0.85 # Sleeping in
                elif 9 <= hour < 17:
                    occ_ratio = 0.65 # Hanging out in rooms / campus
                elif 17 <= hour < 22:
                    occ_ratio = 0.75 # Socializing / games
                else:
                    occ_ratio = 0.90
            else: # Regular Weekday
                if 0 <= hour < 6:
                    occ_ratio = 0.92 # Sleeping in rooms
                elif 6 <= hour < 9:
                    occ_ratio = 0.88 # Waking up, showers, breakfast
                elif 9 <= hour < 17:
                    occ_ratio = 0.18 # At academic departments & labs
                elif 17 <= hour < 21:
                    occ_ratio = 0.82 # Evening return & recreation
                else:
                    occ_ratio = 0.93 # Night study & prep

            # Add random occupant fluctuation
            occupancy_count = int(np.clip(capacity * occ_ratio + np.random.normal(0, 4), 0, capacity))
            actual_occ_ratio = round(occupancy_count / float(capacity), 3)

            # 3. Contextual Power Calculation (kW)
            # Components:
            # - Basal standby load
            # - Lighting load (dependent on hour and occupancy)
            # - Fan / cooling load (dependent on temperature and occupancy)
            # - Plug & high-draw loads (laptops, geysers during morning, charging)
            
            # Morning geyser surge (6 AM to 8:30 AM)
            geyser_load = 0.0
            if 6 <= hour <= 8:
                geyser_factor = 0.045 * capacity * (1.0 if not is_weekend else 0.7)
                geyser_load = np.random.normal(geyser_factor, geyser_factor * 0.15)

            # Lighting load
            lighting_load = 0.0
            if hour >= 18 or hour < 6:
                lighting_load = 0.018 * occupancy_count + (0.5 * floors) # room lights + corridor
            elif 6 <= hour < 9 or (16 <= hour < 18 and humidity > 80):
                lighting_load = 0.008 * occupancy_count + (0.3 * floors)

            # Fan & cooling load (thermal comfort sensitive)
            temp_excess = max(0.0, temperature - 24.0)
            cooling_load = (0.025 * occupancy_count) * (1.0 + 0.08 * temp_excess)

            # Plug loads (laptops, study lamps, phones)
            plug_load = 0.035 * occupancy_count * (1.2 if day_type == "Exam_Day" else 1.0)

            # Base synthetic power
            simulated_kw = base_power_kw + geyser_load + lighting_load + cooling_load + plug_load
            simulated_kw += np.random.normal(0, 0.4) # Normal telemetry sensor jitter
            simulated_kw = max(1.2, simulated_kw)

            # 4. Inject Realistic Ground-Truth Anomalies & Fault Patterns
            ground_truth_label = "NORMAL"
            ground_truth_note = "Normal contextual consumption"

            # Anomaly 1: Unoccupied Class-Hours High-Power Anomaly in Block-A (Day 7, 11:00 to 14:00)
            if block_id == "Block-A" and day_num == 7 and 11 <= hour <= 14:
                simulated_kw += 12.5 # e.g., Unmonitored heaters / air conditioners left running in empty rooms
                ground_truth_label = "ANOMALY_EMPTY_ROOM_HIGH_DRAW"
                ground_truth_note = "High power draw (12.5 kW excess) during class hours with low occupancy (18%)"

            # Anomaly 2: Midnight Spikes in Block-C (Day 12, 02:00 to 04:00)
            if block_id == "Block-C" and day_num == 12 and 2 <= hour <= 4:
                simulated_kw += 16.0 # e.g. unauthorized heating coils or geyser timer bypass
                ground_truth_label = "ANOMALY_LATE_NIGHT_SPIKE"
                ground_truth_note = "Unusual 16.0 kW surge at 03:00 AM while occupants are sleeping"

            # Anomaly 3: Persistent Basal Leakage / Electrical Fault Creep in Block-B (Day 22 onwards)
            if block_id == "Block-B" and day_num >= 22:
                creep_offset_kw = min(6.8, (day_num - 21) * 1.1)
                simulated_kw += creep_offset_kw
                ground_truth_label = "FAULT_PERSISTENT_BASELOAD_CREEP"
                ground_truth_note = f"Continuous baseline elevation (+{round(creep_offset_kw, 1)} kW) across 24h, indicating potential insulation leakage or circuit fault"

            # Anomaly 4: Extreme Hot Afternoon Spike in Block-D (Day 15, 14:00 to 16:00)
            if block_id == "Block-D" and day_num == 15 and 14 <= hour <= 16:
                simulated_kw += 11.0
                ground_truth_label = "ANOMALY_HVAC_SURGE"
                ground_truth_note = "Heavy cooling load excursion during peak ambient heat (39°C)"

            # Floor distribution breakdown (sample floor 1-4)
            # Power in kW for interval of interval_minutes -> Energy in kWh
            energy_kwh = round(simulated_kw * (interval_minutes / 60.0), 3)

            rows.append({
                "timestamp": current_time.strftime("%Y-%m-%d %H:%M:%S"),
                "block_id": block_id,
                "floor": random.choice(range(1, floors + 1)),
                "power_kw": round(float(simulated_kw), 2),
                "energy_kwh": energy_kwh,
                "occupancy": occupancy_count,
                "occupancy_rate": actual_occ_ratio,
                "temperature": temperature,
                "humidity": humidity,
                "day_type": day_type,
                "is_synthetic": 1,
                "ground_truth_label": ground_truth_label,
                "ground_truth_note": ground_truth_note,
                "source": "synthetic_generator"
            })

    df = pd.DataFrame(rows)

    if output_csv is None:
        output_csv = Config.SAMPLE_DATA_PATH

    os.makedirs(os.path.dirname(output_csv), exist_ok=True)
    df.to_csv(output_csv, index=False)
    print(f"Generated {len(df)} synthetic telemetry records saved to: {output_csv}")
    return df

def seed_database_with_telemetry(db_path=None, csv_path=None):
    """Loads telemetry from CSV into the SQLite readings table."""
    from database import get_db_connection, init_db
    
    init_db(db_path)
    if csv_path is None:
        csv_path = Config.SAMPLE_DATA_PATH
        if not os.path.exists(csv_path):
            generate_hostel_telemetry(output_csv=csv_path)

    df = pd.read_csv(csv_path)
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM readings")
    count = cursor.fetchone()[0]
    if count == 0:
        print(f"Seeding SQLite readings table with {len(df)} rows from {csv_path}...")
        records = df[[
            "timestamp", "block_id", "floor", "power_kw", "energy_kwh",
            "occupancy", "occupancy_rate", "temperature", "humidity",
            "day_type", "is_synthetic", "source"
        ]].values.tolist()

        cursor.executemany("""
            INSERT INTO readings (
                timestamp, block_id, floor, power_kw, energy_kwh,
                occupancy, occupancy_rate, temperature, humidity,
                day_type, is_synthetic, source
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, records)
        conn.commit()
        print(f"Seeded {len(records)} telemetry records into readings table.")
    else:
        print(f"Readings table already populated with {count} records.")

    conn.close()

if __name__ == "__main__":
    df = generate_hostel_telemetry()
    seed_database_with_telemetry()

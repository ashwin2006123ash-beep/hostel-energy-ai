import json
import pandas as pd
from config import Config
from database import init_db, get_db_connection, seed_esp32_devices
from services.dataset_generator import generate_hostel_telemetry, seed_database_with_telemetry
from models.anomaly_detector import ContextAwareAnomalyDetector
from services.energy_detective import EnergyDetective
from services.fault_detector import ElectricalFaultEarlyWarningEngine
from services.savings_engine import VerifiedSavingsEngine

def populate_database_and_models():
    """Seeds database and generates initial anomalies, fault warnings, and savings."""
    print("Initializing database...")
    init_db()
    seed_esp32_devices()

    # Generate telemetry if not present
    seed_database_with_telemetry()

    # Load readings from DB
    conn = get_db_connection()
    df = pd.read_sql_query("SELECT * FROM readings ORDER BY timestamp ASC", conn)
    
    # Train and run anomaly detector
    print("Training anomaly detector on telemetry...")
    detector = ContextAwareAnomalyDetector()
    detector.fit(df)
    
    print("Detecting anomalies across all readings...")
    detected_df = detector.detect(df)

    # Insert anomalies into anomalies table
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM anomalies")
    if cursor.fetchone()[0] == 0:
        anomalies_only = detected_df[detected_df["is_anomaly"] == 1]
        print(f"Populating anomalies table with {len(anomalies_only)} detected events...")
        detective = EnergyDetective()

        anomaly_records = []
        for _, row in anomalies_only.iterrows():
            diag = detective.analyze_anomaly(row.to_dict())
            ranked_json = json.dumps(diag["ranked_causes"])
            primary_cause = diag["primary_cause"]

            anomaly_records.append((
                int(row["id"]),
                str(row["timestamp"]),
                str(row["block_id"]),
                float(row["power_kw"]),
                float(row["expected_kw"]),
                float(row["residual_kw"]),
                float(row["anomaly_score"]),
                str(row["severity"]),
                primary_cause,
                ranked_json,
                "New",
                f"Statistical deviation: +{row['residual_kw']} kW above expected baseline."
            ))

        cursor.executemany("""
            INSERT INTO anomalies (
                reading_id, timestamp, block_id, actual_kw, expected_kw,
                residual_kw, anomaly_score, severity, primary_cause,
                cause_ranking_json, status, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, anomaly_records)
        conn.commit()
        print(f"Inserted {len(anomaly_records)} anomaly records.")

    conn.close()

    # Scan and sync fault warnings
    print("Scanning for electrical fault early warnings...")
    fault_engine = ElectricalFaultEarlyWarningEngine()
    faults = fault_engine.scan_telemetry_for_faults(df)
    fault_engine.sync_warnings_to_db(faults)
    print(f"Synced {len(faults)} electrical fault warnings.")

    # Seed verified savings
    print("Seeding verified savings actions...")
    savings_engine = VerifiedSavingsEngine()
    savings_engine.seed_verified_actions()
    print("Seeding complete.")

if __name__ == "__main__":
    populate_database_and_models()

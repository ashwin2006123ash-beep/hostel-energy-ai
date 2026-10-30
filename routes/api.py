import os
import json
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify
from config import Config
from database import get_db_connection
from services.data_processor import validate_csv_data, save_validated_df_to_db
from models.anomaly_detector import ContextAwareAnomalyDetector
from models.consumption_predictor import BaselineConsumptionPredictor
from models.appliance_fingerprinter import VirtualApplianceFingerprinter
from services.energy_detective import EnergyDetective
from services.simulator import WhatIfEnergySimulator
from services.fault_detector import ElectricalFaultEarlyWarningEngine
from services.savings_engine import VerifiedSavingsEngine
from services.league_service import FairEfficiencyLeague
from services.esp32_simulator import ESP32FanSimulator
from services.room_manager import RoomManager

api_bp = Blueprint("api", __name__, url_prefix="/api")

# Singletons / cached instances
_detector = None
_fingerprinter = VirtualApplianceFingerprinter()
_detective = EnergyDetective()
_simulator = WhatIfEnergySimulator()
_fault_engine = ElectricalFaultEarlyWarningEngine()
_savings_engine = VerifiedSavingsEngine()
_league_service = FairEfficiencyLeague()
_esp32_sim = ESP32FanSimulator()
_room_mgr = RoomManager()

def get_detector():
    global _detector
    if _detector is None:
        _detector = ContextAwareAnomalyDetector()
        _detector.load_or_train()
    return _detector

# -------------------------------------------------------------------------
# 1. Dashboard Stats
# -------------------------------------------------------------------------
# 1. Dashboard Stats (Supports timeframe & block filters)
# -------------------------------------------------------------------------
@api_bp.route("/dashboard/stats", methods=["GET"])
def get_dashboard_stats():
    timeframe = request.args.get("timeframe", "7d")  # '24h', '7d', '30d'
    block_id = request.args.get("block_id", "all")

    conn = get_db_connection()
    cursor = conn.cursor()

    # Latest reading timestamp
    cursor.execute("SELECT MAX(timestamp) as max_ts FROM readings")
    max_ts_row = cursor.fetchone()
    max_ts = max_ts_row["max_ts"] if max_ts_row and max_ts_row["max_ts"] else None

    if not max_ts:
        conn.close()
        return jsonify({"error": "No telemetry data available."}), 404

    max_dt = pd.to_datetime(max_ts)
    if timeframe == "24h":
        start_dt = max_dt - timedelta(hours=24)
        period_label = "24 Hours"
    elif timeframe == "30d":
        start_dt = max_dt - timedelta(days=30)
        period_label = "30 Days"
    else:
        start_dt = max_dt - timedelta(days=7)
        period_label = "7 Days"

    start_str = start_dt.strftime("%Y-%m-%d %H:%M:%S")

    # Get latest readings across all blocks at max_ts
    cursor.execute("""
        SELECT block_id, power_kw, occupancy, temperature, humidity
        FROM readings WHERE timestamp = ?
    """, (max_ts,))
    latest_rows = cursor.fetchall()
    
    total_current_kw = sum(r["power_kw"] for r in latest_rows)
    total_occupancy = sum(r["occupancy"] for r in latest_rows)
    avg_temp = np.mean([r["temperature"] for r in latest_rows]) if latest_rows else 28.0

    # Period electricity consumption
    if block_id == "all":
        cursor.execute("SELECT SUM(energy_kwh) as period_kwh FROM readings WHERE timestamp >= ?", (start_str,))
    else:
        cursor.execute("SELECT SUM(energy_kwh) as period_kwh FROM readings WHERE timestamp >= ? AND block_id = ?", (start_str, block_id))
    period_kwh_row = cursor.fetchone()
    period_kwh = float(period_kwh_row["period_kwh"] or 0.0)

    # Total energy consumed in whole 30-day dataset
    cursor.execute("SELECT SUM(energy_kwh) as total_kwh FROM readings")
    total_kwh = float(cursor.fetchone()["total_kwh"] or 0.0)

    # Billing & Carbon Estimations
    period_bill_inr = _simulator.calculate_bill(period_kwh)
    monthly_bill_inr = _simulator.calculate_bill(total_kwh)
    co2_kg = _simulator.calculate_carbon_kg(period_kwh)

    # Flagged rooms requiring investigation in this period
    if block_id == "all":
        cursor.execute("""
            SELECT room_number, block_id, severity, residual_kw
            FROM anomalies
            WHERE status != 'resolved' AND timestamp >= ?
        """, (start_str,))
    else:
        cursor.execute("""
            SELECT room_number, block_id, severity, residual_kw
            FROM anomalies
            WHERE status != 'resolved' AND timestamp >= ? AND block_id = ?
        """, (start_str, block_id))
    anom_rows = cursor.fetchall()

    flagged_room_set = set()
    critical_rooms_set = set()
    warning_rooms_set = set()
    excess_kwh = 0.0

    for r in anom_rows:
        room_key = f"{r['block_id']}-{r['room_number']}"
        flagged_room_set.add(room_key)
        if r["severity"] == "CRITICAL":
            critical_rooms_set.add(room_key)
        else:
            warning_rooms_set.add(room_key)
        if r["residual_kw"] and r["residual_kw"] > 0:
            excess_kwh += float(r["residual_kw"])

    flagged_rooms_count = len(flagged_room_set)
    critical_rooms_count = len(critical_rooms_set)
    warning_rooms_count = len(warning_rooms_set)

    # Potential savings: excess energy above expected baseline in flagged rooms
    potential_savings_kwh = round(excess_kwh, 1)
    potential_savings_inr = _simulator.calculate_bill(potential_savings_kwh)

    # Active persistent fault warnings
    cursor.execute("SELECT COUNT(*) as count FROM fault_warnings WHERE resolved = 0")
    active_faults_count = cursor.fetchone()["count"]

    conn.close()

    sanctioned_load = Config.SANCTIONED_LOAD_KW
    demand_utilization_pct = round((total_current_kw / sanctioned_load) * 100, 1)

    return jsonify({
        "status": "success",
        "timeframe": timeframe,
        "period_label": period_label,
        "block_id": block_id,
        "latest_timestamp": max_ts,
        # 4 Primary Metrics for Main Dashboard
        "total_consumption_kwh": round(period_kwh, 1),
        "estimated_bill_inr": period_bill_inr,
        "flagged_rooms_count": flagged_rooms_count,
        "critical_rooms_count": critical_rooms_count,
        "warning_rooms_count": warning_rooms_count,
        "potential_savings_inr": potential_savings_inr,
        "potential_savings_kwh": potential_savings_kwh,
        # Supporting metrics for backwards compatibility & technical views
        "campus_current_kw": round(total_current_kw, 2),
        "total_occupancy": total_occupancy,
        "sanctioned_load_kw": sanctioned_load,
        "demand_utilization_pct": demand_utilization_pct,
        "ambient_temp_c": round(float(avg_temp), 1),
        "total_kwh_30d": round(total_kwh, 1),
        "estimated_monthly_bill_inr": monthly_bill_inr,
        "estimated_monthly_co2_kg": co2_kg,
        "active_anomalies_count": len(anom_rows),
        "critical_anomalies_count": sum(1 for r in anom_rows if r["severity"] == "CRITICAL"),
        "high_anomalies_count": sum(1 for r in anom_rows if r["severity"] in ("HIGH", "MEDIUM", "WARNING")),
        "active_faults_count": active_faults_count,
        "disclaimer": Config.DISCLAIMER_TEXT
    })

# -------------------------------------------------------------------------
# 2. Historical Telemetry for Charts
# -------------------------------------------------------------------------
@api_bp.route("/readings/history", methods=["GET"])
def get_readings_history():
    block_id = request.args.get("block_id", "all")
    timeframe = request.args.get("timeframe", "7d") # '24h', '7d', '30d'

    conn = get_db_connection()
    cursor = conn.cursor()

    # Determine date window
    cursor.execute("SELECT MAX(timestamp) as max_ts FROM readings")
    max_ts_str = cursor.fetchone()["max_ts"]
    if not max_ts_str:
        conn.close()
        return jsonify({"timestamps": [], "actual_kw": [], "expected_kw": []})

    max_dt = pd.to_datetime(max_ts_str)
    if timeframe == "24h":
        start_dt = max_dt - timedelta(hours=24)
    elif timeframe == "7d":
        start_dt = max_dt - timedelta(days=7)
    else:
        start_dt = max_dt - timedelta(days=30)

    start_str = start_dt.strftime("%Y-%m-%d %H:%M:%S")

    # Fetch readings
    if block_id == "all":
        query = """
            SELECT timestamp,
                   SUM(power_kw) as actual_kw,
                   SUM(occupancy) as occupancy,
                   AVG(temperature) as temperature
            FROM readings
            WHERE timestamp >= ?
            GROUP BY timestamp
            ORDER BY timestamp ASC
        """
        params = (start_str,)
    else:
        query = """
            SELECT timestamp,
                   power_kw as actual_kw,
                   occupancy,
                   temperature
            FROM readings
            WHERE timestamp >= ? AND block_id = ?
            ORDER BY timestamp ASC
        """
        params = (start_str, block_id)

    df_readings = pd.read_sql_query(query, conn, params=params)

    # Fetch corresponding anomalies
    if block_id == "all":
        anomaly_query = """
            SELECT timestamp, SUM(actual_kw) as actual_kw, severity, primary_cause
            FROM anomalies
            WHERE timestamp >= ? AND severity IN ('HIGH', 'CRITICAL')
            GROUP BY timestamp
        """
        anomaly_params = (start_str,)
    else:
        anomaly_query = """
            SELECT timestamp, actual_kw, severity, primary_cause
            FROM anomalies
            WHERE timestamp >= ? AND block_id = ? AND severity IN ('HIGH', 'CRITICAL')
        """
        anomaly_params = (start_str, block_id)

    df_anomalies = pd.read_sql_query(anomaly_query, conn, params=anomaly_params)
    conn.close()

    if df_readings.empty:
        return jsonify({"timestamps": [], "actual_kw": [], "expected_kw": [], "anomalies": []})

    # Compute expected baseline using predictor or aggregate approximation
    detector = get_detector()
    # To get expected_kw for the specific block or campus:
    sample_df = df_readings.copy()
    sample_df["block_id"] = "Block-A" if block_id == "all" else block_id
    sample_df["day_type"] = "Weekday"
    sample_df["humidity"] = 60.0

    try:
        expected_preds = detector.baseline_predictor.predict(sample_df)
        if block_id == "all":
            # Scale by 4 for campus aggregate
            expected_kw_list = np.round(expected_preds * 3.8, 2).tolist()
        else:
            expected_kw_list = np.round(expected_preds, 2).tolist()
    except Exception:
        # Fallback to rolling mean if predictor error
        expected_kw_list = sample_df["actual_kw"].rolling(5, min_periods=1).mean().round(2).tolist()

    # Format anomaly points
    anomaly_map = {row["timestamp"]: {"severity": row["severity"], "cause": row["primary_cause"]}
                   for _, row in df_anomalies.iterrows()}

    anomaly_flags = []
    for ts in df_readings["timestamp"]:
        if ts in anomaly_map:
            anomaly_flags.append(anomaly_map[ts])
        else:
            anomaly_flags.append(None)

    return jsonify({
        "block_id": block_id,
        "timeframe": timeframe,
        "timestamps": df_readings["timestamp"].tolist(),
        "actual_kw": df_readings["actual_kw"].round(2).tolist(),
        "expected_kw": expected_kw_list,
        "occupancy": df_readings["occupancy"].tolist(),
        "temperature": df_readings["temperature"].round(1).tolist(),
        "anomalies": anomaly_flags
    })

# -------------------------------------------------------------------------
# 3. Anomalies List & Diagnostic Deep Dive
# -------------------------------------------------------------------------
@api_bp.route("/anomalies", methods=["GET"])
def get_anomalies():
    severity = request.args.get("severity")
    block_id = request.args.get("block_id")
    status = request.args.get("status")
    limit = int(request.args.get("limit", 50))
    offset = int(request.args.get("offset", 0))

    conn = get_db_connection()
    cursor = conn.cursor()

    query = "SELECT * FROM anomalies WHERE 1=1"
    params = []

    if severity and severity != "ALL":
        query += " AND severity = ?"
        params.append(severity)
    if block_id and block_id != "ALL":
        query += " AND block_id = ?"
        params.append(block_id)
    if status and status != "ALL":
        query += " AND status = ?"
        params.append(status)

    # Count total matching
    count_query = query.replace("SELECT *", "SELECT COUNT(*)")
    cursor.execute(count_query, params)
    total_count = cursor.fetchone()[0]

    query += " ORDER BY id DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    cursor.execute(query, params)
    rows = [dict(r) for r in cursor.fetchall()]

    for r in rows:
        try:
            r["cause_ranking"] = json.loads(r["cause_ranking_json"])
        except Exception:
            r["cause_ranking"] = []

    conn.close()
    return jsonify({
        "total": total_count,
        "limit": limit,
        "offset": offset,
        "anomalies": rows,
        "disclaimer": Config.DISCLAIMER_TEXT
    })

@api_bp.route("/anomalies/<int:anomaly_id>/diagnostic", methods=["GET"])
def get_anomaly_diagnostic(anomaly_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT a.*, r.occupancy, r.occupancy_rate, r.temperature, r.humidity, r.day_type
        FROM anomalies a
        JOIN readings r ON a.reading_id = r.id
        WHERE a.id = ?
    """, (anomaly_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        return jsonify({"error": f"Anomaly ID {anomaly_id} not found"}), 404

    row_dict = dict(row)
    diag_report = _detective.analyze_anomaly(row_dict)
    diag_report["anomaly_id"] = anomaly_id
    diag_report["status"] = row_dict["status"]
    diag_report["notes"] = row_dict["notes"]

    return jsonify(diag_report)

@api_bp.route("/anomalies/<int:anomaly_id>/status", methods=["POST"])
def update_anomaly_status(anomaly_id):
    data = request.get_json() or {}
    new_status = data.get("status", "Investigating")
    notes = data.get("notes", "")

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE anomalies
        SET status = ?, notes = ?
        WHERE id = ?
    """, (new_status, notes, anomaly_id))
    conn.commit()
    conn.close()

    return jsonify({"success": True, "anomaly_id": anomaly_id, "new_status": new_status})

# -------------------------------------------------------------------------
# 4. Virtual Appliance Fingerprinting
# -------------------------------------------------------------------------
@api_bp.route("/fingerprinting", methods=["GET"])
def get_appliance_fingerprinting():
    block_id = request.args.get("block_id", "Block-A")
    conn = get_db_connection()
    df = pd.read_sql_query(
        "SELECT * FROM readings WHERE block_id = ? ORDER BY timestamp DESC LIMIT 300",
        conn, params=(block_id,)
    )
    conn.close()

    if df.empty:
        # Fallback to general sample
        return jsonify({
            "is_estimate": True,
            "disclaimer": _fingerprinter.disclaimer,
            "category_percentages": {
                "standby_base": 18.0,
                "cooling_fans": 34.0,
                "lighting": 16.0,
                "plug_electronics": 22.0,
                "high_wattage_thermal": 10.0
            }
        })

    fp_result = _fingerprinter.fingerprint_dataframe(df)
    fp_result["block_id"] = block_id
    return jsonify(fp_result)

# -------------------------------------------------------------------------
# 5. Electrical Fault Early Warnings
# -------------------------------------------------------------------------
@api_bp.route("/faults", methods=["GET"])
def get_fault_warnings():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM fault_warnings ORDER BY persistence_days DESC, id DESC")
    faults = [dict(r) for r in cursor.fetchall()]
    conn.close()

    return jsonify({
        "active_faults_count": len([f for f in faults if f["resolved"] == 0]),
        "fault_warnings": faults,
        "disclaimer": (
            "NOTICE: Fault early warnings indicate sustained abnormal electrical patterns (e.g., creeping baseload) "
            "and suggest priority targets for physical preventive maintenance testing."
        )
    })

# -------------------------------------------------------------------------
# 6. What-If Energy Simulator
# -------------------------------------------------------------------------
@api_bp.route("/simulate", methods=["POST"])
def run_simulation():
    data = request.get_json() or {}

    # Extract user parameter inputs
    empty_cutoff = float(data.get("empty_room_cutoff_pct", 50))
    led_pct = float(data.get("led_retrofit_pct", 60))
    fan_pct = float(data.get("fan_eco_regulation_pct", 70))
    curfew_enabled = bool(data.get("curfew_cutoff_enabled", True))
    geyser_enabled = bool(data.get("geyser_timer_enabled", True))
    solar_kwp = float(data.get("solar_pv_kwp", 15.0))

    # Fetch actual 30-day consumption from DB as current baseline
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT SUM(energy_kwh) as total_kwh FROM readings")
    row = cursor.fetchone()
    current_kwh = float(row["total_kwh"]) if row and row["total_kwh"] else 18500.0
    conn.close()

    results = _simulator.simulate(
        current_monthly_kwh=current_kwh,
        empty_room_cutoff_pct=empty_cutoff,
        led_retrofit_pct=led_pct,
        fan_eco_regulation_pct=fan_pct,
        curfew_cutoff_enabled=curfew_enabled,
        geyser_timer_enabled=geyser_enabled,
        solar_pv_kwp=solar_kwp
    )

    return jsonify(results)

# -------------------------------------------------------------------------
# 7. Verified Savings Engine (M&V IPMVP)
# -------------------------------------------------------------------------
@api_bp.route("/savings", methods=["GET"])
def get_verified_savings():
    data = _savings_engine.get_all_savings()
    return jsonify(data)

# -------------------------------------------------------------------------
# 8. Fair Energy Efficiency League
# -------------------------------------------------------------------------
@api_bp.route("/league", methods=["GET"])
def get_league_standings():
    standings = _league_service.compute_league_standings()
    return jsonify({
        "standings": standings,
        "normalization_notes": (
            "Metrics are normalized by actual student occupant-days and usable floor area (m²) "
            "to ensure equitable comparison regardless of hostel physical dimensions."
        )
    })

# -------------------------------------------------------------------------
# 9. Energy Digital Twin Status
# -------------------------------------------------------------------------
@api_bp.route("/digital-twin/status", methods=["GET"])
def get_digital_twin_status():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Get latest readings per block
    cursor.execute("SELECT MAX(timestamp) as max_ts FROM readings")
    max_ts = cursor.fetchone()["max_ts"]

    blocks_data = {}
    for block_id, meta in Config.HOSTEL_BLOCKS.items():
        cursor.execute("""
            SELECT power_kw, occupancy, temperature, humidity
            FROM readings
            WHERE block_id = ? AND timestamp = ?
        """, (block_id, max_ts))
        row = cursor.fetchone()

        # Check for active anomalies in this block
        cursor.execute("""
            SELECT severity, primary_cause
            FROM anomalies
            WHERE block_id = ? AND status IN ('New', 'Investigating')
            ORDER BY id DESC LIMIT 1
        """, (block_id,))
        active_anom = cursor.fetchone()

        power_kw = float(row["power_kw"]) if row else 8.5
        occupancy = int(row["occupancy"]) if row else 100
        cap = meta["capacity"]
        floors = meta["floors"]

        # Calculate floor-level breakdown
        floor_breakdown = []
        for fl in range(1, floors + 1):
            fl_share = 1.0 / floors
            fl_kw = round(power_kw * fl_share * np.random.uniform(0.85, 1.15), 2)
            fl_occ = int(occupancy * fl_share)
            fl_density_w_sqm = round((fl_kw * 1000.0) / (meta["floor_area_sqm"] / floors), 2)
            
            # Floor heat level: 0 to 100
            heat_level = int(np.clip((fl_density_w_sqm / 15.0) * 100, 10, 100))

            floor_breakdown.append({
                "floor_number": fl,
                "power_kw": fl_kw,
                "occupancy": fl_occ,
                "power_density_w_sqm": fl_density_w_sqm,
                "heat_level_pct": heat_level,
                "status": "NORMAL" if not active_anom else active_anom["severity"]
            })

        blocks_data[block_id] = {
            "name": meta["name"],
            "type": meta["type"],
            "capacity": cap,
            "floors_count": floors,
            "current_power_kw": power_kw,
            "current_occupancy": occupancy,
            "occupancy_rate_pct": round((occupancy / cap) * 100, 1),
            "floors": floor_breakdown,
            "active_anomaly": {
                "severity": active_anom["severity"],
                "cause": active_anom["primary_cause"]
            } if active_anom else None
        }

    conn.close()
    return jsonify({
        "timestamp": max_ts,
        "blocks": blocks_data
    })

# -------------------------------------------------------------------------
# 10. Virtual ESP32 Fan Control
# -------------------------------------------------------------------------
@api_bp.route("/esp32/devices", methods=["GET"])
def get_esp32_devices():
    devices = _esp32_sim.get_devices()
    return jsonify({"devices": devices, "disclaimer": _esp32_sim.disclaimer})

@api_bp.route("/esp32/command", methods=["POST"])
def send_esp32_command():
    data = request.get_json() or {}
    device_id = data.get("device_id")
    command_type = data.get("command_type", "SET_SPEED")
    value = data.get("value", 50)
    result = _esp32_sim.send_command(device_id, command_type, value)
    return jsonify(result)

@api_bp.route("/esp32/logs", methods=["GET"])
def get_esp32_logs():
    logs = _esp32_sim.get_logs()
    return jsonify({"logs": logs})

# -------------------------------------------------------------------------
# 11. CSV Upload Pipeline
# -------------------------------------------------------------------------
@api_bp.route("/upload", methods=["POST"])
def handle_csv_upload():
    if "file" not in request.files:
        return jsonify({"valid": False, "errors": ["No file part in the upload request."]}), 400

    file = request.files["file"]
    action = request.form.get("action", "preview") # 'preview' or 'ingest'

    if file.filename == "":
        return jsonify({"valid": False, "errors": ["No file selected."]}), 400

    if not file.filename.lower().endswith(".csv"):
        return jsonify({"valid": False, "errors": ["Only CSV files (.csv) are accepted."]}), 400

    # Validate file contents
    validation_result = validate_csv_data(file.stream)
    if not validation_result["valid"]:
        return jsonify(validation_result), 400

    df = validation_result["df"]

    # Preview mode
    if action == "preview":
        preview_rows = df.head(10).to_dict(orient="records")
        return jsonify({
            "valid": True,
            "action": "preview",
            "warnings": validation_result["warnings"],
            "summary": validation_result["summary"],
            "preview": preview_rows
        })

    # Ingest mode
    elif action == "ingest":
        try:
            saved_count = save_validated_df_to_db(df, source=f"csv_upload:{file.filename}")
            
            # Run anomaly detection on newly ingested data
            detector = get_detector()
            detected_df = detector.detect(df)
            anomalies_only = detected_df[detected_df["is_anomaly"] == 1]
            
            # Sync new anomalies to DB
            conn = get_db_connection()
            cursor = conn.cursor()
            detective = EnergyDetective()
            for _, row in anomalies_only.iterrows():
                diag = detective.analyze_anomaly(row.to_dict())
                cursor.execute("""
                    INSERT INTO anomalies (
                        timestamp, block_id, actual_kw, expected_kw,
                        residual_kw, anomaly_score, severity, primary_cause,
                        cause_ranking_json, status, notes
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'New', ?)
                """, (
                    str(row["timestamp"]),
                    str(row["block_id"]),
                    float(row["power_kw"]),
                    float(row["expected_kw"]),
                    float(row["residual_kw"]),
                    float(row["anomaly_score"]),
                    str(row["severity"]),
                    diag["primary_cause"],
                    json.dumps(diag["ranked_causes"]),
                    f"Uploaded dataset anomaly: +{row['residual_kw']} kW deviation."
                ))
            conn.commit()
            conn.close()

            return jsonify({
                "valid": True,
                "action": "ingest",
                "saved_rows": saved_count,
                "anomalies_detected": len(anomalies_only),
                "summary": validation_result["summary"]
            })
        except Exception as e:
            return jsonify({"valid": False, "errors": [f"Database ingest failed: {str(e)}"]}), 500

    return jsonify({"valid": False, "errors": ["Invalid action specified."]}), 400

# -------------------------------------------------------------------------
# 12. Reset to Synthetic Telemetry
# -------------------------------------------------------------------------
@api_bp.route("/reset-data", methods=["POST"])
def reset_synthetic_data():
    from seed_all import populate_database_and_models
    try:
        # Re-initialize
        populate_database_and_models()
        return jsonify({"success": True, "message": "Synthetic database and ML models reset successfully."})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# -------------------------------------------------------------------------
# 13. Room Investigation List
# -------------------------------------------------------------------------
@api_bp.route("/rooms", methods=["GET"])
def get_rooms():
    block_id = request.args.get("block_id", "all")
    severity = request.args.get("severity", "all")
    status = request.args.get("status", "all")
    occupancy = request.args.get("occupancy", "all")
    limit = int(request.args.get("limit", 100))
    offset = int(request.args.get("offset", 0))

    conn = get_db_connection()
    cursor = conn.cursor()

    query = "SELECT * FROM anomalies WHERE 1=1"
    params = []

    if block_id != "all":
        query += " AND block_id = ?"
        params.append(block_id)
    if severity != "all":
        query += " AND severity = ?"
        params.append(severity)
    if status != "all":
        query += " AND status = ?"
        params.append(status)
    if occupancy != "all":
        query += " AND occupancy_status = ?"
        params.append(occupancy)

    # Order priority: pending first, then by severity (CRITICAL > HIGH > MEDIUM > LOW), then by id DESC
    query += """
        ORDER BY 
            CASE status WHEN 'pending' THEN 1 WHEN 'investigating' THEN 2 ELSE 3 END,
            CASE severity WHEN 'CRITICAL' THEN 1 WHEN 'HIGH' THEN 2 WHEN 'MEDIUM' THEN 3 ELSE 4 END,
            id DESC
        LIMIT ? OFFSET ?
    """
    params.extend([limit, offset])

    cursor.execute(query, params)
    rows = [dict(r) for r in cursor.fetchall()]

    for r in rows:
        try:
            r["cause_ranking"] = json.loads(r.get("cause_ranking_json", "[]"))
        except Exception:
            r["cause_ranking"] = []

    conn.close()
    return jsonify({
        "status": "success",
        "count": len(rows),
        "rooms": rows,
        "disclaimer": Config.DISCLAIMER_TEXT
    })

# -------------------------------------------------------------------------
# 14. AI Recommendations for Staff & Wardens
# -------------------------------------------------------------------------
@api_bp.route("/recommendations", methods=["GET"])
def get_recommendations():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Get active unresolved anomalies
    cursor.execute("""
        SELECT a.*, r.temperature, r.humidity
        FROM anomalies a
        LEFT JOIN readings r ON a.reading_id = r.id
        WHERE a.status != 'resolved'
        ORDER BY 
            CASE a.severity WHEN 'CRITICAL' THEN 1 WHEN 'HIGH' THEN 2 ELSE 3 END,
            a.residual_kw DESC
        LIMIT 40
    """)
    rows = cursor.fetchall()
    conn.close()

    immediate = []
    operational = []
    routine = []

    for r in rows:
        row = dict(r)
        actual = row["actual_kw"]
        expected = row["expected_kw"]
        delta = row["residual_kw"]
        occ = row["occupancy_status"] or "unknown"
        block = row["block_id"]
        room = row["room_number"] or "General Room"

        # Actionable plain English explanation and checklists
        if occ == "likely vacant":
            symptom_text = f"Room shows active draw of {actual:.1f} kW (+{delta:.1f} kW over {expected:.1f} kW expected baseline) while flagged as likely vacant."
            check_list = [
                "Physically inspect room to verify occupant presence.",
                "Check for unattended space heaters, coolers, or high-power study lamps left powered on.",
                "Inspect heavy plug sockets for unauthorized high-wattage extension boards.",
                "Turn off main circuit switch if room is confirmed unoccupied."
            ]
        elif row["severity"] == "CRITICAL":
            symptom_text = f"Severe power excursion of {actual:.1f} kW exceeding expected baseline by +{delta:.1f} kW ({row['anomaly_score']*100:.0f}% confidence)."
            check_list = [
                "Immediate safety check: inspect floor distribution box for warm circuit breakers or electrical tripping smell.",
                "Inspect common washroom water geyser relays - verify if contactor is stuck in continuous ON state.",
                "Inspect shared pantry/kitchen equipment for potential earth leakage or overloaded phases.",
                "Alert electrical maintenance staff if breaker switch is unusually hot to the touch."
            ]
        else:
            symptom_text = f"Elevated baseline draw (+{delta:.1f} kW deviation from expected load). Possible continuous equipment cycling."
            check_list = [
                "Check ceiling fan speed regulators and refrigerator door gaskets.",
                "Survey student rooms for multiple continuous charging laptops or desktop mini-PCs.",
                "Remind floor occupants of campus peak hours (06:00-09:00 and 18:00-22:00)."
            ]

        # Calculate estimated avoidable waste in INR (approx 9.2 INR/kWh)
        waste_kwh = max(delta, 0.5)
        waste_inr = round(waste_kwh * 9.2, 0)

        rec_item = {
            "id": row["id"],
            "block_id": block,
            "room_number": room,
            "severity": row["severity"],
            "occupancy_status": occ,
            "issue_type": "Suspected Anomaly" if row["status"] == "pending" else "Under Investigation",
            "symptom": symptom_text,
            "checklist": check_list,
            "action": row["recommended_action"],
            "potential_savings_inr": waste_inr,
            "requires_approval": True,
            "status": row["status"]
        }

        if row["severity"] == "CRITICAL":
            immediate.append(rec_item)
        elif occ == "likely vacant":
            operational.append(rec_item)
        else:
            routine.append(rec_item)

    return jsonify({
        "status": "success",
        "total_recommendations": len(immediate) + len(operational) + len(routine),
        "immediate": immediate[:8],
        "operational": operational[:8],
        "routine": routine[:8],
        "guidance_note": "All recommendations are AI diagnostic hypotheses and require warden approval before real-world enforcement."
    })

# -------------------------------------------------------------------------
# 15. Incident Memory Handlers ("Learn Once, Act Smart")
# -------------------------------------------------------------------------
@api_bp.route("/incidents", methods=["GET", "POST"])
def handle_incidents():
    conn = get_db_connection()
    cursor = conn.cursor()

    if request.method == "POST":
        data = request.get_json() or {}
        block_id = data.get("block_id", "Block-A")
        room_number = data.get("room_number", "Room 101")
        incident_date = data.get("incident_date", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        anomaly_symptom = data.get("anomaly_symptom", "Elevated electricity consumption")
        confirmed_cause = data.get("confirmed_cause", "")
        action_taken = data.get("action_taken", "")
        measured_result = data.get("measured_result", "Load returned to normal baseline")
        savings_kwh_post = float(data.get("savings_kwh_post", 0.0))
        savings_inr_post = float(data.get("savings_inr_post", savings_kwh_post * 9.2))
        verified_by = data.get("verified_by", "Hostel Warden")

        if not confirmed_cause or not action_taken:
            conn.close()
            return jsonify({"success": False, "error": "Confirmed cause and action taken are required."}), 400

        cursor.execute("""
            INSERT INTO incident_memory (
                block_id, room_number, incident_date, anomaly_symptom,
                confirmed_cause, action_taken, measured_result,
                savings_kwh_post, savings_inr_post, verified_by, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Verified')
        """, (
            block_id, room_number, incident_date, anomaly_symptom,
            confirmed_cause, action_taken, measured_result,
            savings_kwh_post, savings_inr_post, verified_by
        ))
        new_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return jsonify({"success": True, "id": new_id, "message": "Incident resolution verified and recorded in institutional memory."})

    else:
        cursor.execute("SELECT * FROM incident_memory ORDER BY id DESC")
        rows = [dict(r) for r in cursor.fetchall()]
        conn.close()
        return jsonify({"status": "success", "incidents": rows, "count": len(rows)})

@api_bp.route("/incidents/match", methods=["POST", "GET"])
def match_incident():
    symptom = request.args.get("symptom") or (request.get_json() or {}).get("symptom", "")
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM incident_memory ORDER BY id DESC")
    all_incidents = [dict(r) for r in cursor.fetchall()]
    conn.close()

    matches = []
    symptom_lower = symptom.lower()

    for inc in all_incidents:
        score = 0
        text_corp = f"{inc['anomaly_symptom']} {inc['confirmed_cause']} {inc['action_taken']}".lower()
        keywords = [w for w in symptom_lower.split() if len(w) > 3]
        for kw in keywords:
            if kw in text_corp:
                score += 1

        if score > 0 or not symptom:
            matches.append({
                "incident": inc,
                "relevance_score": score,
                "recommended_action": inc["action_taken"],
                "historical_savings_inr": inc["savings_inr_post"]
            })

    matches.sort(key=lambda x: x["relevance_score"], reverse=True)

    return jsonify({
        "status": "success",
        "matches": matches[:3],
        "approval_required": True,
        "disclaimer": "Requires hostel warden approval before taking any physical corrective action."
    })

# -------------------------------------------------------------------------
# 16. Reports Summary and CSV Export
# -------------------------------------------------------------------------
@api_bp.route("/reports/summary", methods=["GET"])
def get_reports_summary():
    timeframe = request.args.get("timeframe", "30d")
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT MAX(timestamp) as max_ts FROM readings")
    max_ts = cursor.fetchone()["max_ts"]
    max_dt = pd.to_datetime(max_ts) if max_ts else datetime.now()
    if timeframe == "24h":
        start_dt = max_dt - timedelta(hours=24)
    elif timeframe == "7d":
        start_dt = max_dt - timedelta(days=7)
    else:
        start_dt = max_dt - timedelta(days=30)
    start_str = start_dt.strftime("%Y-%m-%d %H:%M:%S")

    cursor.execute("SELECT SUM(energy_kwh) as total_kwh, AVG(power_kw) as avg_kw, MAX(power_kw) as peak_kw FROM readings WHERE timestamp >= ?", (start_str,))
    totals = cursor.fetchone()
    total_kwh = float(totals["total_kwh"] or 0.0)
    avg_kw = float(totals["avg_kw"] or 0.0)
    peak_kw = float(totals["peak_kw"] or 0.0)

    cursor.execute("""
        SELECT block_id, 
               SUM(energy_kwh) as block_kwh, 
               AVG(occupancy) as avg_occ,
               AVG(power_kw) as avg_kw
        FROM readings 
        WHERE timestamp >= ?
        GROUP BY block_id
    """, (start_str,))
    block_rows = cursor.fetchall()
    blocks_breakdown = []
    for br in block_rows:
        b_kwh = float(br["block_kwh"] or 0.0)
        b_bill = _simulator.calculate_bill(b_kwh)
        avg_occ = float(br["avg_occ"] or 1.0)
        per_capita = round(b_kwh / max(avg_occ, 1.0), 2)
        blocks_breakdown.append({
            "block_id": br["block_id"],
            "consumption_kwh": round(b_kwh, 1),
            "estimated_bill_inr": b_bill,
            "avg_occupancy": int(avg_occ),
            "per_student_kwh": per_capita
        })

    cursor.execute("SELECT COUNT(DISTINCT room_number) as flagged_rooms, COUNT(*) as total_anomalies FROM anomalies WHERE timestamp >= ? AND status != 'resolved'", (start_str,))
    flag_stats = cursor.fetchone()

    cursor.execute("SELECT SUM(verified_savings_kwh) as kwh_saved, SUM(verified_cost_saved_inr) as cost_saved FROM savings_actions")
    sav_row = cursor.fetchone()

    conn.close()

    return jsonify({
        "status": "success",
        "timeframe": timeframe,
        "start_date": start_str,
        "end_date": max_ts,
        "total_consumption_kwh": round(total_kwh, 1),
        "estimated_bill_inr": _simulator.calculate_bill(total_kwh),
        "carbon_kg": _simulator.calculate_carbon_kg(total_kwh),
        "peak_demand_kw": round(peak_kw, 2),
        "avg_demand_kw": round(avg_kw, 2),
        "flagged_rooms_count": flag_stats["flagged_rooms"] or 0,
        "total_anomalies": flag_stats["total_anomalies"] or 0,
        "verified_savings_kwh": round(float(sav_row["kwh_saved"] or 0.0), 1),
        "verified_savings_inr": round(float(sav_row["cost_saved"] or 0.0), 2),
        "blocks": blocks_breakdown
    })

@api_bp.route("/reports/export-csv", methods=["GET"])
def export_reports_csv():
    import io
    import csv
    from flask import Response

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT a.timestamp, a.block_id, a.room_number, a.actual_kw, a.expected_kw,
               a.residual_kw, a.occupancy_status, a.severity, a.primary_cause,
               a.recommended_action, a.status
        FROM anomalies a
        ORDER BY a.id DESC
        LIMIT 500
    """)
    rows = cursor.fetchall()
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Timestamp", "Block", "Room Number", "Actual (kW)", "Expected (kW)",
        "Residual Deviation (kW)", "Occupancy Status", "Severity", "Primary Cause",
        "Recommended Action", "Status"
    ])
    for r in rows:
        writer.writerow([
            r["timestamp"], r["block_id"], r["room_number"],
            r["actual_kw"], r["expected_kw"], r["residual_kw"],
            r["occupancy_status"], r["severity"], r["primary_cause"],
            r["recommended_action"], r["status"]
        ])

    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment;filename=hostel_energy_flagged_rooms_report.csv"}
    )

# -------------------------------------------------------------------------
# 17. Room Command Center APIs
# -------------------------------------------------------------------------
@api_bp.route("/command-center/stats", methods=["GET"])
def get_command_center_stats():
    stats = _room_mgr.get_command_center_stats()
    stats["status"] = "success"
    stats["disclaimer"] = Config.DISCLAIMER_TEXT
    return jsonify(stats)

@api_bp.route("/rooms/live", methods=["GET"])
def get_live_rooms():
    block_id = request.args.get("block_id")
    room_state = request.args.get("room_state")
    occupancy_state = request.args.get("occupancy_state")
    switch_state = request.args.get("switch_state")
    rooms = _room_mgr.get_all_rooms(
        block_id=block_id,
        room_state=room_state,
        occupancy_state=occupancy_state,
        switch_state=switch_state
    )
    from services.live_power_simulator import live_simulator
    sim_status = live_simulator.get_status()
    return jsonify({
        "status": "success",
        "count": len(rooms),
        "rooms": rooms,
        "simulation": sim_status,
        "disclaimer": Config.DISCLAIMER_TEXT
    })

@api_bp.route("/rooms/<room_id>", methods=["GET"])
def get_single_room(room_id):
    room = _room_mgr.get_room_by_id(room_id)
    if not room:
        return jsonify({"status": "error", "message": f"Room {room_id} not found."}), 404
    return jsonify({"status": "success", "room": room})

@api_bp.route("/rooms/<room_id>/switch-state", methods=["GET"])
def get_room_switch_state(room_id):
    room = _room_mgr.get_room_by_id(room_id)
    if not room:
        return jsonify({"status": "error", "message": f"Room {room_id} not found."}), 404
    return jsonify({
        "status": "success",
        "room_id": room["room_id"],
        "block_id": room["block_id"],
        "room_number": room["room_number"],
        "switch_state": room["switch_state"],
        "effective_switch_state": room["effective_switch_state"],
        "manual_off_lock": room["manual_off_lock"],
        "fault_status": room["fault_status"],
        "power_w": room["power_w"],
        "room_state": room["room_state"],
        "relay_state": room["relay_state"],
        "trip_reason": room["trip_reason"],
        "last_switch_by": room["last_switch_by"],
        "last_switch_at": room["last_switch_at"],
        "resolution_confirmed_by": room["resolution_confirmed_by"],
        "resolution_confirmed_at": room["resolution_confirmed_at"],
        "resolution_notes": room["resolution_notes"],
        "can_switch_on": room["can_switch_on"],
        "switch_on_block_reason": room["switch_on_block_reason"],
        "restoration_eligible": room["restoration_eligible"],
        "optimization_target_w": room.get("optimization_target_w", 800.0),
        "excess_power_w": room.get("excess_power_w", 0.0),
        "reduction_required_w": room.get("reduction_required_w", 0.0),
        "optimization_state": room.get("optimization_state", "NORMAL"),
        "is_offline": room.get("is_offline", False),
        "sensor_status": room.get("sensor_status", "ONLINE"),
        "controllable_loads": room.get("controllable_loads", []),
        "events": room.get("events", [])
    })

@api_bp.route("/rooms/<room_id>/optimize", methods=["POST"])
def optimize_room_power_route(room_id):
    data = request.get_json() or {}
    operator = data.get("operator", "Warden (Power Optimizer)")
    target_w = data.get("target_w")
    if target_w is not None:
        try:
            target_w = float(target_w)
        except (ValueError, TypeError):
            return jsonify({"status": "error", "message": "Target wattage must be a valid numeric value."}), 400

    result = _room_mgr.optimize_room_power(room_id, operator=operator, target_w=target_w)
    status_code = result.get("code", 200) if not result.get("success") else 200
    return jsonify(result), status_code

@api_bp.route("/rooms/<room_id>/loads", methods=["GET", "POST"])
def handle_room_loads(room_id):
    if request.method == "POST":
        data = request.get_json() or {}
        loads = data.get("loads")
        if not isinstance(loads, list):
            return jsonify({"status": "error", "message": "Payload must contain a 'loads' list."}), 400
        _room_mgr.save_room_controllable_loads(room_id, loads)
        return jsonify({"status": "success", "room_id": room_id, "loads": loads, "message": "Simulated loads updated successfully."})
    else:
        loads = _room_mgr.get_room_controllable_loads(room_id)
        return jsonify({"status": "success", "room_id": room_id, "loads": loads})

@api_bp.route("/rooms/<room_id>/target", methods=["POST"])
def update_room_target_route(room_id):
    data = request.get_json() or {}
    target_w = data.get("target_w")
    threshold_w = data.get("threshold_w")
    if target_w is None:
        return jsonify({"status": "error", "message": "Missing 'target_w' field."}), 400
    try:
        t_val = float(target_w)
        thresh_val = float(threshold_w) if threshold_w is not None else None
    except (ValueError, TypeError):
        return jsonify({"status": "error", "message": "Target and threshold must be numeric."}), 400

    result = _room_mgr.update_room_target(room_id, target_w=t_val, threshold_w=thresh_val)
    if not result.get("success"):
        return jsonify(result), result.get("code", 400)
    return jsonify(result)

@api_bp.route("/rooms/<room_id>/switch-off", methods=["POST"])
def manual_room_switch_off(room_id):
    data = request.get_json() or {}
    operator = data.get("operator", "Hostel Warden")
    reason = data.get("reason")
    result = _room_mgr.manual_switch_off(room_id, operator=operator, reason=reason)
    if not result.get("success"):
        return jsonify(result), result.get("code", 400)
    return jsonify(result)

@api_bp.route("/rooms/<room_id>/switch-on", methods=["POST"])
def manual_room_switch_on(room_id):
    data = request.get_json() or {}
    operator = data.get("operator", "Hostel Warden")
    result = _room_mgr.manual_switch_on(room_id, operator=operator)
    if not result.get("success"):
        return jsonify(result), result.get("code", 400)
    return jsonify(result)

@api_bp.route("/rooms/<room_id>/release-lock", methods=["POST"])
def release_room_manual_lock(room_id):
    data = request.get_json() or {}
    operator = data.get("operator", "Hostel Warden")
    result = _room_mgr.release_manual_lock(room_id, operator=operator)
    if not result.get("success"):
        return jsonify(result), result.get("code", 400)
    return jsonify(result)

@api_bp.route("/rooms/<room_id>/problem-resolved", methods=["POST"])
def resolve_room_problem(room_id):
    data = request.get_json() or {}
    operator = data.get("operator", "Hostel Warden")
    notes = data.get("resolution_notes", "")
    fault_cleared = data.get("fault_cleared", True)
    result = _room_mgr.resolve_room_fault(
        room_id,
        operator=operator,
        resolution_notes=notes,
        fault_cleared=fault_cleared
    )
    if not result.get("success"):
        return jsonify(result), result.get("code", 400)
    return jsonify(result)

@api_bp.route("/rooms/<room_id>/reset-trip", methods=["POST"])
def reset_room_trip(room_id):
    data = request.get_json() or {}
    operator = data.get("operator", "Hostel Warden")
    result = _room_mgr.reset_room_trip(room_id, operator=operator)
    if not result.get("success"):
        return jsonify(result), 400
    return jsonify(result)

@api_bp.route("/nilm/simulate", methods=["POST"])
def simulate_nilm_scenario():
    data = request.get_json() or {}
    scenario_id = int(data.get("scenario_id", 1))
    target_room_id = data.get("target_room_id")
    fast_forward = bool(data.get("fast_forward", True))
    result = _room_mgr.trigger_nilm_scenario(scenario_id, target_room_id=target_room_id, fast_forward=fast_forward)
    return jsonify(result)

@api_bp.route("/events/trips", methods=["GET"])
def get_trip_events():
    room_id = request.args.get("room_id")
    limit = int(request.args.get("limit", 50))
    events = _room_mgr.get_trip_events(room_id=room_id, limit=limit)
    return jsonify({"status": "success", "count": len(events), "events": events})

@api_bp.route("/settings", methods=["GET", "POST"])
def handle_system_settings():
    if request.method == "POST":
        data = request.get_json()
        if not data or not isinstance(data, dict):
            return jsonify({"status": "error", "message": "Invalid JSON payload provided."}), 400

        # Validate Maximum Room Power Limit (W)
        if "high_power_threshold_w" in data:
            val = data["high_power_threshold_w"]
            if val is None or str(val).strip() == "":
                return jsonify({"status": "error", "message": "Maximum Room Power Limit cannot be empty."}), 400
            try:
                high_val = float(val)
                if high_val <= 0:
                    return jsonify({"status": "error", "message": "Maximum Room Power Limit must be a positive number greater than zero."}), 400
                data["high_power_threshold_w"] = str(round(high_val, 1))
            except (ValueError, TypeError):
                return jsonify({"status": "error", "message": "Maximum Room Power Limit must be a valid numeric value."}), 400

        # Validate Preferred Optimization Target (W)
        if "default_optimization_target_w" in data:
            val = data["default_optimization_target_w"]
            if val is not None and str(val).strip() != "":
                try:
                    t_val = float(val)
                    if t_val <= 0:
                        return jsonify({"status": "error", "message": "Optimization Target must be greater than zero."}), 400
                    data["default_optimization_target_w"] = str(round(t_val, 1))
                except (ValueError, TypeError):
                    return jsonify({"status": "error", "message": "Optimization Target must be a valid numeric value."}), 400

        # Validate Optimization Tolerance (W)
        if "optimization_tolerance_w" in data:
            val = data["optimization_tolerance_w"]
            if val is not None and str(val).strip() != "":
                try:
                    tol_val = float(val)
                    if tol_val < 0:
                        return jsonify({"status": "error", "message": "Optimization tolerance cannot be negative."}), 400
                    data["optimization_tolerance_w"] = str(round(tol_val, 1))
                except (ValueError, TypeError):
                    return jsonify({"status": "error", "message": "Optimization tolerance must be a numeric value."}), 400

        # Validate Vacant Room Wattage Threshold (W) - kept independent
        if "empty_room_threshold_w" in data:
            val = data["empty_room_threshold_w"]
            if val is None or str(val).strip() == "":
                return jsonify({"status": "error", "message": "Vacant Room Wattage Threshold cannot be empty."}), 400
            try:
                empty_val = float(val)
                if empty_val < 0:
                    return jsonify({"status": "error", "message": "Vacant Room Wattage Threshold cannot be negative."}), 400
                data["empty_room_threshold_w"] = str(round(empty_val, 1))
            except (ValueError, TypeError):
                return jsonify({"status": "error", "message": "Vacant Room Wattage Threshold must be a valid numeric value."}), 400

        # Validate Persistence Window (minutes)
        if "persistence_window_min" in data:
            val = data["persistence_window_min"]
            if val is None or str(val).strip() == "":
                return jsonify({"status": "error", "message": "Persistence window cannot be empty."}), 400
            try:
                p_val = float(val)
                if p_val <= 0:
                    return jsonify({"status": "error", "message": "Persistence window must be greater than zero."}), 400
                data["persistence_window_min"] = str(int(p_val))
            except (ValueError, TypeError):
                return jsonify({"status": "error", "message": "Persistence window must be a valid number of minutes."}), 400

        # Validate Continuous Geyser Run Limit (minutes)
        if "geyser_persistence_min" in data:
            val = data["geyser_persistence_min"]
            if val is None or str(val).strip() == "":
                return jsonify({"status": "error", "message": "Continuous geyser limit cannot be empty."}), 400
            try:
                g_val = float(val)
                if g_val <= 0:
                    return jsonify({"status": "error", "message": "Continuous geyser limit must be greater than zero."}), 400
                data["geyser_persistence_min"] = str(int(g_val))
            except (ValueError, TypeError):
                return jsonify({"status": "error", "message": "Continuous geyser limit must be a valid number of minutes."}), 400

        # Strictly enforce safety lock: real hardware switching permanently disabled
        data["real_hardware_relay_enabled"] = "0"

        _room_mgr.update_system_settings(data)
        updated = _room_mgr.get_system_settings()
        return jsonify({
            "status": "success",
            "message": "System operational threshold policies updated and synchronized successfully.",
            "settings": updated
        })
    else:
        settings = _room_mgr.get_system_settings()
        return jsonify({"status": "success", "settings": settings})

@api_bp.route("/simulator/reset-demo", methods=["POST"])
@api_bp.route("/rooms/reset-simulation", methods=["POST"])
def reset_demo_simulation():
    data = request.get_json() or {}
    operator = data.get("operator", "Hostel Warden")
    from services.live_power_simulator import live_simulator
    result = live_simulator.reset(operator=operator)
    result["simulation"] = live_simulator.get_status()
    return jsonify(result)

# -------------------------------------------------------------------------
# 20. Live Power Simulator APIs
# -------------------------------------------------------------------------
@api_bp.route("/simulation/status", methods=["GET"])
def get_simulation_status():
    from services.live_power_simulator import live_simulator
    return jsonify({
        "status": "success",
        "simulation": live_simulator.get_status()
    })

@api_bp.route("/simulation/start", methods=["POST"])
def start_simulation():
    from services.live_power_simulator import live_simulator
    live_simulator.start()
    return jsonify({
        "status": "success",
        "message": "Simulation started",
        "simulation": live_simulator.get_status()
    })

@api_bp.route("/simulation/pause", methods=["POST"])
def pause_simulation():
    from services.live_power_simulator import live_simulator
    live_simulator.pause()
    return jsonify({
        "status": "success",
        "message": "Simulation paused",
        "simulation": live_simulator.get_status()
    })

@api_bp.route("/simulation/resume", methods=["POST"])
def resume_simulation():
    from services.live_power_simulator import live_simulator
    live_simulator.resume()
    return jsonify({
        "status": "success",
        "message": "Simulation resumed",
        "simulation": live_simulator.get_status()
    })

@api_bp.route("/simulation/reset", methods=["POST"])
def reset_simulation():
    data = request.get_json() or {}
    operator = data.get("operator", "Hostel Warden")
    from services.live_power_simulator import live_simulator
    result = live_simulator.reset(operator=operator)
    return jsonify({
        "status": "success",
        "message": "Simulation reset successfully",
        "reset_result": result,
        "simulation": live_simulator.get_status()
    })

@api_bp.route("/simulation/step", methods=["POST"])
def step_simulation():
    data = request.get_json() or {}
    elapsed = float(data.get("elapsed_seconds", 10.0))
    from services.live_power_simulator import live_simulator
    updated_rooms = live_simulator.step(elapsed_seconds=elapsed)
    return jsonify({
        "status": "success",
        "message": f"Simulated {elapsed}s step executed",
        "updated_count": len(updated_rooms),
        "simulation": live_simulator.get_status()
    })

@api_bp.route("/rooms/<room_id>/simulation-profile", methods=["POST"])
def set_room_simulation_profile(room_id):
    data = request.get_json() or {}
    profile = data.get("profile")
    if not profile:
        return jsonify({"status": "error", "message": "Missing 'profile' field in JSON request body."}), 400
    from services.live_power_simulator import live_simulator
    res = live_simulator.set_room_profile(room_id, profile)
    if not res.get("success"):
        return jsonify({"status": "error", "message": res.get("error", "Failed to update profile")}), 400
    return jsonify({
        "status": "success",
        "room_id": room_id,
        "simulation_profile": res["simulation_profile"],
        "message": f"Room {room_id} profile set to {res['simulation_profile']}"
    })




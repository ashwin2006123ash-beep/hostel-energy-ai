import json
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from config import Config
from database import get_db_connection

class ElectricalFaultEarlyWarningEngine:
    """
    Electrical Fault Early Warning Engine.
    Detects persistent abnormal consumption patterns indicative of equipment failure,
    ground leakage, stuck pump contactors, or electrical insulation breakdown.
    
    Adheres strictly to the requirement: Does not assert definitive guilt or cause;
    identifies persistent statistical anomalies requiring electrical audit.
    """
    def __init__(self):
        pass

    def scan_telemetry_for_faults(self, df=None):
        """
        Scans historical telemetry dataframe or SQLite readings for persistent fault signatures.
        Returns list of active fault warning dictionaries.
        """
        if df is None:
            conn = get_db_connection()
            df = pd.read_sql_query("SELECT * FROM readings ORDER BY timestamp ASC", conn)
            conn.close()

        if df.empty:
            return []

        df = df.copy()
        df["parsed_timestamp"] = pd.to_datetime(df["timestamp"])
        df["date"] = df["parsed_timestamp"].dt.date
        df["hour"] = df["parsed_timestamp"].dt.hour

        warnings = []

        # Analyze each block individually
        for block_id, block_df in df.groupby("block_id"):
            # 1. Pattern A: Baseload Creep (Evaluate 02:00 - 05:00 AM minimum draw per day)
            night_df = block_df[block_df["hour"].isin([2, 3, 4])]
            if not night_df.empty:
                daily_baseload = night_df.groupby("date")["power_kw"].min().reset_index()
                daily_baseload = daily_baseload.sort_values("date")

                if len(daily_baseload) >= 4:
                    kw_values = daily_baseload["power_kw"].values
                    dates = daily_baseload["date"].values

                    # Check for monotonic or significant upward drift over consecutive days
                    # E.g., if baseload has increased by > 3.0 kW over 3+ days
                    drift_window = 4
                    for i in range(len(kw_values) - drift_window + 1):
                        window_vals = kw_values[i : i + drift_window]
                        drift_delta = window_vals[-1] - window_vals[0]
                        
                        # If baseload continuously trends upward by >= 2.5 kW
                        if drift_delta >= 2.5 and all(np.diff(window_vals) >= -0.2):
                            start_date = str(dates[i])
                            end_date = str(dates[i + drift_window - 1])
                            severity = "CRITICAL" if drift_delta >= 4.5 else "WARNING"

                            warning_obj = {
                                "block_id": block_id,
                                "pattern_type": "PERSISTENT_BASELOAD_CREEP",
                                "first_detected": f"{start_date} 03:00:00",
                                "last_detected": f"{end_date} 03:00:00",
                                "persistence_days": drift_window,
                                "severity": severity,
                                "baseline_drift_kw": round(float(drift_delta), 2),
                                "diagnostic_evidence": (
                                    f"Night baseline power (02:00-05:00 AM) rose from {round(window_vals[0], 2)} kW "
                                    f"to {round(window_vals[-1], 2)} kW (+{round(drift_delta, 2)} kW) over {drift_window} consecutive days. "
                                    "Continuous nighttime elevation independent of occupancy suggests ground leakage, "
                                    "insulation degradation, or continuous auxiliary equipment operation."
                                ),
                                "recommended_inspection": (
                                    "Perform insulation resistance test (Megger test) on main busbars; "
                                    "check submersible pump automatic float switch; inspect capacitor bank contactors."
                                )
                            }
                            warnings.append(warning_obj)
                            break # One warning per block window is sufficient

            # 2. Pattern B: High Volatility & Intermittent Spiking (Fluctuation without occupancy change)
            # Evaluate standard deviation of power within stable low-occupancy hours
            low_occ_df = block_df[block_df["occupancy_rate"] < 0.25]
            if len(low_occ_df) >= 12:
                recent_low_occ = low_occ_df.tail(24)
                power_std = float(recent_low_occ["power_kw"].std())
                if power_std > 5.5:
                    warnings.append({
                        "block_id": block_id,
                        "pattern_type": "VOLATILITY_SURGE_UNSTABLE_LOAD",
                        "first_detected": str(recent_low_occ["timestamp"].min()),
                        "last_detected": str(recent_low_occ["timestamp"].max()),
                        "persistence_days": 2,
                        "severity": "WARNING",
                        "baseline_drift_kw": round(power_std, 2),
                        "diagnostic_evidence": (
                            f"Unusual active power standard deviation (σ={round(power_std, 2)} kW) during low-occupancy intervals. "
                            "Indicates rapid intermittent load cycling, potential loose electrical terminations, or cycling compressor fault."
                        ),
                        "recommended_inspection": (
                            "Thermographic infrared camera inspection of circuit breaker panels for hot spots; "
                            "torque-check terminal connections."
                        )
                    })

        return warnings

    def sync_warnings_to_db(self, warnings=None):
        """Persists detected warnings into SQLite fault_warnings table."""
        if warnings is None:
            warnings = self.scan_telemetry_for_faults()

        conn = get_db_connection()
        cursor = conn.cursor()

        # Clear older unresolved warnings to avoid duplicate spamming
        cursor.execute("DELETE FROM fault_warnings WHERE resolved = 0")

        for w in warnings:
            cursor.execute("""
                INSERT INTO fault_warnings (
                    block_id, pattern_type, first_detected, last_detected,
                    persistence_days, severity, baseline_drift_kw,
                    diagnostic_evidence, recommended_inspection, resolved
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
            """, (
                w["block_id"],
                w["pattern_type"],
                w["first_detected"],
                w["last_detected"],
                w["persistence_days"],
                w["severity"],
                w["baseline_drift_kw"],
                w["diagnostic_evidence"],
                w["recommended_inspection"]
            ))

        conn.commit()
        conn.close()
        return len(warnings)

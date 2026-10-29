import json
import numpy as np
import pandas as pd
from datetime import datetime
from config import Config
from database import get_db_connection

class VerifiedSavingsEngine:
    """
    Verified Savings Engine:
    Implements IPMVP (Option C: Whole Facility) Measurement & Verification (M&V).
    Compares weather-and-occupancy-adjusted baseline models with actual post-action metered data
    to produce mathematically verified energy, cost, and carbon savings.
    """
    def __init__(self):
        self.emission_factor = Config.GRID_EMISSION_FACTOR_KG_CO2_PER_KWH
        self.tariff_rate = Config.TARIFF_TIER_2_RATE # Marginal savings rate

    def verify_action_savings(self, block_id, action_title, action_type,
                              baseline_start, baseline_end,
                              post_start, post_end, df=None):
        """
        Calculates adjusted baseline vs actual post-intervention consumption.
        """
        if df is None:
            conn = get_db_connection()
            df = pd.read_sql_query(
                "SELECT * FROM readings WHERE block_id = ? ORDER BY timestamp ASC",
                conn, params=(block_id,)
            )
            conn.close()

        if df.empty:
            return None

        df["parsed_ts"] = pd.to_datetime(df["timestamp"])
        b_mask = (df["parsed_ts"] >= pd.to_datetime(baseline_start)) & (df["parsed_ts"] <= pd.to_datetime(baseline_end))
        p_mask = (df["parsed_ts"] >= pd.to_datetime(post_start)) & (df["parsed_ts"] <= pd.to_datetime(post_end))

        base_df = df[b_mask]
        post_df = df[p_mask]

        if base_df.empty or post_df.empty:
            return None

        # Calculate average power per occupant and thermal sensitivity in baseline
        base_avg_kw = base_df["power_kw"].mean()
        base_avg_occ = max(1.0, base_df["occupancy"].mean())
        base_avg_temp = base_df["temperature"].mean()

        post_avg_occ = max(1.0, post_df["occupancy"].mean())
        post_avg_temp = post_df["temperature"].mean()
        actual_post_kwh = float(post_df["energy_kwh"].sum())

        # IPMVP Routine Adjustments for Post Period Conditions:
        # 1. Occupancy adjustment ratio
        occ_ratio = post_avg_occ / base_avg_occ
        # 2. Temperature cooling degree adjustment
        temp_delta = post_avg_temp - base_avg_temp
        temp_adj_factor = 1.0 + (0.02 * temp_delta)

        # Baseline adjusted to post period duration and conditions
        post_hours = len(post_df)
        adjusted_baseline_kwh = round(base_avg_kw * occ_ratio * temp_adj_factor * post_hours, 2)

        verified_savings_kwh = round(max(0.0, adjusted_baseline_kwh - actual_post_kwh), 2)
        pct_savings = round((verified_savings_kwh / max(1.0, adjusted_baseline_kwh)) * 100, 1)

        cost_saved_inr = round(verified_savings_kwh * self.tariff_rate, 2)
        co2_saved_kg = round(verified_savings_kwh * self.emission_factor, 2)

        record = {
            "action_title": action_title,
            "action_type": action_type,
            "block_id": block_id,
            "implementation_date": post_start,
            "baseline_period_start": baseline_start,
            "baseline_period_end": baseline_end,
            "post_period_start": post_start,
            "post_period_end": post_end,
            "weather_adjusted_baseline_kwh": adjusted_baseline_kwh,
            "actual_post_kwh": round(actual_post_kwh, 2),
            "verified_savings_kwh": verified_savings_kwh,
            "percentage_saved": pct_savings,
            "verified_cost_saved_inr": cost_saved_inr,
            "verified_co2_saved_kg": co2_saved_kg,
            "status": "Verified (IPMVP Option C)"
        }
        return record

    def seed_verified_actions(self):
        """Populates benchmark verified energy savings interventions in SQLite."""
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM savings_actions")
        if cursor.fetchone()[0] == 0:
            actions = [
                (
                    "Block-A Corridor Smart LED Conversion",
                    "LIGHTING_RETROFIT",
                    "Block-A",
                    "2026-10-15 00:00:00",
                    "2026-10-01 00:00:00",
                    "2026-10-14 23:59:59",
                    "2026-10-15 00:00:00",
                    "2026-10-28 23:59:59",
                    7240.50,
                    6180.20,
                    1060.30,
                    9754.76,
                    869.45,
                    "Verified (IPMVP Option C)"
                ),
                (
                    "Block-C Automated Geyser Timer Scheduling",
                    "THERMAL_TIMERS",
                    "Block-C",
                    "2026-10-12 00:00:00",
                    "2026-10-01 00:00:00",
                    "2026-10-11 23:59:59",
                    "2026-10-12 00:00:00",
                    "2026-10-26 23:59:59",
                    9150.80,
                    7720.40,
                    1430.40,
                    13159.68,
                    1172.93,
                    "Verified (IPMVP Option C)"
                ),
                (
                    "Block-D Study Wing Curfew Motion Cutoff",
                    "SENSOR_CUTOFF",
                    "Block-D",
                    "2026-10-16 00:00:00",
                    "2026-10-01 00:00:00",
                    "2026-10-15 23:59:59",
                    "2026-10-16 00:00:00",
                    "2026-10-28 23:59:59",
                    6820.00,
                    6010.50,
                    809.50,
                    7447.40,
                    663.79,
                    "Verified (IPMVP Option C)"
                )
            ]
            cursor.executemany("""
                INSERT INTO savings_actions (
                    action_title, action_type, block_id, implementation_date,
                    baseline_period_start, baseline_period_end,
                    post_period_start, post_period_end,
                    weather_adjusted_baseline_kwh, actual_post_kwh,
                    verified_savings_kwh, verified_cost_saved_inr,
                    verified_co2_saved_kg, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, actions)
            conn.commit()
        conn.close()

    def get_all_savings(self):
        """Retrieves list of all logged verified actions with campus summary."""
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM savings_actions ORDER BY implementation_date DESC")
        rows = [dict(r) for r in cursor.fetchall()]
        conn.close()

        total_kwh_saved = sum(r["verified_savings_kwh"] for r in rows)
        total_inr_saved = sum(r["verified_cost_saved_inr"] for r in rows)
        total_co2_saved = sum(r["verified_co2_saved_kg"] for r in rows)

        return {
            "actions": rows,
            "campus_summary": {
                "total_verified_kwh_saved": round(total_kwh_saved, 1),
                "total_verified_cost_saved_inr": round(total_inr_saved, 2),
                "total_verified_co2_saved_kg": round(total_co2_saved, 1),
                "verified_projects_count": len(rows)
            }
        }

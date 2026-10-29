import numpy as np
import pandas as pd
from config import Config
from database import get_db_connection

class FairEfficiencyLeague:
    """
    Fair Energy Efficiency League:
    Normalizes energy telemetry across distinct hostel blocks based on occupancy headcount,
    usable floor area (m²), and operational schedule to rank blocks equitably.
    """
    def __init__(self):
        self.blocks = Config.HOSTEL_BLOCKS

    def compute_league_standings(self, df=None):
        """
        Calculates normalized league metrics for each hostel block.
        """
        if df is None:
            conn = get_db_connection()
            df = pd.read_sql_query("SELECT * FROM readings", conn)
            conn.close()

        if df.empty:
            return []

        df = df.copy()
        df["parsed_ts"] = pd.to_datetime(df["timestamp"])
        df["hour"] = df["parsed_ts"].dt.hour

        standings = []

        for block_id, meta in self.blocks.items():
            b_df = df[df["block_id"] == block_id]
            if b_df.empty:
                continue

            capacity = meta["capacity"]
            area_sqm = meta["floor_area_sqm"]

            total_kwh = float(b_df["energy_kwh"].sum())
            total_hours = len(b_df)
            total_days = max(1.0, total_hours / 24.0)

            # Cumulative occupant-days
            avg_occupancy = float(b_df["occupancy"].mean())
            total_occupant_days = max(1.0, avg_occupancy * total_days)

            # 1. Metric: Specific Energy Consumption (kWh per occupant-day)
            sec_kwh_per_occ_day = round(total_kwh / total_occupant_days, 2)

            # 2. Metric: Energy Use Intensity (EUI in kWh / m² / month)
            # Extrapolate to 30 days
            month_factor = 30.0 / total_days
            eui_kwh_per_sqm_month = round((total_kwh * month_factor) / area_sqm, 2)

            # 3. Metric: Off-hours night waste (01:00 to 05:00 AM)
            night_df = b_df[b_df["hour"].isin([1, 2, 3, 4])]
            night_kwh = float(night_df["energy_kwh"].sum()) if not night_df.empty else 0.0
            night_waste_ratio = round((night_kwh / max(1.0, total_kwh)) * 100, 1)

            # 4. Metric: Average Power in kW
            avg_power_kw = round(float(b_df["power_kw"].mean()), 2)
            peak_power_kw = round(float(b_df["power_kw"].max()), 2)

            # 5. Composite Score Calculation (0 to 100 points, higher is more efficient)
            # Lower SEC and lower EUI increase score
            # Benchmark SEC: 3.5 kWh/occ-day (100 pts) -> 7.0 kWh/occ-day (40 pts)
            sec_score = np.clip(100.0 - (sec_kwh_per_occ_day - 3.0) * 18.0, 30.0, 100.0)
            eui_score = np.clip(100.0 - (eui_kwh_per_sqm_month - 4.5) * 15.0, 30.0, 100.0)
            night_score = np.clip(100.0 - (night_waste_ratio - 12.0) * 3.5, 30.0, 100.0)

            composite_index = round(float(0.45 * sec_score + 0.35 * eui_score + 0.20 * night_score), 1)

            # Star rating
            if composite_index >= 88:
                star_rating = 5
                tier = "Platinum - Eco Pioneer"
            elif composite_index >= 76:
                star_rating = 4
                tier = "Gold - Energy Efficient"
            elif composite_index >= 64:
                star_rating = 3
                tier = "Silver - Standard Compliance"
            else:
                star_rating = 2
                tier = "Bronze - High Conservation Potential"

            # Badges
            badges = []
            if sec_kwh_per_occ_day <= 3.8:
                badges.append({"label": "Top Occupant Efficiency", "color": "emerald"})
            if night_waste_ratio <= 14.0:
                badges.append({"label": "Low Night Waste", "color": "cyan"})
            if eui_kwh_per_sqm_month <= 5.0:
                badges.append({"label": "Compact Footprint", "color": "blue"})

            standings.append({
                "block_id": block_id,
                "block_name": meta["name"],
                "block_type": meta["type"],
                "capacity": capacity,
                "floor_area_sqm": area_sqm,
                "floors": meta["floors"],
                "total_kwh": round(total_kwh, 1),
                "avg_occupancy": round(avg_occupancy, 1),
                "sec_kwh_per_occ_day": sec_kwh_per_occ_day,
                "eui_kwh_per_sqm_month": eui_kwh_per_sqm_month,
                "night_waste_ratio_pct": night_waste_ratio,
                "avg_power_kw": avg_power_kw,
                "peak_power_kw": peak_power_kw,
                "composite_index": composite_index,
                "star_rating": star_rating,
                "tier": tier,
                "badges": badges
            })

        # Sort by composite_index descending
        standings.sort(key=lambda x: x["composite_index"], reverse=True)
        for idx, item in enumerate(standings, 1):
            item["rank"] = idx

        return standings

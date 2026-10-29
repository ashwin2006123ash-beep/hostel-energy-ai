import numpy as np
import pandas as pd
from config import Config

class VirtualApplianceFingerprinter:
    """
    Virtual Appliance Fingerprinting Service.
    Decomposes aggregate electrical telemetry into estimated end-use appliance categories
    using context-aware heuristic decomposition and thermal modeling.
    
    IMPORTANT: This is explicitly labeled as an ESTIMATE / HEURISTIC DISAGGREGATION.
    Sub-metering or physical current transducers are required for certified sub-circuit measurement.
    """
    def __init__(self):
        self.disclaimer = (
            "NOTICE: Virtual appliance breakdowns are algorithmic estimates derived from "
            "temporal context, occupancy ratios, and thermodynamic cooling demand. "
            "They serve as non-intrusive diagnostic approximations."
        )

    def fingerprint_reading(self, power_kw, occupancy, temperature, hour, block_id="Block-A"):
        """
        Estimates the power breakdown (in kW and %) for a single telemetry instant.
        """
        block_info = Config.HOSTEL_BLOCKS.get(block_id, {})
        capacity = block_info.get("capacity", 200)
        floors = block_info.get("floors", 3)
        
        # 1. Base / Standby Load (Routers, emergency lights, CCTV, idle equipment)
        # Consistent round-the-clock draw
        base_load = round(float(2.0 * (capacity / 100.0)), 2)
        base_load = min(base_load, power_kw * 0.4)

        remaining_kw = max(0.0, power_kw - base_load)

        # 2. Lighting Load
        # Depends on time of day and occupancy
        if hour >= 18 or hour < 6:
            lighting_est = 0.016 * occupancy + (0.4 * floors)
        elif 6 <= hour < 9 or 16 <= hour < 18:
            lighting_est = 0.007 * occupancy + (0.2 * floors)
        else:
            lighting_est = 0.002 * occupancy + (0.1 * floors)
        lighting_kw = round(float(min(lighting_est, remaining_kw * 0.45)), 2)
        remaining_kw = max(0.0, remaining_kw - lighting_kw)

        # 3. Cooling & Fan Load
        # Driven by ambient temperature above 23°C and student count
        temp_factor = max(0.0, temperature - 23.0)
        cooling_est = (0.024 * occupancy) * (1.0 + 0.1 * temp_factor)
        cooling_kw = round(float(min(cooling_est, remaining_kw * 0.70)), 2)
        remaining_kw = max(0.0, remaining_kw - cooling_kw)

        # 4. Plug Loads (Laptops, mobile devices, study lights)
        plug_est = 0.030 * occupancy
        plug_kw = round(float(min(plug_est, remaining_kw * 0.85)), 2)
        remaining_kw = max(0.0, remaining_kw - plug_kw)

        # 5. High-Wattage / Heating / Anomalous Spike (Geysers, kettles, irons, unmonitored heaters)
        # Anything remaining above baseline expectations falls here
        high_draw_kw = round(float(remaining_kw), 2)

        total_kw = max(0.1, base_load + lighting_kw + cooling_kw + plug_kw + high_draw_kw)

        categories = {
            "standby_base": {
                "name": "Base & Standby Load",
                "kw": base_load,
                "percentage": round((base_load / total_kw) * 100, 1),
                "description": "CCTV, Wi-Fi access points, exit lights, corridor base fixtures"
            },
            "cooling_fans": {
                "name": "Cooling & Ceiling Fans",
                "kw": cooling_kw,
                "percentage": round((cooling_kw / total_kw) * 100, 1),
                "description": "Ceiling fans, exhaust ventilation, room cooling"
            },
            "lighting": {
                "name": "Lighting (Corridor & Rooms)",
                "kw": lighting_kw,
                "percentage": round((lighting_kw / total_kw) * 100, 1),
                "description": "Room fluorescent/LED tubes, study lamps, hallway fixtures"
            },
            "plug_electronics": {
                "name": "Plug Loads & Electronics",
                "kw": plug_kw,
                "percentage": round((plug_kw / total_kw) * 100, 1),
                "description": "Laptops, smartphones, audio devices, desktop monitors"
            },
            "high_wattage_thermal": {
                "name": "High-Wattage / Thermal Appliances",
                "kw": high_draw_kw,
                "percentage": round((high_draw_kw / total_kw) * 100, 1),
                "description": "Water heaters/geysers, electric kettles, irons, or unexpected excess surge"
            }
        }

        return {
            "is_estimate": True,
            "confidence_level": "MODERATE_HEURISTIC_ESTIMATE",
            "total_measured_kw": power_kw,
            "disaggregated_kw": round(total_kw, 2),
            "disclaimer": self.disclaimer,
            "categories": categories
        }

    def fingerprint_dataframe(self, df):
        """
        Computes aggregate appliance fingerprint breakdown over a historical dataset.
        """
        totals = {
            "standby_base": 0.0,
            "cooling_fans": 0.0,
            "lighting": 0.0,
            "plug_electronics": 0.0,
            "high_wattage_thermal": 0.0
        }

        # Sample up to 500 rows for fast statistical distribution
        sample_df = df.sample(min(len(df), 500), random_state=Config.RANDOM_SEED)

        for _, row in sample_df.iterrows():
            hour = pd.to_datetime(row["timestamp"]).hour
            fp = self.fingerprint_reading(
                power_kw=float(row["power_kw"]),
                occupancy=int(row["occupancy"]),
                temperature=float(row["temperature"]),
                hour=hour,
                block_id=str(row["block_id"])
            )
            for cat_key, cat_val in fp["categories"].items():
                totals[cat_key] += cat_val["kw"]

        sum_all = sum(totals.values()) or 1.0
        summary_percentages = {
            k: round((v / sum_all) * 100, 1) for k, v in totals.items()
        }

        return {
            "is_estimate": True,
            "confidence_level": "MODERATE_HEURISTIC_ESTIMATE",
            "disclaimer": self.disclaimer,
            "category_percentages": summary_percentages,
            "sample_size": len(sample_df)
        }

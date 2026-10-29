import json
import numpy as np
import pandas as pd
from config import Config

class EnergyDetective:
    """
    AI Energy Detective: Explains anomalies, aggregates multi-factor evidence,
    and ranks probable diagnostic causes.
    
    Adheres strictly to ethical AI guidelines:
    - Never asserts electricity theft or illicit activities as proven facts.
    - Evaluates data-driven evidence to propose prioritized audit hypotheses.
    """
    def __init__(self):
        self.disclaimer = Config.DISCLAIMER_TEXT

    def analyze_anomaly(self, anomaly_dict):
        """
        Analyzes a single anomaly record and produces an evidence-backed diagnostic report.
        anomaly_dict keys:
            power_kw, expected_kw, residual_kw, occupancy, occupancy_rate,
            temperature, humidity, day_type, timestamp, block_id, severity
        """
        power_kw = float(anomaly_dict.get("power_kw", 0.0))
        expected_kw = float(anomaly_dict.get("expected_kw", power_kw))
        residual_kw = float(anomaly_dict.get("residual_kw", power_kw - expected_kw))
        occupancy = int(anomaly_dict.get("occupancy", 0))
        occ_rate = float(anomaly_dict.get("occupancy_rate", 0.5))
        temperature = float(anomaly_dict.get("temperature", 28.0))
        day_type = str(anomaly_dict.get("day_type", "Weekday"))
        block_id = str(anomaly_dict.get("block_id", "Block-A"))
        timestamp = str(anomaly_dict.get("timestamp", ""))

        try:
            hour = pd.to_datetime(timestamp).hour
        except Exception:
            hour = 12

        candidates = []

        # -------------------------------------------------------------
        # Hypothesis 1: Unattended Appliances in Vacant Rooms (Class Hours)
        # -------------------------------------------------------------
        h1_evidence = []
        h1_score = 0.0

        if 9 <= hour <= 16 and day_type == "Weekday":
            h1_score += 0.45
            h1_evidence.append(f"Occurred during academic lecture hours ({hour:02d}:00) on a {day_type}.")
        
        if occ_rate <= 0.30:
            h1_score += 0.40
            h1_evidence.append(f"Hostel occupancy is unusually low ({round(occ_rate * 100, 1)}%, {occupancy} students present).")
        
        if residual_kw >= 4.0:
            h1_score += 0.15
            h1_evidence.append(f"Substantial residual draw (+{round(residual_kw, 1)} kW) despite largely vacant premises.")

        if h1_evidence:
            candidates.append({
                "cause_code": "UNATTENDED_VACANT_ROOM_DRAW",
                "title": "Unattended Equipment in Vacant Dormitories",
                "confidence": min(0.95, round(h1_score, 2)),
                "evidence": h1_evidence,
                "action": "Dispatch floor prefect to verify vacant rooms; inspect common rooms for left-on lighting and fans.",
                "category": "Behavioral Waste"
            })

        # -------------------------------------------------------------
        # Hypothesis 2: Nighttime High-Power Appliance or Bypass (00:00 - 05:00)
        # -------------------------------------------------------------
        h2_evidence = []
        h2_score = 0.0

        if 0 <= hour <= 5:
            h2_score += 0.50
            h2_evidence.append(f"Recorded during deep sleep curfew hours ({hour:02d}:00) when active occupancy should be minimal.")
            if residual_kw >= 5.0:
                h2_score += 0.35
                h2_evidence.append(f"Elevated night spike (+{round(residual_kw, 1)} kW) exceeds standard standby baseload by >250%.")
            if day_type == "Exam_Day":
                h2_score -= 0.20
                h2_evidence.append("Exam period active: students may be legitimately awake group-studying with laptops and lights.")
            else:
                h2_evidence.append(f"Typical night draw is ~{round(expected_kw, 1)} kW, indicating potential unmonitored heating elements or geyser override.")

        if h2_evidence:
            candidates.append({
                "cause_code": "NIGHT_HIGH_WATTAGE_APPLIANCE",
                "title": "Late-Night High-Wattage Load or Heating Element",
                "confidence": min(0.92, round(h2_score, 2)),
                "evidence": h2_evidence,
                "action": "Review wing electrical distribution board; inspect geyser timer relays and study room heating fixtures.",
                "category": "Potential Appliance Misuse / Timer Failure"
            })

        # -------------------------------------------------------------
        # Hypothesis 3: Ambient Weather / Severe Thermal Surge
        # -------------------------------------------------------------
        h3_evidence = []
        h3_score = 0.0

        if temperature >= 33.0:
            h3_score += 0.50
            h3_evidence.append(f"High ambient temperature of {temperature}°C increases cooling and fan load exponentially.")
            if 12 <= hour <= 18:
                h3_score += 0.30
                h3_evidence.append(f"Peak afternoon solar radiation coincided with high building thermal inertia.")
            if occ_rate >= 0.5:
                h3_score += 0.15
                h3_evidence.append(f"Occupancy is active ({round(occ_rate * 100)}%), driving maximum fan and ventilation usage.")

        if h3_evidence:
            candidates.append({
                "cause_code": "THERMAL_COOLING_SURGE",
                "title": "Severe Ambient Heat / Thermal Cooling Overload",
                "confidence": min(0.90, round(h3_score, 2)),
                "evidence": h3_evidence,
                "action": "Activate passive cooling measures (solar reflective roof shades, cross-ventilation, eco-mode fans).",
                "category": "Weather Impact"
            })

        # -------------------------------------------------------------
        # Hypothesis 4: Morning Geyser / Water Heater Peak Congestion
        # -------------------------------------------------------------
        h4_evidence = []
        h4_score = 0.0

        if 6 <= hour <= 9:
            h4_score += 0.55
            h4_evidence.append(f"Time window ({hour:02d}:00) matches standard morning shower and preparation schedule.")
            if residual_kw >= 4.0:
                h4_score += 0.30
                h4_evidence.append(f"High simultaneous hot water heater demand across multiple wings.")

        if h4_evidence:
            candidates.append({
                "cause_code": "MORNING_GEYSER_CONGESTION",
                "title": "Morning Water Heater / Geyser Peak Congestion",
                "confidence": min(0.88, round(h4_score, 2)),
                "evidence": h4_evidence,
                "action": "Consider staggered geyser timer schedules or heat-pump pre-heating to avoid peak demand tariff penalties.",
                "category": "Demand Congestion"
            })

        # -------------------------------------------------------------
        # Hypothesis 5: Electrical Circuit Basal Leakage / Stuck Contactor
        # -------------------------------------------------------------
        h5_evidence = []
        h5_score = 0.0

        if 2.0 <= residual_kw <= 8.0:
            h5_score += 0.35
            h5_evidence.append(f"Consistent moderate offset (+{round(residual_kw, 1)} kW) typical of stuck pump relay or continuous auxiliary draw.")
            h5_evidence.append("Does not follow normal occupant diurnal curves.")

        if h5_evidence:
            candidates.append({
                "cause_code": "CIRCUIT_BASELINE_DRIFT",
                "title": "Continuous Auxiliary Load / Stuck Relay / Circuit Leakage",
                "confidence": min(0.75, round(h5_score, 2)),
                "evidence": h5_evidence,
                "action": "Check sub-distribution box insulation resistance and water circulation pump float switches.",
                "category": "Electrical Hardware"
            })

        # Sort candidates by confidence descending
        candidates.sort(key=lambda x: x["confidence"], reverse=True)
        top_cause = candidates[0]["title"] if candidates else "Unclassified Telemetry Fluctuation"

        return {
            "primary_cause": top_cause,
            "ranked_causes": candidates,
            "context_summary": {
                "timestamp": timestamp,
                "block_id": block_id,
                "hour": hour,
                "actual_kw": power_kw,
                "expected_kw": expected_kw,
                "residual_kw": residual_kw,
                "occupancy_rate_pct": round(occ_rate * 100, 1),
                "temperature_c": temperature,
                "day_type": day_type
            },
            "disclaimer": self.disclaimer
        }

    def explain_anomalies_batch(self, anomaly_df):
        """Analyzes a batch of detected anomalies and returns list of reports."""
        reports = []
        for _, row in anomaly_df.iterrows():
            rep = self.analyze_anomaly(row.to_dict())
            reports.append(rep)
        return reports

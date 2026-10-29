import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from models.anomaly_detector import ContextAwareAnomalyDetector
from models.consumption_predictor import BaselineConsumptionPredictor
from services.energy_detective import EnergyDetective

@pytest.fixture
def sample_training_data():
    """Generates a small synthetic dataframe for test fixtures."""
    dates = [datetime(2026, 10, 1, 0, 0) + timedelta(hours=i) for i in range(120)]
    rows = []
    for dt in dates:
        hour = dt.hour
        occ = 140 if (hour >= 18 or hour < 8) else 30
        power = 4.0 + (occ * 0.03) + (1.5 if (12 <= hour <= 16) else 0.0)
        rows.append({
            "timestamp": dt.strftime("%Y-%m-%d %H:%M:%S"),
            "block_id": "Block-A",
            "floor": 1,
            "power_kw": round(power, 2),
            "energy_kwh": round(power, 2),
            "occupancy": occ,
            "occupancy_rate": round(occ / 180.0, 2),
            "temperature": 28.0 + 5.0 * np.sin(hour * np.pi / 12),
            "humidity": 60.0,
            "day_type": "Weekday",
            "is_synthetic": 1
        })
    return pd.DataFrame(rows)

def test_baseline_predictor(sample_training_data):
    predictor = BaselineConsumptionPredictor()
    metrics = predictor.fit(sample_training_data)
    assert "r2_score" in metrics
    assert "mae" in metrics
    
    # Predict on test data
    preds = predictor.predict(sample_training_data)
    assert len(preds) == len(sample_training_data)
    assert all(p >= 0.0 for p in preds)

def test_anomaly_detection_pipeline(sample_training_data):
    detector = ContextAwareAnomalyDetector()
    detector.fit(sample_training_data)

    # Normal test sample: should have low anomaly score
    normal_df = sample_training_data.iloc[:5].copy()
    res_normal = detector.detect(normal_df)
    assert "residual_kw" in res_normal.columns
    assert "severity" in res_normal.columns
    assert all(res_normal["severity"].isin(["NORMAL", "LOW"]))

    # Injected severe surge: occupancy 20, power 25.0 kW (normal is ~4.6 kW)
    anom_row = pd.DataFrame([{
        "timestamp": "2026-10-15 11:00:00",
        "block_id": "Block-A",
        "floor": 1,
        "power_kw": 25.0, # Huge surge
        "energy_kwh": 25.0,
        "occupancy": 20,
        "occupancy_rate": 0.11,
        "temperature": 29.0,
        "humidity": 55.0,
        "day_type": "Weekday",
        "is_synthetic": 1
    }])
    res_anom = detector.detect(anom_row)
    assert res_anom["is_anomaly"].values[0] == 1
    assert res_anom["severity"].values[0] in ["HIGH", "CRITICAL"]
    assert res_anom["residual_kw"].values[0] > 10.0

def test_energy_detective_hypotheses():
    detective = EnergyDetective()
    # Case: Empty room high draw during class hours
    diag = detective.analyze_anomaly({
        "timestamp": "2026-10-15 11:00:00",
        "block_id": "Block-A",
        "power_kw": 22.0,
        "expected_kw": 5.0,
        "residual_kw": 17.0,
        "occupancy": 25,
        "occupancy_rate": 0.14,
        "temperature": 28.0,
        "day_type": "Weekday",
        "severity": "CRITICAL"
    })

    assert diag["primary_cause"] != ""
    assert len(diag["ranked_causes"]) > 0
    # Top cause should be related to unattended vacant room draw
    top_cause_code = diag["ranked_causes"][0]["cause_code"]
    assert top_cause_code == "UNATTENDED_VACANT_ROOM_DRAW"
    assert "disclaimer" in diag

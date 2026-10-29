import os
import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from config import Config
from models.consumption_predictor import BaselineConsumptionPredictor
from services.data_processor import engineer_features

ISO_MODEL_FILE = os.path.join(Config.BASE_DIR, "models", "isolation_forest.joblib")

class ContextAwareAnomalyDetector:
    """
    Context-Aware Electricity Anomaly Detector.
    Evaluates observed power against expected baseline predictions (derived from occupancy,
    hour, temperature, day type) and multidimensional Isolation Forest scoring.
    """
    def __init__(self, contamination=Config.ANOMALY_CONTAMINATION):
        self.contamination = contamination
        self.iso_forest = IsolationForest(
            contamination=contamination,
            random_state=Config.RANDOM_SEED,
            n_estimators=100
        )
        self.baseline_predictor = BaselineConsumptionPredictor()
        self.is_trained = False
        self.residual_std = 1.8 # Initial default standard deviation

    def fit(self, df):
        """Fits both the baseline regressor and the Isolation Forest model."""
        # 1. Fit baseline predictor
        self.baseline_predictor.fit(df)
        
        # 2. Compute training residuals
        feat_df = engineer_features(df)
        expected = self.baseline_predictor.predict(df)
        residuals = feat_df["power_kw"].values - expected
        self.residual_std = max(0.8, float(np.std(residuals)))

        # 3. Fit Isolation Forest on multidimensional context
        iso_features = [
            "power_kw",
            "occupancy",
            "temperature",
            "sin_hour",
            "cos_hour",
            "thermal_occupancy_load"
        ]
        X_iso = feat_df[iso_features]
        self.iso_forest.fit(X_iso)
        self.is_trained = True

        # Save model
        os.makedirs(os.path.dirname(ISO_MODEL_FILE), exist_ok=True)
        joblib.dump({
            "iso_forest": self.iso_forest,
            "residual_std": self.residual_std
        }, ISO_MODEL_FILE)

        return {
            "residual_std": round(self.residual_std, 3),
            "baseline_metrics": self.baseline_predictor.metrics
        }

    def load_or_train(self, df=None):
        """Loads models or trains from supplied telemetry."""
        self.baseline_predictor.load_or_train(df)

        if os.path.exists(ISO_MODEL_FILE):
            try:
                saved = joblib.load(ISO_MODEL_FILE)
                self.iso_forest = saved["iso_forest"]
                self.residual_std = saved.get("residual_std", 1.8)
                self.is_trained = True
                return
            except Exception:
                pass

        if df is not None and not df.empty:
            self.fit(df)
        else:
            self.is_trained = True

    def detect(self, df):
        """
        Runs context-aware anomaly detection on telemetry DataFrame.
        Returns enriched DataFrame with expected_kw, residual_kw, anomaly_score, severity, is_anomaly.
        """
        if not self.is_trained:
            self.load_or_train(df)

        results = df.copy()
        
        # 1. Expected Power from Baseline Predictor
        expected_kw = self.baseline_predictor.predict(results)
        results["expected_kw"] = np.round(expected_kw, 2)
        results["residual_kw"] = np.round(results["power_kw"].values - expected_kw, 2)

        # 2. Residual Z-Score (context-aware deviation)
        z_scores = results["residual_kw"] / self.residual_std
        results["residual_zscore"] = np.round(z_scores, 2)

        # 3. Isolation Forest decision function
        feat_df = engineer_features(results)
        iso_features = [
            "power_kw",
            "occupancy",
            "temperature",
            "sin_hour",
            "cos_hour",
            "thermal_occupancy_load"
        ]
        for col in iso_features:
            if col not in feat_df.columns:
                feat_df[col] = 0.0

        # decision_function gives negative values for outliers, positive for inliers
        iso_scores = self.iso_forest.decision_function(feat_df[iso_features])
        # Map to 0 (normal) to 1 (high anomaly)
        # Typically iso_scores range around -0.3 to +0.3
        iso_norm = np.clip(1.0 / (1.0 + np.exp(6.0 * iso_scores)), 0.0, 1.0)
        results["iso_anomaly_score"] = np.round(iso_norm, 3)

        # 4. Composite Calibrated Anomaly Score (0.0 to 1.0)
        # We heavily weight positive excess residuals (unexpected surge) and Isolation Forest
        pos_residual_factor = np.clip(z_scores / 4.0, 0.0, 1.0)
        composite_score = 0.65 * pos_residual_factor + 0.35 * iso_norm
        results["anomaly_score"] = np.round(np.clip(composite_score, 0.0, 1.0), 3)

        # Retrieve active high-power threshold from SQLite system_settings (converted to kW)
        high_limit_kw = 1.2
        try:
            from database import get_db_connection
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM system_settings WHERE key = 'high_power_threshold_w'")
            row = cursor.fetchone()
            conn.close()
            if row and row["value"]:
                high_limit_kw = float(row["value"]) / 1000.0
        except Exception:
            pass

        # 5. Classify Severity
        def classify_severity(row):
            score = row["anomaly_score"]
            residual = row["residual_kw"]
            power = row.get("power_kw", 0.0)

            # Contextually flag power exceeding the configured policy threshold
            if power >= high_limit_kw and residual > 0.5:
                if score >= 0.65 or residual > 6.0:
                    return "CRITICAL"
                return "HIGH"

            # Excess draw thresholds
            if score >= 0.70 or residual > 10.0:
                return "CRITICAL"
            elif score >= 0.50 or residual > 6.0:
                return "HIGH"
            elif score >= 0.35 or residual > 3.5:
                return "MEDIUM"
            elif score >= 0.25 or residual > 2.0:
                return "LOW"
            else:
                return "NORMAL"

        results["severity"] = results.apply(classify_severity, axis=1)
        results["is_anomaly"] = (results["severity"] != "NORMAL").astype(int)

        return results

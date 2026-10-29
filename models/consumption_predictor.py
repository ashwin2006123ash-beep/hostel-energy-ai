import os
import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score
from config import Config
from services.data_processor import engineer_features

MODEL_FILE = os.path.join(Config.BASE_DIR, "models", "baseline_predictor.joblib")

FEATURE_COLS = [
    "sin_hour", "cos_hour",
    "sin_dow", "cos_dow",
    "occupancy",
    "temperature",
    "humidity",
    "cooling_degree_factor",
    "thermal_occupancy_load",
    "is_weekend",
    "is_exam_day",
    "block_Block-A",
    "block_Block-B",
    "block_Block-C",
    "block_Block-D"
]

class BaselineConsumptionPredictor:
    """
    ML model that predicts expected electricity consumption (kW)
    conditioned on contextual variables: occupancy, timestamp, ambient temperature, and day type.
    """
    def __init__(self):
        self.model = GradientBoostingRegressor(
            n_estimators=120,
            learning_rate=0.08,
            max_depth=4,
            random_state=Config.RANDOM_SEED
        )
        self.is_trained = False
        self.metrics = {}

    def fit(self, df):
        """Trains the baseline model on historical telemetry."""
        feat_df = engineer_features(df)
        
        # Ensure all feature columns exist
        for col in FEATURE_COLS:
            if col not in feat_df.columns:
                feat_df[col] = 0

        X = feat_df[FEATURE_COLS]
        y = feat_df["power_kw"]

        # Train/test split by time or stratified
        split_idx = int(len(X) * 0.8)
        X_train, X_test = X.iloc[:split_idx], X.iloc[split_idx:]
        y_train, y_test = y.iloc[:split_idx], y.iloc[split_idx:]

        self.model.fit(X_train, y_train)
        self.is_trained = True

        # Calculate metrics
        y_pred = self.model.predict(X_test)
        self.metrics = {
            "r2_score": round(float(r2_score(y_test, y_pred)), 3),
            "mae": round(float(mean_absolute_error(y_test, y_pred)), 3),
            "rmse": round(float(np.sqrt(mean_squared_error(y_test, y_pred))), 3),
            "train_samples": len(X_train),
            "test_samples": len(X_test)
        }

        # Save model to disk
        os.makedirs(os.path.dirname(MODEL_FILE), exist_ok=True)
        joblib.dump({"model": self.model, "metrics": self.metrics}, MODEL_FILE)
        return self.metrics

    def load_or_train(self, df=None):
        """Loads a pre-trained model or trains a new one if not found."""
        if os.path.exists(MODEL_FILE):
            try:
                saved = joblib.load(MODEL_FILE)
                self.model = saved["model"]
                self.metrics = saved.get("metrics", {})
                self.is_trained = True
                return self.metrics
            except Exception:
                pass

        if df is not None and not df.empty:
            return self.fit(df)
        raise ValueError("Model is not trained and no training data was supplied.")

    def predict(self, df):
        """
        Generates expected power consumption predictions for the given DataFrame.
        Returns numpy array of expected power_kw.
        """
        if not self.is_trained:
            self.load_or_train(df)

        feat_df = engineer_features(df)
        for col in FEATURE_COLS:
            if col not in feat_df.columns:
                feat_df[col] = 0

        X = feat_df[FEATURE_COLS]
        predictions = self.model.predict(X)
        return np.clip(predictions, 0.5, None) # Power cannot be negative

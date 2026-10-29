import os
import io
import numpy as np
import pandas as pd
from datetime import datetime
from config import Config
from database import get_db_connection

REQUIRED_COLUMNS = ["timestamp", "block_id", "power_kw", "occupancy", "temperature"]
OPTIONAL_COLUMNS = ["floor", "humidity", "day_type", "is_synthetic"]

class DataValidationError(Exception):
    def __init__(self, message, errors=None):
        super().__init__(message)
        self.errors = errors or []

def validate_csv_data(filepath_or_buffer):
    """
    Validates an uploaded or local CSV file for required columns, data types,
    acceptable physical ranges, and timestamp parsing.
    Returns: dict with { "valid": bool, "errors": list, "warnings": list, "df": DataFrame, "summary": dict }
    """
    errors = []
    warnings = []

    try:
        if isinstance(filepath_or_buffer, str):
            if not os.path.exists(filepath_or_buffer) or os.path.getsize(filepath_or_buffer) == 0:
                return {"valid": False, "errors": ["The uploaded CSV file is empty."], "warnings": [], "df": None}
            df = pd.read_csv(filepath_or_buffer)
        elif hasattr(filepath_or_buffer, "read"):
            content = filepath_or_buffer.read()
            if not content or len(content.strip()) == 0:
                return {"valid": False, "errors": ["The uploaded CSV file is empty."], "warnings": [], "df": None}
            if isinstance(content, str):
                df = pd.read_csv(io.StringIO(content))
            else:
                df = pd.read_csv(io.BytesIO(content))
        else:
            return {"valid": False, "errors": ["Invalid file input source."], "warnings": [], "df": None}
    except pd.errors.EmptyDataError:
        return {"valid": False, "errors": ["The uploaded CSV file is empty."], "warnings": [], "df": None}
    except Exception as e:
        return {"valid": False, "errors": [f"Could not parse CSV file: {str(e)}"], "warnings": [], "df": None}

    if df.empty:
        return {"valid": False, "errors": ["The uploaded CSV file is empty."], "warnings": [], "df": None}

    # 1. Column header check
    df.columns = [c.strip().lower() for c in df.columns]
    missing_cols = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing_cols:
        errors.append(f"Missing required columns: {', '.join(missing_cols)}. Required are: {', '.join(REQUIRED_COLUMNS)}")
        return {"valid": False, "errors": errors, "warnings": warnings, "df": None}

    # 2. Row count check
    if len(df) > 50000:
        errors.append(f"File contains {len(df)} rows, exceeding maximum limit of 50,000 rows.")
        return {"valid": False, "errors": errors, "warnings": warnings, "df": None}

    # 3. Timestamp parsing
    try:
        df["parsed_timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
        invalid_ts_count = df["parsed_timestamp"].isna().sum()
        if invalid_ts_count > 0:
            errors.append(f"Found {invalid_ts_count} rows with invalid timestamp format. Use YYYY-MM-DD HH:MM:SS format.")
    except Exception as e:
        errors.append(f"Timestamp parsing error: {str(e)}")

    # 4. Numerical range validations
    # Power kW: must be numeric and >= 0.0, <= 500.0 kW
    try:
        df["power_kw"] = pd.to_numeric(df["power_kw"], errors="coerce")
        invalid_power = df["power_kw"].isna().sum()
        if invalid_power > 0:
            errors.append(f"{invalid_power} rows contain non-numeric power_kw values.")
        else:
            neg_power = (df["power_kw"] < 0).sum()
            if neg_power > 0:
                errors.append(f"Negative power values detected in {neg_power} rows. Active power must be >= 0 kW.")
            excess_power = (df["power_kw"] > 500.0).sum()
            if excess_power > 0:
                warnings.append(f"{excess_power} rows have unusually high power draw (>500 kW). Please verify unit scale.")
    except Exception as e:
        errors.append(f"Power validation error: {str(e)}")

    # Occupancy: must be numeric, integer-like >= 0
    try:
        df["occupancy"] = pd.to_numeric(df["occupancy"], errors="coerce")
        invalid_occ = df["occupancy"].isna().sum()
        if invalid_occ > 0:
            errors.append(f"{invalid_occ} rows contain non-numeric occupancy values.")
        else:
            neg_occ = (df["occupancy"] < 0).sum()
            if neg_occ > 0:
                errors.append(f"Negative occupancy detected in {neg_occ} rows.")
            high_occ = (df["occupancy"] > 2000).sum()
            if high_occ > 0:
                warnings.append(f"{high_occ} rows report occupancy > 2,000 students.")
    except Exception as e:
        errors.append(f"Occupancy validation error: {str(e)}")

    # Temperature: must be numeric between -20°C and 65°C
    try:
        df["temperature"] = pd.to_numeric(df["temperature"], errors="coerce")
        invalid_temp = df["temperature"].isna().sum()
        if invalid_temp > 0:
            errors.append(f"{invalid_temp} rows contain non-numeric temperature values.")
        else:
            extreme_temp = ((df["temperature"] < -20) | (df["temperature"] > 65)).sum()
            if extreme_temp > 0:
                warnings.append(f"{extreme_temp} rows have extreme ambient temperatures (<-20°C or >65°C).")
    except Exception as e:
        errors.append(f"Temperature validation error: {str(e)}")

    # 5. Optional columns defaults
    if "humidity" not in df.columns:
        df["humidity"] = 60.0
    else:
        df["humidity"] = pd.to_numeric(df["humidity"], errors="coerce").fillna(60.0)

    if "floor" not in df.columns:
        df["floor"] = 1
    else:
        df["floor"] = pd.to_numeric(df["floor"], errors="coerce").fillna(1).astype(int)

    if "day_type" not in df.columns:
        # Infer day_type based on day of week
        df["day_type"] = df["parsed_timestamp"].dt.dayofweek.apply(
            lambda dow: "Weekend" if dow in [5, 6] else "Weekday"
        )

    if "is_synthetic" not in df.columns:
        df["is_synthetic"] = 0

    if "energy_kwh" not in df.columns:
        # Default assume 1-hour intervals: energy_kwh = power_kw * 1.0
        df["energy_kwh"] = df["power_kw"].round(3)

    # 6. Block ID sanity check
    unique_blocks = df["block_id"].dropna().unique().tolist()
    known_blocks = list(Config.HOSTEL_BLOCKS.keys())
    unknown_blocks = [b for b in unique_blocks if b not in known_blocks]
    if unknown_blocks:
        warnings.append(f"Data includes blocks not in standard campus roster: {unknown_blocks}. Standard blocks are: {known_blocks}")

    if errors:
        return {"valid": False, "errors": errors, "warnings": warnings, "df": None}

    # Format timestamp string cleanly
    df["timestamp"] = df["parsed_timestamp"].dt.strftime("%Y-%m-%d %H:%M:%S")

    # Add occupancy rate based on block capacity
    def get_occ_rate(row):
        blk = row["block_id"]
        cap = Config.HOSTEL_BLOCKS.get(blk, {}).get("capacity", 200)
        return round(min(1.0, float(row["occupancy"]) / cap), 3)

    df["occupancy_rate"] = df.apply(get_occ_rate, axis=1)

    summary = {
        "total_rows": len(df),
        "unique_blocks": unique_blocks,
        "date_min": str(df["timestamp"].min()),
        "date_max": str(df["timestamp"].max()),
        "avg_power_kw": round(float(df["power_kw"].mean()), 2),
        "max_power_kw": round(float(df["power_kw"].max()), 2),
        "avg_occupancy": round(float(df["occupancy"].mean()), 1)
    }

    return {
        "valid": True,
        "errors": [],
        "warnings": warnings,
        "df": df,
        "summary": summary
    }

def engineer_features(df):
    """
    Transforms raw telemetry into ML feature vectors including cyclic time encodings,
    occupancy ratios, and thermal interaction features.
    """
    df = df.copy()
    if "parsed_timestamp" not in df.columns:
        df["parsed_timestamp"] = pd.to_datetime(df["timestamp"])

    # Temporal features
    df["hour"] = df["parsed_timestamp"].dt.hour
    df["dayofweek"] = df["parsed_timestamp"].dt.dayofweek
    df["is_weekend"] = df["dayofweek"].isin([5, 6]).astype(int)

    # Cyclic hour transformation (captures 23:00 -> 00:00 smooth continuity)
    df["sin_hour"] = np.sin(2 * np.pi * df["hour"] / 24.0)
    df["cos_hour"] = np.cos(2 * np.pi * df["hour"] / 24.0)

    # Cyclic day of week
    df["sin_dow"] = np.sin(2 * np.pi * df["dayofweek"] / 7.0)
    df["cos_dow"] = np.cos(2 * np.pi * df["dayofweek"] / 7.0)

    # Thermal cooling demand factor (base 24°C)
    df["cooling_degree_factor"] = np.maximum(0.0, df["temperature"] - 24.0)

    # Interaction feature: Cooling demand * Occupancy
    df["thermal_occupancy_load"] = df["cooling_degree_factor"] * (df["occupancy"] / 100.0)

    # Day type flags
    df["is_exam_day"] = (df["day_type"] == "Exam_Day").astype(int)
    df["is_weekday"] = (df["day_type"] == "Weekday").astype(int)

    # Block one-hot encoding
    for block in Config.HOSTEL_BLOCKS.keys():
        df[f"block_{block}"] = (df["block_id"] == block).astype(int)

    return df

def save_validated_df_to_db(df, source="csv_upload"):
    """Inserts a validated DataFrame into SQLite readings table."""
    conn = get_db_connection()
    cursor = conn.cursor()

    records = []
    for _, row in df.iterrows():
        records.append((
            row["timestamp"],
            row["block_id"],
            int(row.get("floor", 1)),
            float(row["power_kw"]),
            float(row.get("energy_kwh", row["power_kw"])),
            int(row["occupancy"]),
            float(row.get("occupancy_rate", 0.5)),
            float(row["temperature"]),
            float(row.get("humidity", 60.0)),
            str(row.get("day_type", "Weekday")),
            int(row.get("is_synthetic", 0)),
            source
        ))

    cursor.executemany("""
        INSERT INTO readings (
            timestamp, block_id, floor, power_kw, energy_kwh,
            occupancy, occupancy_rate, temperature, humidity,
            day_type, is_synthetic, source
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, records)

    conn.commit()
    conn.close()
    return len(records)

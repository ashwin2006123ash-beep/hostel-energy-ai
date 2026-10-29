import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

class Config:
    BASE_DIR = BASE_DIR
    SECRET_KEY = os.environ.get("SECRET_KEY", "hostel-energy-ai-secret-key-2026")
    DATABASE_PATH = os.path.join(BASE_DIR, "hostel_energy.db")
    SAMPLE_DATA_PATH = os.path.join(BASE_DIR, "data", "sample_telemetry.csv")
    UPLOAD_FOLDER = os.path.join(BASE_DIR, "data", "uploads")
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB max upload

    # Tariff Configuration (Institutional rate in INR)
    # Tier 1 (up to 3000 kWh/month): ₹7.50 / kWh
    # Tier 2 (> 3000 kWh/month): ₹9.20 / kWh
    # Fixed demand charge: ₹120 per kW sanctioned load per month
    TARIFF_TIER_1_LIMIT_KWH = 3000.0
    TARIFF_TIER_1_RATE = 7.50
    TARIFF_TIER_2_RATE = 9.20
    FIXED_DEMAND_CHARGE_PER_KW = 120.0
    SANCTIONED_LOAD_KW = 120.0  # Combined campus hostel sanctioned demand

    # Carbon Footprint: Central Electricity Authority (CEA) India grid factor (kg CO2e per kWh)
    GRID_EMISSION_FACTOR_KG_CO2_PER_KWH = 0.82

    # Hostel Blocks Metadata
    HOSTEL_BLOCKS = {
        "Block-A": {
            "name": "Aryabhatta Hall",
            "type": "Boys Hostel",
            "floors": 3,
            "rooms": 60,
            "capacity": 180,
            "floor_area_sqm": 2400,
            "sanctioned_load_kw": 30.0,
            "base_occupancy_ratio": 0.85
        },
        "Block-B": {
            "name": "Bhaskara Hall",
            "type": "Boys Hostel",
            "floors": 3,
            "rooms": 60,
            "capacity": 180,
            "floor_area_sqm": 2400,
            "sanctioned_load_kw": 30.0,
            "base_occupancy_ratio": 0.80
        },
        "Block-C": {
            "name": "Gargi Hall",
            "type": "Girls Hostel",
            "floors": 4,
            "rooms": 80,
            "capacity": 240,
            "floor_area_sqm": 3200,
            "sanctioned_load_kw": 35.0,
            "base_occupancy_ratio": 0.90
        },
        "Block-D": {
            "name": "Maitreyi Hall",
            "type": "Girls Hostel",
            "floors": 4,
            "rooms": 80,
            "capacity": 240,
            "floor_area_sqm": 3200,
            "sanctioned_load_kw": 35.0,
            "base_occupancy_ratio": 0.88
        }
    }

    # Model & Anomaly Hyperparameters
    ANOMALY_CONTAMINATION = 0.04
    RESIDUAL_ZSCORE_THRESHOLD = 2.2
    RANDOM_SEED = 42

    # Transparency Disclaimers
    DISCLAIMER_TEXT = (
        "AI predictions, appliance fingerprinting, and anomaly rankings are probabilistic estimations "
        "derived from context-aware telemetry to support energy auditing. Anomalies signify statistical "
        "deviations from baseline patterns and do not serve as definitive proof of unauthorized appliance "
        "usage, theft, or electrical faults without physical on-site inspection."
    )

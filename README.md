# Hostel Energy AI — AI-Powered Hostel Electricity Anomaly Detection (PS 3.1)

A complete, production-grade AI platform for university campus hostel electricity monitoring, context-aware anomaly detection, digital twin visualization, root-cause diagnostics, and energy optimization.

---

## 🌟 Key Features

1. **Context-Aware Electricity Anomaly Detection**
   - Evaluates active power telemetry against expected baselines conditioned on **occupancy, timestamp (hour, day of week), ambient temperature, and day type** (Weekday, Weekend, Exam Period).
   - Dual-engine machine learning: **Gradient Boosting Regressor** for expected baseline modeling and **Isolation Forest** with residual z-score thresholding for multi-dimensional anomaly detection.
2. **Expected vs Actual Electricity Consumption Prediction**
   - R² > 0.97 regression model that predicts expected consumption across all campus hostel blocks, providing clear delta metrics ($\Delta \text{ kW} = \text{Actual} - \text{Expected}$).
3. **AI Energy Detective (Explainable Root-Cause Reasoning)**
   - Automatically investigates anomalies, aggregates contextual evidence, and ranks probable diagnostic hypotheses with calibrated confidence percentages.
   - Distinct classification of vacant dorm waste, midnight heating spikes, weather thermal surges, morning geyser congestion, and circuit baseline leakage.
4. **What-If Energy Simulator**
   - Interactive policy simulator with real-time range sliders for:
     - Vacant room automated cutoff compliance %
     - Corridor & room LED retrofit %
     - ESP32 smart fan adaptive regulation %
     - Night curfew common area shutdown toggle
     - Scheduled geyser timer operation toggle
     - Rooftop solar PV capacity (kWp)
   - Real-time calculations of monthly kWh savings, two-tier institutional electricity bill savings (₹), carbon abatement ($\text{kg CO}_2\text{e}$ and Tonnes/yr), implementation Capex (₹), and payback period (months).
5. **Virtual Appliance Fingerprinting**
   - Algorithmic disaggregation decomposing aggregate power into: **Base Standby Load, Cooling & Fans, Lighting, Plug Loads & Electronics, and High-Wattage Thermal Spikes**.
   - **Explicitly labeled** as an algorithmic heuristic estimate to uphold physical transparency.
6. **Electrical Fault Early Warning Engine**
   - Detects persistent electrical abnormalities (e.g., **Baseload Creep** at 03:00 AM over 3+ consecutive days, or excessive low-occupancy volatility) indicative of equipment degradation, ground leakage, stuck pump contactors, or insulation breakdown.
7. **Verified Savings Engine (M&V IPMVP Option C)**
   - Evaluates pre-intervention vs post-intervention metered telemetry normalized by weather (cooling degree hours) and student occupancy headcount to provide certified measurement and verification.
8. **Fair Energy Efficiency League**
   - Solves building size bias by normalizing telemetry across hostel blocks using:
     - **Specific Energy Consumption (SEC):** $\text{kWh per student occupant-day}$
     - **Energy Use Intensity (EUI):** $\text{kWh per m}^2\text{ per month}$
     - **Off-Hours Night Waste Ratio (%):** 01:00 to 05:00 AM consumption
   - Fair Star Ratings (★★★★★) and Green Badges for healthy campus competition.
9. **Interactive Energy Digital Twin**
   - Spatial visualizer showing all 4 campus hostel blocks (Aryabhatta, Bhaskara, Gargi, Maitreyi).
   - Floor-by-floor heatmaps, power density ($\text{W/m}^2$), occupancy density, and zone breakdowns (Dorm Rooms, Study Lounge, Corridor/Geyser lines).
10. **Financial & Carbon Analytics Dashboard**
    - Live metrics, Chart.js time-series charts with clickable anomaly excursions, two-tier institutional tariff calculations, and Central Electricity Authority (CEA) grid carbon factors.
11. **Virtual ESP32 Fan Control Hub**
    - Safe simulation environment for edge IoT fan speed regulation and occupancy-driven eco-throttling.
    - **100% software sandbox:** Zero physical GPIO switching or high-voltage risk. Animated fan telemetry, PWM duty-cycle control, and audit event logs.
12. **Robust CSV Ingestion & Validation**
    - Automated header checking, datetime parsing, physical range bounds, duplicate detection, live preview, and one-click database ingestion with immediate AI anomaly scoring.

---

## 🏗️ System Architecture & File Structure

```
hostel-energy-ai/
├── app.py                         # Flask application factory and server entrypoint
├── config.py                      # Campus block metadata, tariffs, CEA grid emission factor
├── database.py                    # SQLite schema initialization and connection manager
├── seed_all.py                    # Comprehensive database seeder & ML model trainer
├── requirements.txt               # Dependencies
├── README.md                      # Documentation
├── data/
│   ├── sample_telemetry.csv       # 30-day realistic synthetic dataset (2,880 records)
│   └── test_upload_valid.csv      # Sample upload CSV for validation testing
├── models/
│   ├── __init__.py
│   ├── consumption_predictor.py   # Baseline Gradient Boosting Regressor (R² = 0.97)
│   ├── anomaly_detector.py        # Context-aware anomaly detector (Residuals + IsolationForest)
│   └── appliance_fingerprinter.py # Virtual Appliance Fingerprinting decomposition
├── services/
│   ├── __init__.py
│   ├── data_processor.py          # Strict CSV validation and cyclic feature engineering
│   ├── dataset_generator.py       # High-realism synthetic telemetry generator
│   ├── energy_detective.py        # Multi-factor evidence evaluator & cause ranker
│   ├── simulator.py               # What-If energy scenario modeling engine
│   ├── fault_detector.py          # Persistent electrical fault early warning scanner
│   ├── savings_engine.py          # IPMVP Option C verified savings engine
│   ├── league_service.py          # Fair efficiency league normalizer
│   └── esp32_simulator.py         # Virtual ESP32 edge fan controller simulation
├── routes/
│   ├── __init__.py
│   ├── views.py                   # Frontend HTML view routes
│   └── api.py                     # Complete JSON REST API endpoints
├── static/
│   ├── css/
│   │   └── style.css              # Modern glassmorphism UI styles, dark mode, animations
│   └── js/
│       ├── main.js                # Core JS, modal manager, anomaly status updater
│       ├── dashboard.js           # Live KPI feeds, Chart.js line and donut charts
│       ├── digital_twin.js        # Spatial floor heatmap visualizer
│       ├── detective.js           # Anomaly filtering and diagnostic dossier viewer
│       ├── simulator.js           # Range slider bindings and ECM comparison chart
│       ├── league.js              # League table, star ratings, and SEC bar chart
│       └── esp32.js               # Virtual fan controller & simulation logger
├── templates/
│   ├── base.html                  # Global layout, navbar, transparency notices, modals
│   ├── dashboard.html             # Overview dashboard
│   ├── digital_twin.html          # Interactive digital twin
│   ├── detective.html             # AI detective and anomaly investigation
│   ├── simulator.html             # What-if scenario simulator
│   ├── league.html                # Fair efficiency league
│   ├── esp32.html                 # ESP32 fan control simulation
│   └── upload.html                # CSV upload & preview interface
└── tests/
    ├── __init__.py
    ├── test_anomaly_detection.py  # Anomaly detector and baseline regression tests
    ├── test_cost_carbon.py        # Tiered billing, carbon, simulator, and league tests
    └── test_csv_validation.py     # CSV schema and boundary validation tests
```

---

## 🚀 Quickstart & Installation

### 1. Prerequisites
- Python 3.10+ (Tested on Python 3.13)
- SQLite3

### 2. Install Dependencies
```bash
python -m pip install -r requirements.txt
```

### 3. Initialize Database & Train Models
```bash
python seed_all.py
```
*This generates 30 days of realistic telemetry across all 4 hostel blocks, trains the context-aware baseline models, seeds detected anomalies and electrical faults, and populates the SQLite database.*

### 4. Run the Application
```bash
python app.py
```
The application will launch on:
👉 **http://localhost:5000**

---

## 🧪 Running Automated Tests

Run the complete test suite with `pytest`:
```bash
python -m pytest tests/ -v
```
All 12 unit and integration tests validate:
- Baseline regression modeling and prediction boundaries
- Context-aware anomaly scoring and severity thresholds
- AI Energy Detective evidence hypothesis formulation
- Two-tier institutional electricity billing calculations
- CEA carbon emission factor calculations
- What-If simulator savings and payback logic
- Fair league normalization (SEC & EUI)
- Strict CSV schema and physical range validation

---

## 🛡️ Ethical AI & Transparency Commitments

In accordance with responsible AI standards:
1. **No Accusations of Theft or Misconduct:** Anomaly detections and AI detective explanations represent statistical hypotheses to assist energy audits. They do not claim or prove electricity theft, unauthorized appliances, or faulty wiring without physical on-site verification.
2. **Clear Boundary Distinctions:** The interface clearly distinguishes between **Measured Telemetry**, **Predicted Baseline Values**, and **Simulated Projections**.
3. **Appliance Fingerprinting Transparency:** Sub-circuit disaggregation is prominently labeled as an **Algorithmic Heuristic Estimate**.
4. **Hardware Safety:** The ESP32 fan control interface operates exclusively in a simulated software sandbox with zero physical switching.

---

## 📊 Hostel Blocks Metadata

| Block ID | Block Name | Hostel Type | Floors | Rooms | Student Capacity | Usable Area | Sanctioned Load |
| :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: |
| **Block-A** | Aryabhatta Hall | Boys Hostel | 3 | 60 | 180 | 2,400 m² | 30.0 kW |
| **Block-B** | Bhaskara Hall | Boys Hostel | 3 | 60 | 180 | 2,400 m² | 30.0 kW |
| **Block-C** | Gargi Hall | Girls Hostel | 4 | 80 | 240 | 3,200 m² | 35.0 kW |
| **Block-D** | Maitreyi Hall | Girls Hostel | 4 | 80 | 240 | 3,200 m² | 35.0 kW |

---

## 🔌 API Endpoints Summary

| Endpoint | Method | Description |
| :--- | :---: | :--- |
| `/api/dashboard/stats` | `GET` | Campus KPIs, current kW, 30-day kWh, bill (₹), carbon, active anomaly counts |
| `/api/readings/history` | `GET` | Historical telemetry time-series (actual kW, expected kW, occupancy, anomalies) |
| `/api/anomalies` | `GET` | Filtered list of detected anomalies (severity, block, status, pagination) |
| `/api/anomalies/<id>/diagnostic` | `GET` | Deep-dive diagnostic evidence report from AI Detective |
| `/api/anomalies/<id>/status` | `POST` | Update audit status (`Investigating`, `Resolved`, `False_Positive`) |
| `/api/fingerprinting` | `GET` | Estimated virtual appliance disaggregation percentages |
| `/api/faults` | `GET` | Active electrical fault early warnings (e.g. baseload creep) |
| `/api/simulate` | `POST` | What-If scenario execution (cutoffs, LEDs, fans, solar PV, geysers) |
| `/api/savings` | `GET` | IPMVP Option C verified savings interventions |
| `/api/league` | `GET` | Normalized efficiency league standings and star ratings |
| `/api/digital-twin/status` | `GET` | Live block and floor-level spatial heatmaps and power densities |
| `/api/esp32/devices` | `GET` | Virtual ESP32 device nodes and live simulated telemetry |
| `/api/esp32/command` | `POST` | Dispatch simulated PWM/mode command to virtual ESP32 node |
| `/api/esp32/logs` | `GET` | Recent edge simulation activity logs |
| `/api/upload` | `POST` | CSV file upload with preview and database ingest |
| `/api/reset-data` | `POST` | Reset database and re-train baseline ML models |

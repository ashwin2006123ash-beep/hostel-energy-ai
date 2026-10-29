# Hostel Energy AI — Implementation & Architecture Plan (PS 3.1)

**System:** Hostel Energy AI — AI-Powered Hostel Electricity Anomaly Detection and Investigation System  
**Version:** Phase 1 Architecture & Implementation Roadmap  
**Date:** October 29, 2026  
**Document Status:** Complete (Phase 1 Deliverable)  

---

## 1. Executive Inspection & Current State Audit

### 1.1 Existing Repository Audit
An inspection of the workspace (`c:\Users\ashwi\OneDrive\Desktop\hostel-energy-ai`) reveals a functional, modular codebase:
- **Application Core:** `app.py` using Flask factory pattern, registering `views_bp` and `api_bp`.
- **Database (`hostel_energy.db`):** SQLite database containing 6 tables:
  - `readings` (2,880 rows, hourly telemetry for 4 campus blocks)
  - `anomalies` (343 detected events with residual and isolation scores)
  - `fault_warnings` (2 persistent baseload creep warnings)
  - `savings_actions` (3 verified IPMVP Option C intervention case studies)
  - `esp32_devices` (6 simulated IoT fan nodes)
  - `esp32_logs` (15 simulation command execution logs)
- **Machine Learning Core:**
  - `models/consumption_predictor.py`: Gradient Boosting Regressor predicting expected load based on cyclic time and context ($R^2 = 0.971$, $MAE = 0.702\text{ kW}$).
  - `models/anomaly_detector.py`: Dual-engine detector combining baseline prediction residuals with an `IsolationForest` decision function.
  - `models/appliance_fingerprinter.py`: Virtual appliance decomposition engine with explicit heuristic disclaimer.
- **Intelligence & Domain Services:**
  - `services/energy_detective.py`: Multi-factor evidence ranker.
  - `services/simulator.py`: What-If policy scenario engine.
  - `services/fault_detector.py`: Baseload creep early warning scanner.
  - `services/savings_engine.py`: IPMVP Option C M&V engine.
  - `services/league_service.py`: Fair efficiency normalizer (SEC in kWh/occupant-day, EUI in kWh/m²).
  - `services/esp32_simulator.py`: Virtual fan node simulation with affinity-law power calculation.
- **Frontend & Visuals:** Modern dark glassmorphic UI across 7 Jinja2 templates (`dashboard`, `digital_twin`, `detective`, `simulator`, `league`, `esp32`, `upload`) styled with `static/css/style.css` and Chart.js.
- **Automated Tests:** 12 unit tests passing in `tests/` (`test_anomaly_detection.py`, `test_cost_carbon.py`, `test_csv_validation.py`).

### 1.2 Python Environment Audit
- **Python Version:** 3.13.14 (Windows amd64).
- **Core Packages Installed:** `Flask==3.1.3`, `pandas==3.0.3`, `numpy==2.5.1`, `scikit-learn==1.9.1`, `scipy==1.18.0`, `pytest==9.1.1`.
- **Environment Health:** All dependencies are verified, operational, and import without conflicts.

### 1.3 LEAD1.0 Dataset Audit
Empirical inspection of the LEAD1.0 dataset (`https://github.com/samy101/lead-dataset`, archive: `lead1.0-small.zip`) confirmed:
- **File:** `lead1.0-small.csv` (1,749,494 rows, 200 buildings, 8,784 hourly intervals for 2016).
- **Available Columns:** `building_id`, `timestamp`, `meter_reading` (kWh), `anomaly` (0 vs 1).
- **Data Quality:** 107,653 missing meter readings (6.15%), 0 duplicates, 2.13% anomaly prevalence (37,296 anomalies).
- **Domain Gap:** Student occupancy headcounts, room counts, hostel block IDs, and ambient temperature are **absent**.
- **Architectural Policy:** In accordance with the prompt's instructions, we strictly uphold a **zero-fabrication policy**: we never invent occupancy or weather and append them to real LEAD1.0 records. Instead, a clean dual-track strategy separates real LEAD1.0 benchmark data from contextual synthetic hostel simulations.

---

## 2. Gap Analysis & Architecture Evolution

To address the complete PS 3.1 requirements, the existing system will be extended with the following core modules:

```
┌───────────────────────────────────────────────────────────────────────────────────┐
│                           Hostel Energy AI Architecture                           │
├───────────────────────────────────────────────────────────────────────────────────┤
│                                  PRESENTATION                                     │
│  [Overview] [Block/Rooms] [Telemetry] [Queue] [Thresholds] [Actions] [Memory]   │
│  [Savings M&V] [Device Health] [Sim Controls] [Model Eval] [Export Reports]       │
├───────────────────────────────────────────────────────────────────────────────────┤
│                             INTELLIGENCE & ENGINES                                │
│  • Dynamic Threshold Service (Baseline + Uncertainty + Hysteresis + Occupancy)     │
│  • Investigation Prioritization Engine (Excess Cost, Persistence, Context)        │
│  • Incident Memory: "Learn Once, Act Smart" (Pattern Matcher & Case Memory)       │
│  • Supervised LEAD1.0 Benchmark Evaluator (Held-Out Test Set F1 / PR-AUC)         │
│  • Deterministic Scenario Player (10 Repeatable Operational Conditions)           │
│  • Verified Savings Engine (IPMVP Option C Normalized Comparison)                 │
├───────────────────────────────────────────────────────────────────────────────────┤
│                         HARDWARE ABSTRACTION LAYER (HAL)                          │
│  • Unified Telemetry Schema Validator (device_id, room_id, motion, V, I, P, kWh)  │
│  • Ingestion Router: 'simulation' vs 'hardware' Source Separation                 │
│  • Sensor Health Monitor: Online / Offline / Stale Data Detector                  │
│  • Safe Action Controller: Allowlist, Approval Gate, Timeout, Rollback            │
├───────────────────────────────────────────────────────────────────────────────────┤
│                                DATA STORAGE                                       │
│  SQLite: readings | anomalies | incident_memory | threshold_configs | devices     │
│          telemetry_logs | savings_actions | fault_warnings | lead_benchmark      │
└───────────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Detailed Component Architecture

### 3.1 Hardware Abstraction Layer (HAL) & Unified Telemetry Schema
To ensure the application is **software-first and hardware-ready**, we define an explicit telemetry protocol accepted by `POST /api/telemetry`:

```json
{
  "device_id": "ESP32-BLK-A-R101",
  "hostel_block": "Block-A",
  "room_id": "Room-101",
  "timestamp": "2026-10-29 12:30:00",
  "motion_detected": true,
  "occupancy_state": "occupied",
  "voltage_v": 231.4,
  "current_a": 2.85,
  "power_w": 659.5,
  "energy_kwh": 0.66,
  "sensor_status": "ONLINE",
  "data_source": "simulation"
}
```

- **Validation Rules:**
  - `voltage_v`: Expected range 180V–260V AC (flag anomalies if out of range).
  - `current_a`: Non-negative ($\ge 0\text{ A}$), safety cutoff alert if $> 16\text{ A}$ for 1-phase room circuits.
  - `occupancy_state`: Explicit enumeration: `occupied`, `likely_vacant`, `unknown`.
  - `data_source`: Strictly segregated as `"simulation"` or `"hardware"`.
  - **Stale Data Detector:** If `current_time - last_seen > 15 minutes`, device transitions to `STALE`; if $> 60\text{ minutes}$, `OFFLINE`.

### 3.2 Occupancy-Aware Dynamic Thresholds
The dynamic threshold service establishes expected energy and an allowance envelope:

$$\text{Threshold}_{\text{upper}} = \text{Expected Power} + (\text{Normal Variation Allowance} \times \alpha) + \text{Measurement Uncertainty}$$

- **State-Dependent Rules:**
  1. **`occupied` State:** Threshold provides a generous comfort allowance (+45% above expected baseline) for personal laptops, fans, and study lighting.
  2. **`likely_vacant` State:** Occurs after configurable no-motion interval (default: 30 minutes). Threshold tightens to base standby level (+1.2 kW max for whole floor, or 80W per room).
  3. **`unknown` State:** PIR non-detection does **not** prove vacancy (e.g. students sleeping or reading quietly). Threshold defaults to a conservative middle band; aggressive automated control actions are strictly prohibited in the `unknown` state.
- **Hysteresis & Minimum Duration:**
  - An excursion must persist for at least `min_duration_mins` (default: 15 minutes) before generating an anomaly record.
  - A 10% hysteresis buffer prevents noisy alert flapping near boundary limits.

### 3.3 Anomaly Detection & Cautious Investigation Queue
- **Transparent Investigation Prioritization:**
  Incidents are ranked in the audit queue by priority score ($0–100$):
  $$\text{Priority} = 0.35 \times \text{Excess Cost (INR)} + 0.25 \times \text{Residual Deviation} + 0.20 \times \text{Persistence (hours)} + 0.20 \times \text{Occupancy Confidence}$$
- **Cautious Evidence-Based Taxonomy:**
  To uphold scientific integrity and prevent false accusations, labels strictly follow evidence:
  - `unusual consumption` (general unexplained residual)
  - `possible unnecessary consumption` (high draw during verified low-occupancy class hours)
  - `high-current safety alert` (circuit draw exceeding sanctioned threshold or rapid thermal surge)
  - `possible recurring incident` (pattern matches prior verified history)
  - `sensor communication failure` (stale telemetry or dropped packets)
  - `professional inspection recommended` (persistent baseload drift indicative of leakage)

### 3.4 Incident Memory: "Learn Once, Act Smart"
- **Memory Store (`incident_memory` table):**
  When staff investigates an anomaly, they record:
  - Incident signature (block, room type, time window, power deviation magnitude, occupancy state)
  - Verified cause (e.g. "Unattended room cooler running during lectures", "Defective thermostat on water heater")
  - Approved corrective action (e.g. "Prefect physical room sweep", "Thermostat replacement")
  - Resolution outcome and measured post-action improvement (%)
- **Pattern Matching Engine:**
  When a new incident occurs, the engine computes feature similarity against resolved memory items. If similarity $> 0.82$:
  - Displays: *"Matching Incident Found: Similar pattern resolved in Block-A Room 204 on Oct 15 (Action: Verified room shutoff). Recommend same action?"*
  - Provides one-click human approval or dismissal.

### 3.5 Deterministic Simulation Scenarios
To enable thorough testing and evaluation without physical hardware, the simulator will provide 10 deterministic scenarios:
1. `SCEN_NORMAL_OCCUPIED`: Daytime active study with normal laptop/fan loads.
2. `SCEN_VACANT_LOW`: Vacant room during class hours with low standby draw.
3. `SCEN_VACANT_PERSISTENT_HIGH`: Vacant room during class hours with unattended heavy loads running.
4. `SCEN_OCCUPIED_NORMAL_NIGHT`: Night sleep hours with standard ceiling fans and low lighting.
5. `SCEN_SUDDEN_SPIKE`: Sudden 15 kW surge during off-peak hours.
6. `SCEN_REPEATED_INCIDENT`: Replay of a previously logged and resolved incident to demonstrate Incident Memory matching.
7. `SCEN_UNKNOWN_OCCUPANCY`: Sensor reports no motion, but student is asleep; tests threshold conservatism.
8. `SCEN_SENSOR_OFFLINE`: Node stops sending heartbeat; tests timeout and offline flagging.
9. `SCEN_STALE_MISSING_DATA`: Intermittent packet drops and NaN readings; tests data validation.
10. `SCEN_SAFETY_ALERT`: Current draw exceeds 16A; triggers immediate high-priority safety inspection alert.

### 3.6 LEAD1.0 Supervised Benchmark Module
- **Sample Extraction:** Extract a representative slice (`data/lead_benchmark_sample.csv`, ~25,000 rows across 4 diverse commercial meters: 107, 111, 141, 1319) from `lead1.0-small.csv`.
- **Chronological Split:**
  - Train: `2016-01-01` to `2016-09-30` (First 9 months, 75%)
  - Test: `2016-10-01` to `2016-12-31` (Final 3 months, 25%)
- **Supervised Classifier:** Train a Random Forest / Logistic Regression classifier on genuine LEAD1.0 features (rolling mean, rolling std, cyclic hour, day of week) against the original binary ground-truth labels.
- **Reporting:** Display real held-out metrics (Precision, Recall, F1-Score, PR-AUC, Confusion Matrix) on the dashboard without data leakage.

### 3.7 Hardware Documentation & Bill of Materials (BOM)
A dedicated technical guide in `docs/hardware_architecture.md` specifying:
- Component specifications: ESP32-WROOM-32, Non-invasive Split-Core Current Transformer (SCT-013-000, 30A/1V), AC Voltage Sensor Module (ZMPT101B) or Isolated Energy IC (PZEM-004T v3.0), Digital PIR Motion Sensor (HC-SR501).
- Wiring diagram, optical isolation, electrical safety, calibration formulas, and estimated pricing in INR (~₹1,850 per room node).

---

## 4. Step-by-Step Phased Implementation Roadmap

```
Phase 1: Inspection & Implementation Plan (Completed)
   │
   ▼
Phase 2: Database Schema Expansion, LEAD1.0 Benchmark Ingestion & App Stabilization
   │      • Add incident_memory, threshold_configs, and telemetry_logs tables
   │      • Extract data/lead_benchmark_sample.csv and verify schema
   │      • Ensure Flask application starts cleanly with all new models
   │
   ▼
Phase 3: Complete Dashboard UI & Live/Simulated Telemetry Feeds
   │      • Build unified navigation across all 11 required views
   │      • Implement Room Monitoring, Device Health, and Hardware Status cards
   │      • Implement Telemetry live feeds with simulation/hardware source tagging
   │
   ▼
Phase 4: Dynamic Thresholds, Anomaly Detection & Investigation Queue
   │      • Implement services/dynamic_thresholds.py (occupancy states, uncertainty, hysteresis)
   │      • Implement investigation prioritization scoring in services/energy_detective.py
   │      • Update UI with dynamic threshold bands and cautious labels
   │
   ▼
Phase 5: Recommendations, Incident Memory ("Learn Once, Act Smart") & Safe Control
   │      • Implement services/incident_memory.py (hash signature, pattern matcher)
   │      • Build investigation resolution modal with outcome tracking
   │      • Build safe simulated response controller with allowlists and approvals
   │
   ▼
Phase 6: Savings Estimation, M&V Verification, Model Evaluation & Export Reports
   │      • Implement chronological LEAD1.0 model benchmark evaluation (F1, PR-AUC)
   │      • Implement CSV and JSON report export endpoints
   │      • Refine IPMVP Option C savings verification with weather/occupancy adjustments
   │
   ▼
Phase 7: Hardware Abstraction Layer & Ingestion API Testing
   │      • Implement POST /api/telemetry with strict validation (V, I, P, kWh, motion)
   │      • Implement sensor online/offline/stale state machine
   │      • Provide automated test suite simulating edge node payloads
   │
   ▼
Phase 8: Comprehensive Verification, Testing & Final Documentation
          • Run complete pytest suite covering all modules
          • Document hardware BOM, connection schematics, and run commands
          • Deliver final verification report
```

---

## 5. Verification Checklist for Phase 1

- [x] Existing codebase inspected and preserved (all 12 `pytest` tests pass).
- [x] Python 3.13 environment audited and verified.
- [x] LEAD1.0 dataset inspected empirically (1,749,494 rows, 200 buildings, 4 columns, 6.15% missing meter readings, 2.13% anomaly rate).
- [x] Dataset inspection report delivered in [docs/dataset_inspection.md](file:///c:/Users/ashwi/OneDrive/Desktop/hostel-energy-ai/docs/dataset_inspection.md).
- [x] Complete implementation plan produced in [docs/implementation_plan.md](file:///c:/Users/ashwi/OneDrive/Desktop/hostel-energy-ai/docs/implementation_plan.md).
- [x] Zero-fabrication policy reaffirmed: synthetic contextual data kept strictly segregated from real LEAD1.0 smart meter telemetry.

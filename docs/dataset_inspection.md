# Phase 1: LEAD1.0 Dataset Inspection and Integration Planning Report

**Project:** Hostel Energy AI — AI-Powered Hostel Electricity Anomaly Detection  
**Problem Statement:** PS 3.1  
**Inspection Date:** October 29, 2026  
**Investigated Repository:** [https://github.com/samy101/lead-dataset](https://github.com/samy101/lead-dataset)  

---

## 1. Executive Summary

This report documents the empirical inspection of the **LEAD1.0 (Large-scale Energy Anomaly Detection)** dataset, identified in Problem Statement PS 3.1 as the primary data source for energy anomaly detection.

Our empirical inspection reveals:
1. **Repository Structure:** The official GitHub repository (`samy101/lead-dataset`) hosts one primary data archive: `data/lead1.0-small.zip` (compressed size: **9.56 MB** / 10,027,589 bytes).
2. **Extracted Data:** The archive contains exactly one file: `lead1.0-small.csv` (uncompressed size: **55.0 MB** / 57,680,722 bytes), containing **1,749,494 records** spanning 200 commercial buildings over the full 2016 calendar year.
3. **Available Schema:** The file contains exactly four columns: `building_id`, `timestamp`, `meter_reading`, and `anomaly`.
4. **Key Finding on Domain Mismatch:** While LEAD1.0 provides high-quality, ground-truth-annotated electricity meter readings, **hostel-specific context—including student occupancy headcounts, room counts, hostel block identifiers, and ambient temperature—is completely absent** from this dataset.
5. **Ethical & Methodological Recommendation:** In strict compliance with the hackathon requirements, **we will never fabricate or impute occupancy, hostel identities, or temperatures into LEAD1.0 and present them as real measurements.** Instead, we propose a clean **Dual-Track System**:
   - **Track A (LEAD1.0 Empirical Benchmark):** Supervised and unsupervised anomaly detection trained and benchmarked against real-world ground-truth labels (`0` vs `1`) from 200 real building meters.
   - **Track B (Hostel Contextual Digital Twin & Simulator):** A clearly labelled, dedicated synthetic hostel dataset (`is_synthetic = 1`) to power occupancy-aware predictions, floor heatmaps, ESP32 fan-control simulations, and intervention planning.

---

## 2. Dataset Overview

The LEAD (Large-scale Energy Anomaly Detection) dataset was introduced by researchers to address the scarcity of publicly available, annotated anomaly benchmarks in building energy management. 

- **Provenance:** LEAD1.0 is derived from an annotated subset of the **ASHRAE - Great Energy Predictor III (GEPIII)** dataset (originally hosted on Kaggle in 2019).
- **Domain:** Non-residential and commercial facilities (primarily education, office, and public assembly buildings from university campuses and municipalities).
- **Meters:** Focuses on electricity sub-meters (`meter == 0` in ASHRAE terminology).
- **Ground Truth Annotation:** Anomaly labels were produced via a hybrid protocol: automated rule-based flags (identifying sustained zero readings, frozen values, and extreme surges) followed by expert visual inspection using an R Shiny interactive annotation tool (`AnomalyAnnotator/app.R`).
- **Anomaly Types:** Covers both *point anomalies* (isolated sudden spikes or single-hour sensor dropouts) and *collective/sequential anomalies* (multi-hour or multi-day unexpected deviations, baseload offsets, and continuous unvarying draws).

---

## 3. Source and Licensing Notes

| Property | Details | Notes / Implications |
| :--- | :--- | :--- |
| **Repository URL** | `https://github.com/samy101/lead-dataset` | Public Git repository |
| **Commit Evaluated** | `pushed_at: 2022-06-28T06:10:06Z` (main branch) | Repository contains code & data |
| **Declared License** | `null` (No root `LICENSE` file found) | GitHub API returns `"license": null` |
| **Origin License (ASHRAE)** | Open Database License (ODbL) / CC BY 4.0 | Academic and research usage permitted |
| **Kaggle Competition** | Energy Anomaly Detection Community Competition | Restricted to competition rules for submissions |
| **Storage & Commit Policy** | **Do not commit raw 55 MB CSV to Git** | Store in local cache or `.gitignore` data folder |

> [!WARNING]
> Because `samy101/lead-dataset` does not contain an explicit root `LICENSE` file, the dataset must be treated under fair-use academic research guidelines derived from the parent ASHRAE GEPIII / Building Data Genome Project 2 license (Creative Commons Attribution 4.0 International). Full attribution must be maintained in all project documentation and UI views.

---

## 4. Actual Available Files and Columns

### 4.1 Repository File Listing
Inspection of the GitHub repository tree via API confirmed the following contents:

```
samy101/lead-dataset/
├── .gitignore
├── README.md                          # Project overview & Kaggle competition link
├── AnomalyAnnotator/                  # R Shiny manual annotation tool
│   ├── AnomalyAnnotator.Rproj
│   ├── README.md
│   ├── anomaly_annotator.png
│   ├── app.R                         # Interactive Shiny UI & server logic
│   ├── combine_anomaly.R             # Aggregation script combining annotations
│   ├── global.R
│   ├── initialize_data.R             # Preprocessing script from ASHRAE GEPIII
│   └── server-observers.R
├── data/
│   ├── .gitignore
│   └── lead1.0-small.zip             # 10,027,589 bytes (Primary data release)
└── notebooks/
    └── README.md
```

### 4.2 Structure of `lead1.0-small.csv`
Extraction of the central directory and header confirmed **exactly four columns**:

| Column Name | Raw Data Type | Pandas Type | Description |
| :--- | :--- | :--- | :--- |
| `building_id` | Integer | `int64` | Anonymized building identifier (range: 1 to 1353) |
| `timestamp` | String | `datetime64[ns]` | Timestamp of reading (`YYYY-MM-DD HH:MM:SS`) |
| `meter_reading` | Numeric / Null | `float64` | Measured electricity consumption (kWh per hour) |
| `anomaly` | Binary Flag | `int64` | Ground-truth anomaly label: `0` = Normal, `1` = Anomaly |

---

## 5. Empirical Data Quality Findings

Our inspection script processed all **1,749,494 rows** of `lead1.0-small.csv`. The empirical findings are detailed below:

### 5.1 Volume and Coverage
- **Total Rows:** `1,749,494`
- **Total Unique Buildings:** `200`
- **Time Coverage:** `2016-01-01 00:00:00` to `2016-12-31 23:00:00` (8,784 unique hourly timestamps across a 366-day leap year).
- **Readings per Building:**
  - Minimum: 7,471 hours
  - Median: 8,783 hours
  - Maximum: 8,784 hours (complete year)
- **Duplicate Records:** **Exactly 0** duplicate rows found for `(building_id, timestamp)`.

### 5.2 Missing Values and Sensor Dropouts
| Column | Missing Count | Percentage | Finding & Impact |
| :--- | :---: | :---: | :--- |
| `building_id` | 0 | 0.00% | Complete |
| `timestamp` | 0 | 0.00% | Complete |
| `meter_reading` | **107,653** | **6.15%** | Null / empty meter readings. Concentrated during meter installation periods or long communication dropouts. |
| `anomaly` | 0 | 0.00% | Complete ground-truth labels for all rows. |

### 5.3 Electricity Consumption Distribution
Statistical distribution of non-null `meter_reading` values (1,641,841 valid observations):

| Statistic | Value (kWh) | Interpretation |
| :--- | :---: | :--- |
| **Mean** | 179.902 kWh | High mean driven by large university facility loads |
| **Standard Deviation** | 395.913 kWh | Significant inter-building variability |
| **Minimum** | 0.000 kWh | Zero readings present during shutdowns/outages |
| **25th Percentile** | 30.000 kWh | Small facility or baseload draw |
| **Median (50th %)** | 84.100 kWh | Robust median consumption level |
| **75th Percentile** | 199.000 kWh | Daytime operational load |
| **Maximum** | 6,596.890 kWh | Extreme facility load or mega-meter |

### 5.4 Ground-Truth Anomaly Class Balance
- **Normal Observations (`anomaly == 0`):** `1,712,198` (**97.87%**)
- **Anomalous Observations (`anomaly == 1`):** `37,296` (**2.13%**)
- **Class Imbalance Ratio:** ~46:1
- **Building Prevalence:** All 200 buildings exhibit at least one annotated anomaly.
  - Building with highest anomaly count: `building_id = 1319` (775 anomalous hours).
  - Top 5 buildings account for 2,913 anomalies (~7.8% of all anomalies).

---

## 6. Comparison: Required Hostel Fields vs Available LEAD1.0 Fields

The table below contrasts the fields required for the **Hostel Energy AI** system (Problem Statement PS 3.1) with what is actually present in LEAD1.0:

| Required Hostel Field | Present in LEAD1.0? | Direct Column | Status & Remediation Strategy |
| :--- | :---: | :---: | :--- |
| **`hostel_block`** | ❌ No | `building_id` (partial) | LEAD1.0 has integer building IDs (1–1353) from commercial/campus buildings, not hostel blocks. **Never rename generic buildings as real hostels.** Map selected building IDs (e.g. 107, 111) as external validation meters. |
| **`date_time`** | ✅ Yes | `timestamp` | Direct 1:1 match. Format is `YYYY-MM-DD HH:MM:SS`. |
| **`energy_kwh`** | ✅ Yes | `meter_reading` | Direct 1:1 match. Hourly active electricity in kWh. Requires handling for 6.15% missing values. |
| **`occupancy`** | ❌ No | *None* | **Completely absent.** Cannot be extracted or derived from LEAD1.0 without fabrication. |
| **`room_count`** | ❌ No | *None* | **Completely absent.** In ASHRAE, building area exists in external metadata, but specific room counts do not. |
| **`day_type`** | ⚠️ Partial | *Derivable* | Day of week (Weekday vs Weekend) can be derived from timestamp. Campus academic calendar (Exam Period, Curfew, Vacation) is **absent**. |
| **`outside_temp_c`**| ❌ No | *None* | **Absent from `lead1.0-small.csv`.** Weather was in a separate ASHRAE file and is not included in this LEAD package. |

> [!IMPORTANT]
> **Ethical Principle: Zero Fabrication Policy**  
> We will **never invent occupancy headcounts or ambient temperatures and label them as real LEAD1.0 meter telemetry.** Doing so would compromise scientific validity and mislead evaluators.

---

## 7. Recommended Preprocessing Pipeline for LEAD1.0

When processing LEAD1.0 for model benchmarking, the following pipeline must be implemented:

```
[Raw LEAD1.0 CSV] (1.75M rows)
       │
       ▼
[Missing Value Handler] ──> Drop or linear-interpolate small gaps (≤ 3 hours)
       │                    Mask multi-day outages (do NOT fill with 0)
       ▼
[Temporal Feature Extractor] ──> sin_hour, cos_hour, day_of_week, is_weekend, month
       │
       ▼
[Rolling Contextual Engine] ──> 24h rolling mean, 24h rolling std, 168h (weekly) lag
       │
       ▼
[Leakage-Free Chronological Split] ──> Train: Jan 1 - Sep 30 (75%)
                                       Test:  Oct 1 - Dec 31 (25%)
```

1. **Handling Missing Values (107,653 rows):**
   - For isolated gaps ($\le 3$ hours), apply forward-fill or linear interpolation.
   - For extended dropouts (e.g., Building 1 missing all of January), do **not** impute zero, as zero power would falsely trigger anomaly or baseload fault algorithms. Filter out unmetered periods during training.
2. **Feature Engineering Without Exogenous Weather/Occupancy:**
   - Because temperature and occupancy are missing in LEAD1.0, baseline models on this dataset must rely on **autoregressive and calendar features**:
     - $\sin(2\pi \cdot \text{hour} / 24)$ and $\cos(2\pi \cdot \text{hour} / 24)$
     - Day of week (0–6), Weekend indicator (0/1)
     - Rolling 24-hour mean consumption $\mu_{24}$ and standard deviation $\sigma_{24}$
     - 7-day seasonal lag ($t - 168\text{h}$) to capture building weekly diurnal rhythm
3. **Outlier Scaling:**
   - Apply `RobustScaler` (interquartile range) on `meter_reading` per building to handle extreme variations across meters without distortion from historical anomaly spikes.

---

## 8. Proposed Training & Evaluation Strategy

### 8.1 Preventing Data Leakage
To prevent data leakage in time-series anomaly detection:
1. **Chronological Splitting (Within-Building Benchmark):**
   - **Training Set:** `2016-01-01 00:00:00` to `2016-09-30 23:00:00` (First 9 months, ~75% of data).
   - **Validation/Test Set:** `2016-10-01 00:00:00` to `2016-12-31 23:00:00` (Final 3 months, ~25% of data).
   - *Rationale:* Evaluates model ability to detect future unseen anomalies without lookahead bias.
2. **Cross-Building Generalization Split:**
   - **Training Buildings:** 150 buildings.
   - **Unseen Test Buildings:** 50 buildings.
   - *Rationale:* Tests whether anomaly signatures learned on one set of meters transfer to unseen building circuits.

### 8.2 Evaluation Metrics
Given the severe **2.13% class imbalance**, standard classification accuracy (which would yield 97.8% by predicting all zeros) is completely invalid. Evaluation must report:
- **Precision:** $\frac{TP}{TP + FP}$ (Minimizing false alarms that cause audit fatigue).
- **Recall:** $\frac{TP}{TP + FN}$ (Catching actual high-loss anomalies).
- **F1-Score / Macro-F1:** Harmonic mean of precision and recall.
- **PR-AUC (Precision-Recall Area Under Curve):** Benchmark metric across classification thresholds.

---

## 9. Integration Plan for Hostel Energy AI

To satisfy Problem Statement PS 3.1 while maintaining scientific integrity, we propose the following **Dual-Dataset Integration Architecture**:

```
┌────────────────────────────────────────────────────────────────────────┐
│                        Hostel Energy AI Platform                       │
├────────────────────────────────────┬───────────────────────────────────┤
│ Track A: LEAD1.0 Benchmark Module  │ Track B: Hostel Digital Twin      │
├────────────────────────────────────┼───────────────────────────────────┤
│ • Real-world smart meter data      │ • Dedicated synthetic dataset     │
│ • 200 commercial buildings         │ • 4 campus blocks (A, B, C, D)    │
│ • Ground-truth labels (0 vs 1)     │ • Occupancy, Room Count, Temp     │
│ • Benchmarks supervised detectors  │ • Powers Digital Twin Heatmaps    │
│ • Verifies ML F1 & PR-AUC scores   │ • Powers What-If Policy Sim       │
│ • Ingested via /api/upload         │ • Powers ESP32 Fan Control Hub    │
└────────────────────────────────────┴───────────────────────────────────┘
```

### 9.1 How LEAD1.0 Enhances the Application
1. **Model Validation Benchmark:** LEAD1.0 provides an external, real-world benchmark to evaluate our `ContextAwareAnomalyDetector` and supervised models against human-annotated ground truth.
2. **Pre-packaged Sample Upload:** We will extract a verified slice of LEAD1.0 (e.g. `lead1.0_building_107_sample.csv` with known anomalies) for the UI's **CSV Upload & Ingestion Center**, allowing judges and users to test real dataset performance with one click.
3. **Database Separation:** In SQLite, readings from LEAD1.0 will be stored with `source = 'lead_dataset'` and `is_synthetic = 0`, keeping them isolated from hostel telemetry (`source = 'synthetic_generator'`, `is_synthetic = 1`).

---

## 10. Summary of Findings & Issues Requiring User Approval

### Key Findings Summary
1. LEAD1.0 is a 1.75M-row electricity dataset from 200 commercial/campus buildings with ground-truth binary labels.
2. The dataset has **only 4 columns**: `building_id`, `timestamp`, `meter_reading`, and `anomaly`.
3. Required hostel context (**occupancy, room counts, hostel block IDs, ambient temperature**) is **absent**.
4. The file `lead1.0-small.zip` is 9.56 MB and has been downloaded only to a temporary scratch folder for non-destructive inspection.

### Decisions Requiring User Approval for Phase 2
1. **Dual-Dataset Architecture Approval:** Do you approve keeping Track A (LEAD1.0 empirical benchmark on real meter readings) and Track B (clearly labelled synthetic hostel dataset for occupancy-driven Digital Twin and ESP32 simulation) cleanly separated in the application?
2. **Benchmark Subset Extraction:** Do you approve extracting a representative slice of LEAD1.0 (e.g., 2–4 representative buildings with verified anomalies, ~10,000–35,000 rows) into `data/lead_benchmark_sample.csv` for fast local testing and uploading, rather than committing the full 55 MB file?
3. **Supervised vs Unsupervised Model Addition:** Would you like us to add a dedicated supervised classifier (e.g., LightGBM / Random Forest trained on LEAD1.0 ground-truth labels) alongside our existing unsupervised residual detector?

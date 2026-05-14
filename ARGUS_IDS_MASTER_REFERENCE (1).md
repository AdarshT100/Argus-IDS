**Argus-IDS**

**Master Decision Reference**

*Single source of truth for all project decisions*

This document is the single source of truth for all project decisions.

Before adding any feature, changing any architecture decision, or deviating from any plan below — consult this doc first.

If a decision needs to change, update this doc before touching any code.

| Note: Sections marked with ✦ NEW contain additions not in the original document. |
| :---- |

# **1\. Project Identity**

| Field | Decision |
| :---- | :---- |
| Project name | Argus-IDS |
| Full title | Argus-IDS: An Explainable AI-driven Anomaly Detection Framework for IoT Gateway Intrusion Detection in Smart City Networks |
| Repo description | AI-powered intrusion detection for IoT gateways — explainable threat classification, anomaly detection for zero-days, and real-time alerting with a REST API backend. |
| Ownership | Solo implementation |
| Target completion | 4 weeks from start |
| Python version | 3.11 |
| Development OS | macOS |

# **2\. Scope — What Is In and What Is Out**

## **2.1 In Scope (must be built)**

* Folder restructure into clean service-oriented architecture  
    
* SMOTE for class imbalance handling  
    
* PCA as optional preprocessing step with on/off comparison  
    
* Random Forest classifier (existing, refactor)  
    
* XGBoost classifier (new)  
    
* Voting ensemble of RF \+ XGBoost as the final classifier  
    
* Isolation Forest for unsupervised anomaly detection  
    
* SHAP explainability (existing, extend to cover ensemble)  
    
* Decision engine combining ensemble output \+ anomaly score  
    
* Severity levels: LOW, MEDIUM, HIGH, ANOMALY  
    
* FastAPI backend with /predict and /alerts endpoints  
    
* Streamlit frontend calling FastAPI (refactor existing app.py)  
    
* JS alert dashboard embedded in Streamlit via st.components  
    
* Discord webhook alert dispatcher for HIGH and ANOMALY severities  
    
* CICIDS2017 dataset (existing)  
    
* CIC IoT 2023 dataset — selected files only (DDoS, DoS, Reconnaissance CSVs, under 500MB total)  
    
* Full model benchmarking: Decision Tree, SVM, RF, XGBoost, Ensemble+XAI  
    
* Streamlit Cloud deployment (frontend)  
    
* Railway free tier deployment (FastAPI backend)  
    
* Short technical report (system design \+ architecture \+ results \+ charts)  
    
* **GitHub Actions CI pipeline (linting \+ smoke tests)**  
    
* **Calibrated ensemble probabilities via CalibratedClassifierCV (isotonic)**

## **2.2 Out of Scope — Frozen as Future Work**

These will NOT be implemented. They go in the Future Work section of the report only.

* CNN model  
    
* LSTM model  
    
* CNN-LSTM hybrid model  
    
* Federated learning  
    
* Live packet capture (Scapy/pyshark)  
    
* OS-level deployment (eBPF, Netfilter, Windows Filtering Platform)  
    
* Docker / Docker Compose  
    
* Model quantization / edge deployment  
    
* SVM in the ensemble (RF \+ XGBoost only)  
    
* Additional datasets beyond CICIDS2017 and CIC IoT 2023 subset

# **3\. Architecture Decisions**

## **3.1 Folder Structure (final, do not deviate)**

argus-ids/

├── .github/                          \# ✦ NEW

│   └── workflows/

│       └── ci.yml                    \# Linting \+ smoke tests on every push

├── backend/

│   ├── api/

│   │   ├── main.py                   \# FastAPI app entry point

│   │   ├── routes.py                 \# /predict and /alerts endpoints

│   │   └── schemas.py                \# Pydantic request/response models

│   ├── core/

│   │   ├── data.py                   \# Dataset loading and preprocessing

│   │   ├── model.py                  \# Model and feature loader

│   │   ├── simulation.py             \# Packet selection and window simulation

│   │   ├── evaluation.py             \# Benchmarking utilities

│   │   └── decision.py               \# Decision engine (NEW)

│   ├── model/

|     |   ├── ensemble\_model.pkl      \#Calibrated RF+XGBoost ensemble — used for prediction

│   │   ├── rf\_model.pkl

│   │   ├── xgb\_model.pkl

│   │   ├── iso\_forest.pkl

│   │   └── rf\_features.pkl

│   └── services/

│       ├── SHAP\_explainer.py

│       └── alert\_dispatcher.py       \# Discord webhook (NEW)

├── frontend/

│   └── app.py                        \# Streamlit — calls FastAPI only

├── train\_model.py                    \# Trains RF \+ XGBoost ensemble

├── train\_anomaly.py                  \# Trains Isolation Forest on benign traffic only

├── requirements.txt

└── README.md

## **3.2 Detection Pipeline (fixed, do not change)**

Network traffic (PCAP / CSV simulation)

↓

Feature extraction \+ preprocessing

↓

├── Ensemble classifier (RF \+ XGBoost voting)

│   └── SHAP explanation per prediction

└── Isolation Forest (anomaly score)

↓

Decision engine

↓

Severity output: LOW / MEDIUM / HIGH / ANOMALY

↓

FastAPI response \+ alert log \+ Discord webhook (HIGH and ANOMALY only)

## **3.3 Decision Engine Logic (fixed)**

| Condition | Severity |
| :---- | :---- |
| Ensemble: benign, Isolation Forest: normal | LOW |
| Ensemble: benign, Isolation Forest: anomaly | ANOMALY |
| Ensemble: attack, probability \< 0.75 | MEDIUM |
| Ensemble: attack, probability \>= 0.75 | HIGH |

Discord webhook fires only on HIGH and ANOMALY.

## **3.4 Ensemble Strategy (fixed)**

* Soft voting between Random Forest and XGBoost  
    
* Final class \= argmax of averaged predicted probabilities  
    
* No SVM — confirmed excluded

# **4\. API Design (fixed endpoints)**

| Method | Endpoint | Description |
| :---- | :---- | :---- |
| POST | /predict | Accepts packet features as JSON, returns verdict \+ severity \+ SHAP top features |
| GET | /alerts | Returns recent alert log (last 50 entries) |
| GET | /health | Health check — used by Streamlit to check if API is awake |
| GET | /docs | Swagger UI — auto-generated by FastAPI, used in demo |

## **Request body for /predict**

{"features": { "feature\_name": value, ... }}

## **Response from /predict**

{

"prediction":  "ATTACK",

"severity":    "HIGH",

"anomaly\_score": 0.82,

"confidence":  0.94,

"shap\_top\_features": \[

{ "feature": "flow\\\_duration",          "impact": 0.34 },

{ "feature": "fwd\\\_packet\\\_length\\\_mean", "impact": 0.21 }

\],

"timestamp":   "2026-05-12T10:30:00Z"

}

# **5\. Dataset Decisions**

| Dataset | Status | Usage |
| :---- | :---- | :---- |
| CICIDS2017 (Friday DDoS) | Already downloaded | Primary training and benchmarking |
| CIC IoT 2023 | Download selected CSVs only | Secondary validation — DDoS, DoS, Reconnaissance files only (target \< 500MB) |
| IoT-23 | Out of scope | Future work |
| DNP3 Smart Grid | Out of scope | Future work |

## **5.1 Train/Test Split**

* 80/20 stratified split  
    
* SMOTE applied to training set only — never to test set

## **5.2 Preprocessing Steps (fixed order)**

1. Drop non-informative columns (Flow ID, Source IP, Destination IP, Timestamp)  
     
2. Handle missing and infinite values  
     
3. Label encode: BENIGN=0, ATTACK=1  
     
4. Min-max normalization  
     
5. SMOTE on training split  
     
6. Optional PCA (flag-controlled, default off for primary results)

# **6\. Model Decisions**

| Model | Role | Status |
| :---- | :---- | :---- |
| Random Forest | Ensemble member \+ SHAP | Refactor existing |
| XGBoost | Ensemble member | Build new |
| RF \+ XGBoost voting ensemble | Final classifier | Build new |
| Isolation Forest | Anomaly detection | Build new |
| Decision Tree | Baseline comparison only | Benchmark only |
| SVM | Baseline comparison only | Benchmark only |
| Logistic Regression | Baseline comparison only | Benchmark only |
| CNN / LSTM / CNN-LSTM | Future work | Do not implement |

## **6.1 Model Save Locations (fixed)**

All model files save to and load from backend/model/ only. No exceptions.`ensemble_model.pkl` is the only model file loaded at prediction time. `rf_model.pkl` and `xgb_model.pkl` are benchmarking artifacts and are never loaded by the API or decision engine.

## **6.2 Target Accuracy**

* Aim to match or exceed 97.6% for the Proposed Ensemble \+ XAI  
    
* If real measured result is lower, report the real number — do not fabricate  
    
* Minimum acceptable: 95% — below this, revisit preprocessing

## **6.3 Probability Calibration (fixed)  ✦ NEW**

| All ensemble probability outputs must be wrapped in CalibratedClassifierCV before saving to backend/model/. Method: isotonic regression (method='isotonic', cv=5) Reason: Random Forest and XGBoost raw predict\_proba() outputs are not true probabilities — they are scores. Isotonic regression maps these scores to empirically grounded probabilities using cross-validation on the training set. This makes the severity thresholds in section 3.3 scientifically defensible: *a calibrated confidence of 0.75 means the model was empirically correct in \>= 75% of cases at that score level in validation data.* Implementation: from sklearn.calibration import CalibratedClassifierCV calibrated\_ensemble \= CalibratedClassifierCV(ensemble, method='isotonic', cv=5) calibrated\_ensemble.fit(X\_train, y\_train) Save ensemble\_model.pkl — not the raw ensemble. Calibration curve (reliability diagram) must be included in the technical report — plot before and after calibration to demonstrate the improvement. This plot goes in the Results section alongside confusion matrix and ROC curve. |
| :---- |

# **7\. Frontend Decisions**

| Decision | Choice |
| :---- | :---- |
| Primary UI | Streamlit (refactored to call FastAPI only) |
| JS alert dashboard | Embedded in Streamlit via st.components.v1.html |
| Streamlit imports model directly | No — calls FastAPI only |
| SHAP plots | Rendered in Streamlit as before |
| JS dashboard data source | Polls FastAPI /alerts endpoint |

## **7.1 JS Alert Dashboard (embedded) — must show:**

* Live alert feed (last 10 alerts)  
    
* Severity distribution chart (donut or bar)  
    
* Packet rate over time (line chart)  
    
* Threat level gauge (current window severity)

Technology: vanilla HTML \+ Chart.js — no React, no build step.

# **8\. Alerting Decisions**

| Decision | Choice |
| :---- | :---- |
| Alert channel | Discord webhook |
| Trigger conditions | HIGH severity and ANOMALY severity only |
| Alert content | Timestamp, severity, top 3 SHAP features, confidence score, anomaly score |
| Email alerting | Out of scope |
| Slack webhook | Out of scope |

# **9\. Deployment Decisions**

| Layer | Platform | Cost |
| :---- | :---- | :---- |
| Streamlit frontend | Streamlit Cloud | Free |
| FastAPI backend | Railway free tier | Free |
| Model files | Stored in GitHub repo (if \< 100MB) or fetched from Google Drive at startup | Free |
| JS alert dashboard | Embedded in Streamlit — no separate hosting needed | Free |
| Custom domain | Not required | — |
| Docker | Optional polish — implement only after everything else works | — |

## **9.1 Railway Cold Start**

Railway free tier sleeps after inactivity. First request takes \~30 seconds to wake. Mitigation: Streamlit app shows a "Connecting to backend..." spinner and calls /health on load before making any prediction requests.

## **9.2 Model File Size**

Before pushing to GitHub, check rf\_model.pkl size. If over 100MB, use gdown to fetch from Google Drive on app startup. Decision to be confirmed once model is trained.

# **10\. Report Decisions**

| Decision | Choice |
| :---- | :---- |
| Format | Short technical report — no page limit but concise |
| Goal | Reviewer understands the full project without being overwhelmed |
| Structure | System design → architecture decisions → methodology → results → charts → conclusion |
| Results | Real measured numbers — no projected figures |
| Charts to include | Confusion matrix, ROC curve, precision-recall curve, SHAP summary plot, severity distribution, benchmark comparison table, calibration curve / reliability diagram (before and after calibration) |
| Paper alignment | Deviations from the submitted paper are acceptable — report reflects what was actually built |

# **11\. 4-Week Delivery Plan**

| Week | Focus | Deliverables |
| :---- | :---- | :---- |
| Week 1 | Foundation | Folder restructure, SMOTE, PCA, XGBoost, train ensemble, verify accuracy |
| Week 2 | Detection layer | Isolation Forest, decision engine, SHAP extended to ensemble |
| Week 3 | API \+ alerting | FastAPI endpoints, Streamlit refactor, Discord webhook, JS dashboard embedded, GitHub Actions CI workflow (ci.yml) — flake8 linting on backend/, pytest smoke tests covering decision engine severity logic and FastAPI /health endpoint. |
| Week 4 | Data \+ deploy \+ report | CIC IoT 2023 subset, full benchmarks, Streamlit Cloud \+ Railway deploy, write report |

## **11.1 CI Workflow Specification (fixed)  ✦ NEW**

| File location: .github/workflows/ci.yml Trigger: every push and pull request to main Pipeline steps (in order): 1\.  Checkout repo 2\.  Set up Python 3.11 3\.  Install dependencies from requirements.txt 4\.  Run flake8 on backend/ — max line length 100 5\.  Run pytest on tests/ — verbose output Minimum test coverage required in tests/: Decision engine: all four severity conditions from section 3.3 must have a corresponding unit test FastAPI: /health endpoint must return 200 Schema: /predict request body must reject missing features field CI must pass on main at all times. A failed CI run must be fixed before any other feature work continues. README must display the GitHub Actions CI status badge. |
| :---- |

# **12\. Open Decisions (must resolve before acting)**

| \# | Decision | Notes |
| :---- | :---- | :---- |
| 1 | Model file size | Check after Week 1 training — affects deployment strategy |
| 2 | CIC IoT 2023 specific files | Confirm exact CSV filenames to download before Week 4 |

# **13\. Decisions That Will Not Be Revisited**

These are closed. Do not reopen without a strong reason.

* Project name: Argus-IDS — final  
    
* No SVM in ensemble  
    
* No CNN/LSTM — future work only  
    
* No Docker as a requirement  
    
* No live packet capture in this version  
    
* No email alerting — Discord webhook only  
    
* No separate JS frontend hosting — embedded in Streamlit only  
    
* CICIDS2017 as primary dataset — confirmed  
    
* Railway for FastAPI, Streamlit Cloud for frontend — confirmed  
    
* Soft voting ensemble (RF \+ XGBoost) — confirmed  
    
* Python 3.11, macOS development — confirmed


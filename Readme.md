# Argus-IDS

![CI](https://github.com/AdarshT100/Argus-IDS/actions/workflows/ci.yml/badge.svg)

**Argus-IDS: An Explainable AI-driven Anomaly Detection Framework for IoT Gateway
Intrusion Detection in Smart City Networks**

AI-powered intrusion detection for IoT gateways — explainable threat classification,
anomaly detection for zero-days, and real-time alerting with a REST API backend.

## Stack

- **Backend:** FastAPI (Railway)
- **Frontend:** Streamlit (Streamlit Cloud)
- **Models:** RF + XGBoost calibrated ensemble, Isolation Forest
- **Explainability:** SHAP
- **Dataset:** CICIDS2017 (primary), CIC IoT 2023 (secondary)

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Training

```bash
python train_model.py       # RF + XGBoost calibrated ensemble
python train_anomaly.py     # Isolation Forest (benign traffic only)
```

## Running

```bash
# Backend
uvicorn backend.api.main:app --reload

# Frontend (separate terminal)
streamlit run frontend/app.py
```

## Architecture

See `ARGUS_IDS_MASTER_REFERENCE.md` for all design decisions.
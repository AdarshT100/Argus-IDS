# filename: backend/api/main.py
# purpose: FastAPI application entry point
# governed by: §3.1, §4 (API design)

import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.api.routes import router

app = FastAPI(
    title="Argus-IDS",
    description=(
        "Explainable AI-driven Anomaly Detection Framework "
        "for IoT Gateway Intrusion Detection"
    ),
    version="1.0.0",
)

# CORS middleware — allow Streamlit frontend to call API without CORS errors
ALLOWED_ORIGINS = os.getenv("ARGUS_ALLOWED_ORIGINS", "http://localhost:8501").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

app.include_router(router)

# filename: backend/api/main.py
# purpose: FastAPI application entry point


import os
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from backend.api.routes import router

load_dotenv()

app = FastAPI(
    title="Argus-IDS",
    description=(
        "Explainable AI-driven Anomaly Detection Framework "
        "for IoT Gateway Intrusion Detection"
    ),
    version="1.0.0",
)

# CORS middleware - allow the Vite frontend to call API without CORS errors
ALLOWED_ORIGINS = os.getenv("ARGUS_ALLOWED_ORIGINS", "http://localhost:5173").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

app.mount(
    "/model-plots",
    StaticFiles(directory=os.environ.get("ARGUS_MODEL_DIR", "backend/model")),
    name="model-plots",
)

app.include_router(router)

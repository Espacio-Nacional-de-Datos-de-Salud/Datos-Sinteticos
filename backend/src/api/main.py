"""FastAPI application for the Synthetic Data Tool REST API."""

import os
from contextlib import asynccontextmanager

from backend.src.api.routers import (
    admin,
    configs,
    evaluations,
    files,
    health,
    inspections,
    models,
    pipelines,
    simulations,
)
from backend.src.sessions.configs import bootstrap_configs, migrate_real_config_headers
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure all configuration files exist (bootstrapped from .example.yaml templates)
    # This enables a "just run docker compose" experience without requiring 'make setup'.
    bootstrap_configs()
    migrate_real_config_headers()
    yield


app = FastAPI(
    title="API for the ENDS Synthetic Data Generation Tool",
    description="REST API for the ENDS synthetic data generation tool.",
    version="0.1.0",
    lifespan=lifespan,
)

_extra_origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", *_extra_origins],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(files.router)
app.include_router(configs.router)
app.include_router(inspections.router)
app.include_router(models.router)
app.include_router(simulations.router)
app.include_router(evaluations.router)
app.include_router(pipelines.router)
app.include_router(admin.router)

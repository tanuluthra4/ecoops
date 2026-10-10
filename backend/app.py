from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from config import FRONTEND_DIR
from services.incident_service import build_incident
from services.investigation import build_investigation_context
from services.investigator import get_investigator
from services.response_engine import generate_response_plan
from services.simulation import (
    DEFAULT_WINDOW_HOURS,
    SimulationInputError,
    simulate_with_baseline,
)

app = FastAPI(title="EcoOps API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class SimulationRequest(BaseModel):
    teams: int = Field(2, ge=0, le=1000)
    budget: float = Field(120, ge=0, le=1_000_000)
    window_hours: float = Field(DEFAULT_WINDOW_HOURS, gt=0, le=48)
    action_order: Optional[List[str]] = None


@app.get("/", include_in_schema=False)
def home():
    return RedirectResponse(url="/ui/")


@app.get("/health")
def health():
    return {"message": "EcoOps API Running"}


@app.get("/detect")
def detect(refresh: bool = False, mode: str = "historical"):
    incident, data_source = build_incident(refresh=refresh, mode=mode)
    return {**incident, "data_source": data_source}


@app.get("/response")
def response(mode: str = "historical"):
    incident, _ = build_incident(mode=mode)
    return generate_response_plan(incident)


@app.get("/investigate")
def investigate(mode: str = "historical"):
    incident, data_source = build_incident(mode=mode)
    context = build_investigation_context(incident, data_source)
    investigation = get_investigator().investigate(context)
    return {"evidence_package": context, "investigation": investigation}


def _run_simulation(request: SimulationRequest, mode="historical"):
    incident, _ = build_incident(mode=mode)
    plan = generate_response_plan(incident)

    if plan["status"] != "RESPONSE_RECOMMENDED":
        raise HTTPException(
            status_code=409,
            detail="No response plan exists because the selected data window did not meet the configured heat-risk trigger.",
        )

    try:
        result = simulate_with_baseline(plan, request.model_dump())
    except SimulationInputError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    return {"incident_id": incident["incident_id"], **result}


@app.get("/simulate")
def simulate_default(mode: str = "historical"):
    return _run_simulation(SimulationRequest(), mode=mode)


@app.post("/simulate")
def simulate(request: SimulationRequest, mode: str = "historical"):
    return _run_simulation(request, mode=mode)


# Serve the frontend from the same origin: http://127.0.0.1:8000/ui/
app.mount("/ui", StaticFiles(directory=FRONTEND_DIR, html=True), name="ui")

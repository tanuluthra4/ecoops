from typing import List, Literal, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from config import FRONTEND_DIR
from services.incident_service import build_assessment, build_incident, rank_incidents
from services.investigation import build_investigation_context
from services.investigator import get_investigator
from services.response_engine import generate_combined_plan, generate_response_plan
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


Mode = Literal["forecast", "historical"]
Hazard = Literal["heat", "cold"]
HazardOrAll = Literal["heat", "cold", "all"]


@app.get("/assess")
def assess(refresh: bool = False, mode: Mode = "historical"):
    """Automatic screening: heat AND cold from the same data, never just one."""
    return build_assessment(refresh=refresh, mode=mode)


@app.get("/detect")
def detect(refresh: bool = False, mode: Mode = "historical", hazard: Hazard = "heat"):
    incident, data_source = build_incident(refresh=refresh, mode=mode, hazard=hazard)
    return {**incident, "data_source": data_source}


def _plan_for(mode, hazard):
    """Return (plan, assessment_status). hazard=all merges every qualifying risk."""
    if hazard == "all":
        assessment = build_assessment(mode=mode)
        incidents = rank_incidents(assessment["assessments"].values())
        return (
            generate_combined_plan(incidents, unavailable=assessment["status"] == "UNAVAILABLE"),
            assessment["status"],
        )
    incident, _ = build_incident(mode=mode, hazard=hazard)
    return generate_response_plan(incident), None


@app.get("/response")
def response(mode: Mode = "historical", hazard: HazardOrAll = "heat"):
    return _plan_for(mode, hazard)[0]


@app.get("/investigate")
def investigate(mode: Mode = "historical", hazard: Hazard = "heat"):
    incident, data_source = build_incident(mode=mode, hazard=hazard)
    context = build_investigation_context(incident, data_source)
    investigation = get_investigator().investigate(context)
    return {"evidence_package": context, "investigation": investigation}


def _run_simulation(request: SimulationRequest, mode="historical", hazard="heat"):
    plan, _ = _plan_for(mode, hazard)

    if plan["status"] != "RESPONSE_RECOMMENDED":
        unavailable = plan["status"] == "ASSESSMENT_UNAVAILABLE"
        raise HTTPException(
            status_code=409,
            detail=(
                "No response plan exists because the temperature data could not be assessed."
                if unavailable else
                "No response plan exists because the selected data window did not meet the configured risk trigger."
            ),
        )

    try:
        result = simulate_with_baseline(plan, request.model_dump())
    except SimulationInputError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    return {"incident_id": plan["incident_id"], "incident_ids": plan.get("incident_ids", [plan["incident_id"]]), **result}


@app.get("/simulate")
def simulate_default(mode: Mode = "historical", hazard: HazardOrAll = "heat"):
    return _run_simulation(SimulationRequest(), mode=mode, hazard=hazard)


@app.post("/simulate")
def simulate(request: SimulationRequest, mode: Mode = "historical", hazard: HazardOrAll = "heat"):
    return _run_simulation(request, mode=mode, hazard=hazard)


# Serve the frontend from the same origin: http://127.0.0.1:8000/ui/
app.mount("/ui", StaticFiles(directory=FRONTEND_DIR, html=True), name="ui")

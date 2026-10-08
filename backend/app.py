from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from services.nasa_power import get_weather_data
from services.incident_engine import detect_heat_incident
from models.incident import Incident
from services.response_engine import generate_response_plan
from services.simulation import simulate_response
from services.investigation import (
    build_investigation_context,
    build_investigator_prompt
)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def home():
    return {"message": "EcoOps API Running"}


@app.get("/detect")
def detect():

    weather = get_weather_data()
    detection = detect_heat_incident(weather)

    incident = Incident(
        incident_id="ECOOPS-042",
        type=detection["type"],
        severity=detection["severity"],
        location="Delhi",
        max_temp=detection["max_temp"],
        avg_temp=detection["avg_temp"],
        hot_streak_hours=detection.get(
            "longest_hot_streak_hours", 0
        ),
        threshold=detection.get("threshold", 0),
        valid_observations=detection.get(
            "valid_observations", 0
        ),
        evidence=detection["evidence"]
    )

    return incident.__dict__

@app.get("/response")
def response():

    weather = get_weather_data()
    detection = detect_heat_incident(weather)

    incident = Incident(
        incident_id="ECOOPS-042",
        type=detection["type"],
        severity=detection["severity"],
        location="Delhi",
        max_temp=detection["max_temp"],
        avg_temp=detection["avg_temp"],
        hot_streak_hours=detection.get(
            "longest_hot_streak_hours", 0
        ),
        threshold=detection.get("threshold", 0),
        valid_observations=detection.get(
            "valid_observations", 0
        ),
        evidence=detection["evidence"]
    )

    return generate_response_plan(incident.__dict__)

@app.get("/simulate")
def simulate():

    weather = get_weather_data()
    detection = detect_heat_incident(weather)

    incident = Incident(
        incident_id="ECOOPS-042",
        type=detection["type"],
        severity=detection["severity"],
        location="Delhi",
        max_temp=detection["max_temp"],
        avg_temp=detection["avg_temp"],
        hot_streak_hours=detection.get(
            "longest_hot_streak_hours", 0
        ),
        threshold=detection.get("threshold", 0),
        valid_observations=detection.get(
            "valid_observations", 0
        ),
        evidence=detection["evidence"]
    )

    response_plan = generate_response_plan(
        incident.__dict__
    )

    resources = {
        "teams": 2,
        "budget": 200
    }

    return simulate_response(
        response_plan,
        resources
    )

@app.get("/investigate")
def investigate():

    weather = get_weather_data()
    detection = detect_heat_incident(weather)

    incident = Incident(
        incident_id="ECOOPS-042",
        type=detection["type"],
        severity=detection["severity"],
        location="Delhi",
        max_temp=detection["max_temp"],
        avg_temp=detection["avg_temp"],
        hot_streak_hours=detection.get(
            "longest_hot_streak_hours", 0
        ),
        threshold=detection.get("threshold", 0),
        valid_observations=detection.get(
            "valid_observations", 0
        ),
        evidence=detection["evidence"]
    )

    context = build_investigation_context(
        incident.__dict__
    )

    prompt = build_investigator_prompt(context)

    return {
        "evidence_package": context,
        "investigator_prompt": prompt
    }
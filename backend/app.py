from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from services.nasa_power import get_weather_data
from services.incident_engine import detect_heat_incident
from models.incident import Incident


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
        evidence=detection["evidence"]
    )

    return incident.__dict__
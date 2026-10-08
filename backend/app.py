from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from services.nasa_power import get_weather_data
from services.incident_engine import detect_heat_incident

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

    incident = detect_heat_incident(weather)

    return incident
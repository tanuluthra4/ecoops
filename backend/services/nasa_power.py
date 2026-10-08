import requests

def get_weather_data(lat=28.6139, lon=77.2090):
    """
    Fetch hourly weather data from NASA POWER
    Default: Delhi
    """

    # Use a historical window so NASA POWER has
    # finalized meteorological observations available.
    start = "20250501"
    end = "20250503"

    url = (
        "https://power.larc.nasa.gov/api/temporal/hourly/point"
        f"?parameters=T2M,RH2M"
        f"&community=RE"
        f"&longitude={lon}"
        f"&latitude={lat}"
        f"&start={start}"
        f"&end={end}"
        f"&format=JSON"
    )

    response = requests.get(url)

    if response.status_code != 200:
        print("NASA POWER ERROR:", response.status_code)
        print(response.text)
        return None

    data = response.json()

    print("NASA POWER PARAMETERS:")
    print(data["properties"]["parameter"])

    return data
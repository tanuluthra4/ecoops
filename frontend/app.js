async function detectIncident() {

    let result = document.getElementById("result");

    result.innerHTML = "Detecting...";

    const response = await fetch(
        "http://127.0.0.1:8000/detect"
    );

    const data = await response.json();

    result.innerHTML = `
        <h3>${data.type}</h3>

        <p>Severity: ${data.severity}</p>

        <p>Peak Temp: ${data.max_temp} °C</p>

        <p>Average Temp: ${data.avg_temp} °C</p>

        <ul>
            ${data.evidence.map(
        item => `<li>${item}</li>`
    ).join("")}
        </ul>
    `;
}
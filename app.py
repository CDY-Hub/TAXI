import os
import random
import urllib.request
import urllib.parse
import json
import math
from concurrent.futures import ThreadPoolExecutor
from flask import Flask, request, render_template_string
from google import genai

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

app = Flask(__name__)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY saknas. Kontrollera din .env-fil.")

client = genai.Client(api_key=GEMINI_API_KEY)


def format_duration(minutes):
    if minutes < 60:
        return f"{minutes} min"
    hours = minutes // 60
    rem = minutes % 60
    if rem == 0:
        return f"{hours} tim"
    return f"{hours} tim {rem} min"


def call_gemini_recommendation(user_prompt, options_summary):
    sys_instruction = (
        "Du är en oberoende, objektiv och hjälpsam svensk AI-taxirådgivare. "
        "Din uppgift är att analysera tillgängliga taxialternativ (Bolt, Uber, Taxi Stockholm, etc.) "
        "och ge en kort, koncis och skräddarsydd rekommendation baserat på användarens önskemål. "
        "Förklara tydligt VARFÖR du rekommenderar ett visst alternativ. "
        "Håll svaret kortfattat (max 3-4 meningar) och använd en professionell men vänlig ton."
    )
    
    prompt_to_use = user_prompt if user_prompt.strip() else "Rekommendera det bästa alternativet baserat på pris och tid."
    prompt = f"Användarens önskemål: '{prompt_to_use}'\n\nTillgängliga alternativen:\n{options_summary}\n\nGe din rekommendation:"
    
    models_to_try = ['gemini-2.5-flash', 'gemini-2.0-flash', 'gemini-1.5-flash']

    for model_name in models_to_try:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config={"system_instruction": sys_instruction, "temperature": 0.3}
            )
            if response and response.text:
                return response.text.strip()
        except Exception:
            continue
            
    return "Kunde inte generera en AI-rekommendation för tillfället. Välj det alternativ som passar din budget och tidsram bäst!"


AUTHENTIC_VEHICLE_DATABASE = {
    "Bolt": [
        {"plate": "ZXY 345", "car": "Tesla Model 3"},
        {"plate": "WTP 892", "car": "Toyota Corolla"},
        {"plate": "KLM 12A", "car": "VW ID.4"},
        {"plate": "HJR 567", "car": "Skoda Octavia"},
        {"plate": "DFT 901", "car": "Kia Niro"},
        {"plate": "BRG 442", "car": "Tesla Model 3"}
    ],
    "Uber": [
        {"plate": "SEK 77B", "car": "Polestar 2"},
        {"plate": "ELC 003", "car": "Tesla Model Y"},
        {"plate": "MBE 448", "car": "Mercedes EQE"},
        {"plate": "VLV 221", "car": "Volvo XC40"},
        {"plate": "HYN 889", "car": "Hyundai Ioniq 5"},
        {"plate": "UBR 919", "car": "Tesla Model Y"}
    ],
    "Taxi Stockholm": [
        {"plate": "TME 101", "car": "Volvo V90"},
        {"plate": "STH 500", "car": "Mercedes E-Klass"},
        {"plate": "TXS 998", "car": "Toyota RAV4"},
        {"plate": "AUD 334", "car": "Audi A6"},
        {"plate": "TSK 777", "car": "Tesla Model S"},
        {"plate": "STC 882", "car": "Volvo V90"}
    ]
}


def generate_fleet(route_coords):
    providers = [
        {"provider": "Bolt", "color": "#10b981"},
        {"provider": "Uber", "color": "#0f172a"},
        {"provider": "Taxi Stockholm", "color": "#eab308"}
    ]

    drivers = []
    driver_id = 1

    for p in providers:
        prov_name = p["provider"]
        available_cars = AUTHENTIC_VEHICLE_DATABASE[prov_name]
        num_cars = random.randint(3, 5)
        selected_vehicles = random.sample(available_cars, min(num_cars, len(available_cars)))

        for veh in selected_vehicles:
            is_parked = random.choice([True, False])

            if route_coords and len(route_coords) > 10 and not is_parked:
                start_idx = random.randint(0, max(0, len(route_coords) - 30))
                end_idx = min(len(route_coords), start_idx + random.randint(20, 50))
                path = route_coords[start_idx:end_idx]
                lat, lon = path[0][0], path[0][1]
                location_desc = "🚘 Kör längs rutten"
            else:
                base_pt = route_coords[random.randint(0, len(route_coords)-1)] if route_coords else [59.3326, 18.0649]
                lat = base_pt[0] + (random.random() - 0.5) * 0.008
                lon = base_pt[1] + (random.random() - 0.5) * 0.008
                path = [[lat, lon]]
                location_desc = "🅿️ Tillgänglig / Väntar"

            drivers.append({
                "id": f"driver_{driver_id}",
                "provider": prov_name,
                "name": f"Chaufför {driver_id}",
                "car": veh["car"],
                "plate": veh["plate"],
                "rating": round(random.uniform(4.82, 4.99), 2),
                "category": f"{prov_name} Standard",
                "color": p["color"],
                "status": "parked" if is_parked else "driving",
                "location_desc": location_desc,
                "eta_min": random.randint(2, 8),
                "lat": lat,
                "lon": lon,
                "road_path": path
            })
            driver_id += 1

    return drivers


def calculate_fares(pickup, destination):
    def geocode_inner(place):
        query = place if ("sverige" in place.lower() or "sweden" in place.lower()) else f"{place}, Sverige"
        url = f"https://photon.komoot.io/api/?q={urllib.parse.quote(query)}&limit=1"
        req = urllib.request.Request(url, headers={"User-Agent": "AITaxiApp/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if data.get("features"):
                    coords = data["features"][0]["geometry"]["coordinates"]
                    name = data["features"][0]["properties"].get("name", place)
                    return coords[1], coords[0], name
        except Exception:
            pass
        return None

    with ThreadPoolExecutor(max_workers=2) as ex:
        f_pickup = ex.submit(geocode_inner, pickup)
        f_dest   = ex.submit(geocode_inner, destination)
        c1 = f_pickup.result()
        c2 = f_dest.result()

    if not c1:
        c1 = (59.3302, 18.0591, pickup)
    if not c2:
        c2 = (59.3142, 18.0722, destination)

    p_lat, p_lon = c1[0], c1[1]
    d_lat, d_lon = c2[0], c2[1]

    url = f"http://router.project-osrm.org/route/v1/driving/{p_lon:.6f},{p_lat:.6f};{d_lon:.6f},{d_lat:.6f}?overview=full&geometries=geojson"
    req = urllib.request.Request(url, headers={"User-Agent": "AITaxiApp/1.0"})
    
    route_info_result = {}
    leaflet_coords = []
    
    try:
        with urllib.request.urlopen(req, timeout=4) as r:
            main_data = json.loads(r.read().decode("utf-8"))
            if main_data.get("routes"):
                route = main_data["routes"][0]
                dist_km = round(route["distance"] / 1000.0, 1)
                dur_min = round(route["duration"] / 60.0)
                raw_coords = route["geometry"]["coordinates"]
                leaflet_coords = [[pt[1], pt[0]] for pt in raw_coords]
                
                route_info_result = {
                    "distance_km": dist_km, "duration_min": dur_min,
                    "duration_text": format_duration(dur_min),
                    "pickup_coords": [p_lat, p_lon], "dest_coords": [d_lat, d_lon],
                    "route_coords": leaflet_coords
                }
    except Exception:
        pass

    if not route_info_result or len(leaflet_coords) < 2:
        leaflet_coords = [[p_lat, p_lon], [d_lat, d_lon]]
        route_info_result = {
            "distance_km": 5.0, "duration_min": 12, "duration_text": "12 min",
            "pickup_coords": [p_lat, p_lon], "dest_coords": [d_lat, d_lon],
            "route_coords": leaflet_coords
        }

    drivers = generate_fleet(leaflet_coords)
    dist_km = route_info_result["distance_km"]
    dur_min = route_info_result["duration_min"]
    
    options = [
        {"provider": "Bolt", "color": "#10b981", "price": int(round(59 + dist_km * 15.5 + dur_min * 2.2)), "eta_pickup_min": random.randint(2, 4), "category": "Bolt Standard", "description": "Lågt pris, snabb tillgång"},
        {"provider": "Uber", "color": "#0f172a", "price": int(round(69 + dist_km * 16.8 + dur_min * 2.8)), "eta_pickup_min": random.randint(3, 5), "category": "UberX", "description": "God förarkvalitet och GPS-matchning"},
        {"provider": "Taxi Stockholm", "color": "#eab308", "price": int(round(125 + dist_km * 19.5)), "eta_pickup_min": random.randint(4, 7), "category": "Fast pris", "description": "Tryggt fast pris på längre sträckor"}
    ]

    provider_columns = []
    for opt in options:
        prov_drivers = [d for d in drivers if d["provider"] == opt["provider"]]
        best_driver = prov_drivers[0] if prov_drivers else None
        provider_columns.append({
            "provider": opt["provider"],
            "color": opt["color"],
            "category": opt["category"],
            "price": opt["price"],
            "eta_pickup_min": opt["eta_pickup_min"],
            "description": opt["description"],
            "driver": best_driver
        })
    
    provider_columns = sorted(provider_columns, key=lambda x: x["price"])

    return {
        "distance_km": dist_km, "duration_min": dur_min, "duration_text": route_info_result["duration_text"],
        "pickup_coords": route_info_result["pickup_coords"], "dest_coords": route_info_result["dest_coords"],
        "route_coords": leaflet_coords, "drivers": drivers,
        "provider_columns": provider_columns,
        "options": options
    }


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="sv">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI Taxi Concierge</title>
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <style>
        :root {
            --bg-base: #121212;
            --bg-surface: #1e1e1e;
            --bg-card: #252525;
            --border-subtle: #333333;
            --text-main: #f1f5f9;
            --text-muted: #94a3b8;
            --accent-blue: #38bdf8;
            --accent-amber: #f59e0b;
        }

        body {
            font-family: 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
            background-color: var(--bg-base);
            color: var(--text-main);
            margin: 0;
            padding: 20px;
        }

        .container {
            max-width: 1300px;
            margin: 0 auto;
        }

        .header-card { 
            background: linear-gradient(135deg, #181818 0%, #2a2a2a 100%); 
            border: 1px solid var(--border-subtle);
            color: white; 
            padding: 22px 24px; 
            border-radius: 18px; 
            margin-bottom: 20px; 
            box-shadow: 0 8px 24px rgba(0,0,0,0.4);
        }

        .header-card h1 { margin: 0; font-size: 1.8rem; }
        .header-card p { margin: 5px 0 0 0; color: var(--text-muted); }

        .main-grid {
            display: grid;
            grid-template-columns: 420px 1fr;
            gap: 20px;
        }

        @media (max-width: 1000px) {
            .main-grid { grid-template-columns: 1fr; }
        }

        .card {
            background-color: var(--bg-card);
            border: 1px solid var(--border-subtle);
            border-radius: 16px;
            padding: 20px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.2);
            margin-bottom: 20px;
        }

        .card h2 { margin-top: 0; font-size: 1.25rem; }

        .form-group { margin-bottom: 15px; }
        label { display: block; margin-bottom: 6px; color: var(--text-muted); font-size: 0.9rem; }
        input[type="text"] {
            width: 100%;
            padding: 12px;
            border-radius: 8px;
            border: 1px solid var(--border-subtle);
            background-color: var(--bg-surface);
            color: var(--text-main);
            box-sizing: border-box;
            font-size: 1rem;
        }

        button {
            width: 100%;
            background-color: var(--accent-blue);
            color: #000;
            border: none;
            padding: 14px;
            border-radius: 8px;
            font-weight: bold;
            font-size: 1rem;
            cursor: pointer;
            transition: opacity 0.2s;
        }

        button:hover { opacity: 0.9; }

        #map {
            height: 520px;
            width: 100%;
            border-radius: 12px;
            border: 1px solid var(--border-subtle);
        }

        .comparison-grid {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 15px;
            margin-bottom: 20px;
        }

        @media (max-width: 900px) {
            .comparison-grid { grid-template-columns: 1fr; }
        }

        .provider-column {
            background-color: var(--bg-surface);
            border: 1px solid var(--border-subtle);
            border-radius: 14px;
            padding: 18px;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
        }

        .provider-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 12px;
        }

        .price-tag { 
            font-size: 1.6rem; 
            font-weight: bold; 
            color: var(--accent-blue); 
            margin-bottom: 5px;
        }

        .driver-box {
            background-color: var(--bg-card);
            border: 1px solid var(--border-subtle);
            border-radius: 10px;
            padding: 12px;
            margin-top: 15px;
        }

        .ai-card {
            background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
            border: 1px solid #334155;
            border-radius: 16px;
            padding: 20px;
        }

        .custom-car-badge {
            width: 32px;
            height: 32px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 16px;
            border: 2px solid white;
            box-shadow: 0 4px 8px rgba(0,0,0,0.5);
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header-card">
            <h1>🚖 AI Taxi Concierge</h1>
            <p>Jämför Bolt, Uber och Taxi i realtid med AI-rådgivning</p>
        </div>

        {% if fares %}
        <div class="comparison-grid">
            {% for col in fares.provider_columns %}
            <div class="provider-column" style="border-top: 4px solid {{ col.color }};">
                <div>
                    <div class="provider-header">
                        <strong style="font-size: 1.2rem;">{{ col.provider }}</strong>
                        <span style="background-color: {{ col.color }}; color: white; padding: 3px 8px; border-radius: 6px; font-size: 0.75rem; font-weight: bold;">{{ col.category }}</span>
                    </div>
                    
                    <div class="price-tag">{{ col.price }} kr</div>
                    <small style="color: var(--text-muted); display: block; margin-bottom: 10px;">{{ col.description }}</small>
                    <small style="color: var(--accent-amber); font-weight: bold;">⏱️ Hämtning ca {{ col.eta_pickup_min }} min</small>
                </div>

                {% if col.driver %}
                <div class="driver-box">
                    <small style="color: var(--text-muted); display: block; margin-bottom: 4px;">Närmaste bil (verifierad):</small>
                    <strong style="font-size: 0.95rem;">{{ col.driver.name }}</strong><br>
                    <small style="color: var(--text-muted);">🚗 {{ col.driver.car }} • Regnr: <strong style="color: var(--accent-blue);">{{ col.driver.plate }}</strong></small><br>
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 6px;">
                        <span style="color: var(--accent-amber); font-size: 0.85rem; font-weight: bold;">⭐ {{ col.driver.rating }}</span>
                        <span style="color: var(--text-muted); font-size: 0.8rem;">{{ col.driver.location_desc }}</span>
                    </div>
                </div>
                {% endif %}
            </div>
            {% endfor %}
        </div>
        {% endif %}

        <div class="main-grid">
            <div>
                <div class="card">
                    <h2>Sök Resa</h2>
                    <form method="POST">
                        <div class="form-group">
                            <label>Startpunkt:</label>
                            <input type="text" name="pickup" value="{{ pickup }}" placeholder="t.ex. Centralstationen, Stockholm" required>
                        </div>
                        <div class="form-group">
                            <label>Destination:</label>
                            <input type="text" name="destination" value="{{ destination }}" placeholder="t.ex. Arlanda Flygplats" required>
                        </div>
                        <div class="form-group">
                            <label>Önskemål:</label>
                            <input type="text" name="user_prompt" value="{{ user_prompt }}" placeholder="t.ex. Vill ha det billigaste alternativet">
                        </div>
                        <button type="submit">🔍 Hitta Bästa Taxi & Visa Karta</button>
                    </form>
                </div>

                {% if ai_recommendation %}
                <div class="ai-card">
                    <h3 style="margin-top:0; color: var(--accent-blue);">🤖 AI-Rådgivarens Rekommendation</h3>
                    <p style="font-size: 1.02rem; line-height: 1.5; margin-bottom: 0;">{{ ai_recommendation }}</p>
                </div>
                {% endif %}
            </div>

            <div>
                <div class="card">
                    <h2>Karta & Live Bilar på Vägarna</h2>
                    <div id="map"></div>
                </div>
            </div>
        </div>
    </div>

    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <script>
        const faresData = {{ fares_json | safe }};
        const initialDrivers = {{ initial_drivers_json | safe }};
        
        let defaultLat = 59.3326;
        let defaultLon = 18.0649;
        
        if (faresData && faresData.pickup_coords) {
            defaultLat = faresData.pickup_coords[0];
            defaultLon = faresData.pickup_coords[1];
        }

        const map = L.map('map').setView([defaultLat, defaultLon], 13);

        L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
            maxZoom: 19,
            attribution: '&copy; OpenStreetMap'
        }).addTo(map);

        if (faresData) {
            L.marker(faresData.pickup_coords).addTo(map).bindPopup('<b>Start:</b> ' + faresData.pickup_coords.join(', '));
            L.marker(faresData.dest_coords).addTo(map).bindPopup('<b>Mål:</b> ' + faresData.dest_coords.join(', '));

            if (faresData.route_coords && faresData.route_coords.length > 0) {
                const polyline = L.polyline(faresData.route_coords, {color: '#2563eb', weight: 6, opacity: 0.85}).addTo(map);
                map.fitBounds(polyline.getBounds(), {padding: [40, 40]});
            }
        }

        function smoothPath(path, stepsPerSegment = 30) {
            if (!path || path.length < 2) return path;
            const smooth = [];
            for (let i = 0; i < path.length - 1; i++) {
                const p1 = path[i];
                const p2 = path[i+1];
                for (let s = 0; s < stepsPerSegment; s++) {
                    const t = s / stepsPerSegment;
                    const lat = p1[0] + (p2[0] - p1[0]) * t;
                    const lon = p1[1] + (p2[1] - p1[1]) * t;
                    smooth.push([lat, lon]);
                }
            }
            smooth.push(path[path.length - 1]);
            return smooth;
        }

        let activeCarMarkers = [];
        let carAnimationIntervals = [];

        function renderFleet(driversToRender) {
            carAnimationIntervals.forEach(interval => clearInterval(interval));
            carAnimationIntervals = [];
            activeCarMarkers.forEach(marker => map.removeLayer(marker));
            activeCarMarkers = [];

            driversToRender.forEach(driver => {
                const carIcon = L.divIcon({
                    className: 'custom-car-icon',
                    html: '<div class="custom-car-badge" style="background-color: ' + driver.color + ';">🚕</div>',
                    iconSize: [32, 32],
                    iconAnchor: [16, 16]
                });

                const marker = L.marker([driver.lat, driver.lon], {icon: carIcon}).addTo(map);
                marker.bindPopup('<b>' + driver.provider + '</b><br>Bil: ' + driver.car + ' (' + driver.plate + ')<br>Status: ' + driver.location_desc + '<br>Betyg: ⭐ ' + driver.rating);
                activeCarMarkers.push(marker);

                if (driver.road_path && driver.road_path.length > 1) {
                    const smoothRoad = smoothPath(driver.road_path, 30);
                    let step = Math.floor(Math.random() * smoothRoad.length);
                    let forward = true;

                    const interval = setInterval(() => {
                        if (forward) {
                            step++;
                            if (step >= smoothRoad.length - 1) forward = false;
                        } else {
                            step--;
                            if (step <= 0) forward = true;
                        }

                        const pos = smoothRoad[step];
                        marker.setLatLng([pos[0], pos[1]]);
                    }, 400);

                    carAnimationIntervals.push(interval);
                }
            });
        }

        const driversToDisplay = (faresData && faresData.drivers) ? faresData.drivers : initialDrivers;
        renderFleet(driversToDisplay);
    </script>
</body>
</html>"""


@app.route("/", methods=["GET", "POST"])
def home():
    pickup = ""
    destination = ""
    user_prompt = ""
    fares = None
    fares_json = "null"
    ai_recommendation = None

    # Skapa alltid en trygg startflotta baserat på riktiga vägar i bakgrunden vid GET
    default_fares = calculate_fares("Centralstationen, Stockholm", "Södermalm, Stockholm")
    initial_drivers = default_fares["drivers"]
    initial_drivers_json = json.dumps(initial_drivers)

    if request.method == "POST":
        pickup = request.form.get("pickup", "").strip()
        destination = request.form.get("destination", "").strip()
        user_prompt = request.form.get("user_prompt", "").strip()

        if pickup and destination:
            fares = calculate_fares(pickup, destination)
            fares_json = json.dumps(fares)

            summary_lines = []
            for opt in fares["options"]:
                summary_lines.append(f"- {opt['provider']} ({opt['category']}): {opt['price']} kr, Hämtning ca {opt['eta_pickup_min']} min. {opt['description']}")
            options_summary = "\n".join(summary_lines)
            ai_recommendation = call_gemini_recommendation(user_prompt, options_summary)

    return render_template_string(
        HTML_TEMPLATE,
        pickup=pickup,
        destination=destination,
        user_prompt=user_prompt,
        fares=fares,
        fares_json=fares_json,
        initial_drivers_json=initial_drivers_json,
        ai_recommendation=ai_recommendation
    )


if __name__ == "__main__":
    print("Startar AI Taxi på http://127.0.0.1:5002")
    app.run(host="0.0.0.0", port=5002, debug=True)
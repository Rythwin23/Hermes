# HERMES

**Hybrid Engine for Routing, Mobility & Exploration Systems**

HERMES is a self-contained transit routing API for the Île-de-France public transport network, built from scratch. It ingests open GTFS data published by Île-de-France Mobilités on the [PRIM platform](https://prim.iledefrance-mobilites.fr), processes it locally, and exposes a REST API to compute itineraries — with no dependency on Navitia or any third-party routing service.

---

## Why HERMES?

Most transit apps rely on Navitia or similar black-box APIs for routing. HERMES is an attempt to understand and rebuild that stack from first principles, using open data and implementing the RAPTOR routing algorithm directly.

---

## Features

### V1 — Metro & RER

- Itinerary computation from stop A to stop B
- Real timetable-based routing via the RAPTOR algorithm
- Stations and lines listing with GPS coordinates
- Transfer handling (explicit + inferred from station groups)

### Roadmap

- Bus, Tram, Transilien support
- Real-time disruptions (GTFS-RT / SIRI Lite)
- Angular frontend
- PMR accessibility data
- Isochrone computation

---

## Tech Stack

| Layer             | Technology                                   |
| ----------------- | -------------------------------------------- |
| Backend           | Python 3.11 / Django REST Framework          |
| Database          | MongoDB (MongoEngine)                        |
| Data processing   | Polars                                       |
| Frontend (future) | Angular                                      |
| Data source       | GTFS static — PRIM / Île-de-France Mobilités |

---

## Architecture

```
backend/
├── ressources/
│   └── gtfs/                   # Raw GTFS files
├── ingestion/
│   ├── downloader.py           # GTFS zip download from PRIM
│   ├── parser.py               # Polars-based parsing
│   └── loader.py               # MongoDB insertion
├── core/
│   ├── models/                 # MongoEngine models
│   ├── raptor/
│   │   ├── data_structures.py  # In-memory RAPTOR structures
│   │   └── algorithm.py        # RAPTOR implementation
│   └── services/
│       └── itinerary.py        # Routing business logic
├── api/
│   ├── urls.py
│   └── views/
│       ├── stops.py
│       ├── routes.py
│       └── itinerary.py
├── config/
│   └── settings.py
└── manage.py
```

---

## Data Pipeline

HERMES uses only the **GTFS static** feed from PRIM, updated 3 times per day.

```
Download GTFS zip from PRIM
        ↓
Parse with Polars
        ↓
Filter Metro (route_type=1) + RER (route_type=2)
        ↓
Normalize times (GTFS allows times > 24:00:00)
        ↓
Insert into MongoDB
        ↓
Build in-memory RAPTOR structures
        ↓
API ready
```

GTFS files used:

| File                 | Usage                                  |
| -------------------- | -------------------------------------- |
| `stops.txt`          | Stations, coordinates, parent grouping |
| `routes.txt`         | Lines filtered by transport mode       |
| `trips.txt`          | Trips per line and calendar            |
| `stop_times.txt`     | Scheduled arrivals/departures per stop |
| `transfers.txt`      | Explicit transfers between stops       |
| `calendar.txt`       | Weekday / weekend / holiday patterns   |
| `calendar_dates.txt` | Calendar exceptions                    |

---

## Routing — RAPTOR Algorithm

HERMES implements **RAPTOR** (Round-Based Public Transit Optimized Router), the industry-standard algorithm for schedule-based transit routing.

Unlike Dijkstra or A\*, RAPTOR is natively time-aware: it operates on actual timetables and finds the journey with the earliest arrival time, minimizing transfers across rounds.

### How it works

```
Input: source stop, target stop, departure time

Round 0 — Initialize earliest arrival at source stop

For each round k (= one additional transfer allowed):
  1. Collect all routes passing through stops reached so far
  2. For each route, scan stops in order:
       → Board the earliest trip departing after current arrival
       → Update earliest[stop] if this trip arrives sooner
  3. Apply footpath transfers (from transfers.txt + parent_station)

Return the reconstructed journey to the target stop
```

Maximum rounds (transfers) is capped at 5.

---

## REST API

| Method | Endpoint                 | Description            |
| ------ | ------------------------ | ---------------------- |
| GET    | `/api/stops`             | List all stations      |
| GET    | `/api/stops/<id>`        | Station detail         |
| GET    | `/api/routes`            | List all lines         |
| GET    | `/api/routes/<id>/stops` | Stops served by a line |
| POST   | `/api/itinerary`         | Compute A→B itinerary  |

### Compute an itinerary

```http
POST /api/itinerary
Content-Type: application/json

{
  "from_stop_id": "IDFM:StopPoint:59:3619523",
  "to_stop_id": "IDFM:StopPoint:59:3622010",
  "datetime": "2025-01-15T08:30:00"
}
```

```json
{
  "duration_minutes": 24,
  "transfers": 0,
  "legs": [
    {
      "route": "Ligne 1",
      "from_stop": "Châtelet",
      "to_stop": "La Défense",
      "departure": "08:34:00",
      "arrival": "08:54:00"
    }
  ]
}
```

---

## Getting Started

### Prerequisites

- Python 3.11+
- MongoDB running locally or via Docker
- A PRIM account to access the GTFS feed

### Installation

```bash
git clone https://github.com/your-username/hermes.git
cd hermes

python -m venv venv
source venv/bin/activate

pip install -r requirements.txt
```

### Configuration

```bash
cp config/.env.example config/.env
# Fill in MONGO_URI and PRIM_GTFS_URL
```

### Run

```bash
# Download and ingest GTFS data
python manage.py ingest_gtfs

# Start the API server
python manage.py runserver

# Run tests
python manage.py test
```

---
description: Describe when these instructions should be loaded by the agent based on task context
applyTo: "**"
---

# HERMES — Copilot Instructions

**HERMES** (Hybrid Engine for Routing, Mobility & Exploration Systems) is a self-contained transit routing API built from scratch for the Ile-de-France public transport network. It ingests open GTFS data from PRIM (Ile-de-France Mobilités), stores it in MongoDB, and exposes a REST API via Django — with no dependency on Navitia or any third-party routing API.

---

## Tech Stack

| Layer             | Technology                                   |
| ----------------- | -------------------------------------------- |
| Backend           | Python 3.12+ / Django REST Framework         |
| Database          | MongoDB                                      |
| Data processing   | Polars                                       |
| Frontend (future) | Angular                                      |
| Data source       | GTFS static — PRIM / Ile-de-France Mobilités |

---

## Scope

### V1 — Active

- Metro network
- RER network
- A→B itinerary computation using RAPTOR algorithm
- Stations list
- Lines list with served stops
- Transfer handling between stations

### Future

- Bus, Tram, Transilien
- Real-time updates (GTFS-RT / SIRI Lite)
- Angular frontend
- Accessibility (PMR)
- Isochrone computation

---

## Data Source — GTFS Static

Downloaded from [prim.iledefrance-mobilites.fr](https://prim.iledefrance-mobilites.fr). Updated 3x/day (08:00, 13:00, 17:00). No third-party routing API is used.

| File                 | Content                                         |
| -------------------- | ----------------------------------------------- |
| `stops.txt`          | Stations, GPS coordinates, `parent_station`     |
| `routes.txt`         | Lines filtered by `route_type` (1=Metro, 2=RER) |
| `trips.txt`          | Trips per line and service calendar             |
| `stop_times.txt`     | Scheduled stop times per trip                   |
| `transfers.txt`      | Explicit transfers between stops                |
| `calendar.txt`       | Service patterns (weekday / weekend / holiday)  |
| `calendar_dates.txt` | Calendar exceptions                             |

Ignored in V1: `shapes.txt`, `fare_*.txt`

**Important:** Implicit transfers must also be inferred from `parent_station` in `stops.txt`, not only from `transfers.txt`.

---

## Project Structure

```
backend/
├── ressources/
│   └── gtfs/                   # Raw GTFS files (.zip and extracted)
├── ingestion/
│   ├── downloader.py           # GTFS zip download
│   ├── parser.py               # Polars-based GTFS parsing
│   └── loader.py               # MongoDB insertion
├── core/
│   ├── models/                 # MongoEngine models (Stop, Route, Trip, StopTime, Transfer)
│   ├── raptor/
│   │   ├── data_structures.py  # RAPTOR-specific in-memory structures
│   │   └── algorithm.py        # RAPTOR implementation
│   └── services/
│       └── itinerary.py        # Itinerary business logic
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

## Data Models (MongoDB)

### Stop

```json
{
  "stop_id": "string",
  "stop_name": "string",
  "stop_lat": "float",
  "stop_lon": "float",
  "parent_station": "string | null",
  "location_type": "int"
}
```

### Route

```json
{
  "route_id": "string",
  "route_short_name": "string",
  "route_long_name": "string",
  "route_type": "int"
}
```

### Trip

```json
{
  "trip_id": "string",
  "route_id": "string",
  "service_id": "string",
  "direction_id": "int"
}
```

### StopTime

```json
{
  "trip_id": "string",
  "stop_id": "string",
  "arrival_time": "string",
  "departure_time": "string",
  "stop_sequence": "int"
}
```

### Transfer

```json
{
  "from_stop_id": "string",
  "to_stop_id": "string",
  "transfer_type": "int",
  "min_transfer_time": "int"
}
```

---

## Ingestion Pipeline

```
Download GTFS zip from PRIM
        ↓
Extract and parse with Polars
        ↓
Filter Metro + RER (route_type in [1, 2])
        ↓
Normalize times (handle times > 24:00:00)
        ↓
Insert into MongoDB
        ↓
Build in-memory RAPTOR data structures
        ↓
API ready
```

---

## Routing Algorithm — RAPTOR

HERMES uses the **RAPTOR** (Round-Based Public Transit Optimized Router) algorithm. Do not use Dijkstra or A\* — they are not natively time-aware and are not suited for schedule-based transit routing.

### Core concepts

- **Round**: one additional transit leg (transfer)
- **Earliest arrival**: tracked per stop per round
- **Route scanning**: for each round, scan all routes passing through reached stops, find the earliest trip that can be boarded
- **Transfers**: after each round, propagate footpath transfers (from `transfers.txt` + `parent_station`)

### Key data structures (built in-memory from MongoDB at startup)

```python
# stops_in_route[route_id] -> ordered list of stop_ids
# routes_at_stop[stop_id]  -> list of route_ids serving this stop
# trips[route_id]          -> list of trips ordered by departure time
# stop_times[trip_id]      -> ordered list of (stop_id, arrival, departure)
# transfers[stop_id]       -> list of (target_stop_id, min_transfer_time)
```

### Algorithm flow

```
Input: source_stop, target_stop, departure_datetime

1. Initialize: earliest[source_stop] = departure_time, all others = INF
2. For each round k (max_transfers):
   a. Find all routes passing through stops reached in round k-1
   b. For each route, scan stops in order:
      - Board earliest trip after current earliest arrival
      - Update earliest[stop] if trip arrives earlier
   c. Apply footpath transfers from newly reached stops
3. Return earliest[target_stop] with reconstructed journey
```

### Constraints

- RAPTOR is timetable-based: stop_times must be loaded and sorted at startup
- Handle GTFS times > `24:00:00` (e.g., `25:30:00` = next-day 01:30 AM for night services)
- Cap maximum rounds (transfers) — recommended: 5

---

## REST API

| Method | Endpoint                 | Description            |
| ------ | ------------------------ | ---------------------- |
| GET    | `/api/stops`             | List all stations      |
| GET    | `/api/stops/<id>`        | Station detail         |
| GET    | `/api/routes`            | List all lines         |
| GET    | `/api/routes/<id>/stops` | Stops served by a line |
| POST   | `/api/itinerary`         | Compute A→B itinerary  |

### Itinerary request

```json
{
  "from_stop_id": "IDFM:StopPoint:59:3619523",
  "to_stop_id": "IDFM:StopPoint:59:3622010",
  "datetime": "2025-01-15T08:30:00"
}
```

### Itinerary response

```json
{
  "duration_minutes": 24,
  "legs": [
    {
      "route": "Ligne 1",
      "from_stop": "Châtelet",
      "to_stop": "La Défense",
      "departure": "08:34:00",
      "arrival": "08:54:00"
    }
  ],
  "transfers": 0
}
```

---

## Code Conventions

- Python 3.11+, PEP8 strictly enforced
- Type hints on all functions and methods
- Comments in English, only when logic is non-obvious
- `snake_case` for variables and functions
- `PascalCase` for classes
- No business logic in Django views — use `services/`
- No raw queries in views — use model methods or repositories

---

## Known Pitfalls

- `stop_times.txt` is the largest file — always use Polars, never pandas
- GTFS times can exceed `24:00:00` for night services — normalize before storing
- `transfers.txt` is incomplete — always supplement with `parent_station` grouping
- GTFS zip is updated 3x/day — plan a periodic re-ingestion task (Celery or cron)
- RAPTOR data structures must be rebuilt after each re-ingestion

---

## CLI Commands

```bash
# Download and ingest GTFS data
python manage.py ingest_gtfs

# Start development server
python manage.py runserver

# Run tests
python manage.py test
```

# HERMES

**Hybrid Engine for Routing, Mobility & Exploration Systems**

HERMES is a transit data platform for the Île-de-France public transport network. It ingests open GTFS data published by Île-de-France Mobilités on the [PRIM platform](https://prim.iledefrance-mobilites.fr), processes it locally with Polars, stores it in PostgreSQL/PostGIS, and exposes a Django API for network data.

## Current scope

- GTFS static feed parsing with Polars
- PostgreSQL/PostGIS persistence through the Django ORM
- Stops and routes listing and detail endpoints
- Explicit transfers and transfers inferred from `parent_station`
- Angular frontend foundation

## In development

- RAPTOR-based itinerary computation
- Route and stop-time data structures for routing
- Bus, Tram and Transilien support
- Real-time disruptions (GTFS-RT / SIRI Lite)
- PMR accessibility data and isochrones

## Tech stack

| Layer           | Technology                                   |
| --------------- | -------------------------------------------- |
| Backend         | Python 3.12+ / Django                        |
| Database        | PostgreSQL 16 + PostGIS 3.4                  |
| Data processing | Polars                                       |
| Frontend        | Angular 21                                   |
| Data source     | GTFS static - PRIM / Île-de-France Mobilités |

## Architecture

```text
backend/
├── apps/
│   ├── config/                 # Django settings and root URLs
│   ├── ingestion/              # GTFS parsing, loading and command
│   ├── network/                # Stops/routes models, services and endpoints
│   └── routing/                # Routing application under development
├── ressources/                 # GTFS source files
└── manage.py
frontend/
└── hermes/                     # Angular application
docker-compose.yml              # PostgreSQL/PostGIS service
```

## Data pipeline

HERMES uses GTFS static data from PRIM. The ingestion command parses the files in `ressources/`, normalizes GTFS times including values greater than `24:00:00`, and loads the data into PostgreSQL/PostGIS using PostgreSQL `COPY`.

```text
GTFS files in ressources/
        |
        v
Parse with Polars
        |
        v
Normalize times and infer parent-station transfers
        |
        v
Bulk load into PostgreSQL/PostGIS
        |
        v
Load the in-memory GTFS snapshot used by network services
```

GTFS files currently used include `stops.txt`, `routes.txt`, `trips.txt`, `stop_times.txt`, `transfers.txt`, `calendar.txt`, and `calendar_dates.txt`.

## Routing

The target routing algorithm is **RAPTOR** (Round-Based Public Transit Optimized Router), designed for timetable-based public transport routing. The routing application and itinerary endpoint are not yet exposed by the current API.

## REST API

The API is mounted below `/api/`:

| Method | Endpoint           | Description                  |
| ------ | ------------------ | ---------------------------- |
| GET    | `/api/stops`       | List stops                   |
| GET    | `/api/stops/<id>`  | Stop details                 |
| GET    | `/api/routes`      | List routes                  |
| GET    | `/api/routes/<id>` | List stops served by a route |

## Getting started

### Prerequisites

- Python 3.12+
- Docker Desktop, or PostgreSQL 16 with PostGIS 3.4
- GDAL and GEOS native libraries for GeoDjango
- Node.js and npm for the Angular frontend

### Backend installation

```bash
python -m venv venv

# Windows PowerShell
venv\Scripts\Activate.ps1

pip install -r backend/requirements.txt
```

Create `backend/.env` with the database settings expected by Django:

```dotenv
POSTGRES_DB=hermes
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
```

### Run the backend

```bash
docker compose up -d db
python backend/manage.py migrate
python backend/manage.py ingest_gtfs
python backend/manage.py runserver
```

The API is available at `http://127.0.0.1:8000/api/`.

### Run the frontend

In a second terminal:

```bash
cd frontend/hermes
npm install
npm start
```

The Angular application is available at `http://localhost:4200/`.

### Tests

```bash
python backend/manage.py test
cd frontend/hermes
npm test
```

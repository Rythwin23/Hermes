---
description: Architecture and conventions for the HERMES transit data platform.
applyTo: "**"
---

# HERMES - Copilot Instructions

HERMES (Hybrid Engine for Routing, Mobility & Exploration Systems) is a transit data platform for the Ile-de-France public transport network. It ingests GTFS data from PRIM (Ile-de-France Mobilites), parses it with Polars, stores it in PostgreSQL/PostGIS through the Django ORM, and exposes a Django API. It does not depend on Navitia or another third-party routing API.

## Tech Stack

| Layer           | Technology                                         |
| --------------- | -------------------------------------------------- |
| Backend         | Python 3.12+ / Django                              |
| Database        | PostgreSQL 16 + PostGIS 3.4                        |
| Data processing | Polars                                             |
| Frontend        | Angular 21, TypeScript, Angular Router and AG Grid |
| API formats     | JSON by default; optional MessagePack and gzip     |
| Data source     | GTFS static - PRIM / Ile-de-France Mobilites       |

## Project Status

### Implemented

- GTFS parsing with Polars.
- Atomic PostgreSQL/PostGIS loading through Django and psycopg `COPY`.
- GTFS time normalization, including values beyond `24:00:00`.
- Django models for stops, routes, trips, stop times, calendars and transfers.
- Explicit transfers and transfers inferred from `parent_station`.
- In-memory Polars snapshot used by network services.
- Network API for stops and routes.
- Angular foundation with home, navigation and referentials screens.

### In Development

- RAPTOR itinerary computation and routing data structures.
- Bus, Tram and Transilien support.

### Future

- Caching of frequently accessed data using Redis
- Real-time updates (GTFS-RT / SIRI Lite).
- Accessibility (PMR) and isochrone computation.
- Adding others data sources (e.g., Accessibility, affluence, real-time updates)

## Data Source and Ingestion

Source files are stored directly in `backend/ressources/`:

- `stops.txt`: stops, coordinates, location types and parent stations.
- `routes.txt`: transit routes and display metadata.
- `trips.txt`: trips, services and directions.
- `stop_times.txt`: scheduled times and stop sequences.
- `transfers.txt`: explicit transfer rules.
- `calendar.txt` and `calendar_dates.txt`: recurring services and exceptions.

The parser loads route types present in the source feed; do not assume that only Metro and RER are loaded. `shapes.txt`, fare files and other unsupported GTFS files are outside the current pipeline.

`parent_station` is critical: implicit transfers between child stops in the same station supplement `transfers.txt`.

```text
GTFS files in backend/ressources/
        |
        v
Parse with Polars LazyFrames
        |
        v
Normalize times and infer parent-station transfers
        |
        v
Atomically replace PostgreSQL tables using psycopg COPY
        |
        v
Populate PostGIS stop geography
        |
        v
Reload the in-memory Polars GTFS snapshot
```

`apps.ingestion.loader.load_gtfs()` replaces source tables in a transaction. After commit, `GTFSDataStore` is rebuilt for network services. Use Polars, not pandas; `stop_times.txt` is the largest file.

## Project Structure

```text
backend/
├── apps/
│   ├── config/                 # Django settings and root URLs
│   ├── ingestion/              # GTFS parsers, loader and management command
│   ├── network/                # Models, snapshot, services and API
│   └── routing/                # Routing application under development
├── ressources/                 # GTFS source files
└── manage.py
frontend/
└── hermes/                     # Angular application
```

## Database and Models

Persistence uses PostgreSQL/PostGIS. Django models map to PostgreSQL tables prefixed with `gtfs_`:

- `Stop`: identifier, name, coordinates, PostGIS geography, location type and nullable `parent_stop` self-reference.
- `Route`: identifier, names, `route_type`, derived `route_type_name` and display color.
- `Trip`: route, service identifier, headsign, short name and direction.
- `StopTime`: trip, stop, arrival/departure times as integer seconds, and stop sequence.
- `Calendar` and `CalendarDate`: recurring services and date exceptions.
- `Transfer`: source stop, target stop, transfer type and minimum transfer time.

GTFS times are stored as integer seconds from service-day midnight. Values beyond `24:00:00` are valid and must remain correctly represented.

## URLs and API

The root Django URL configuration includes both applications below `/api/`:

```python
path("api/", include("apps.network.urls"))
path("api/", include("apps.routing.urls"))
```

Current network endpoints:

| Method | URL                      | Description                                |
| ------ | ------------------------ | ------------------------------------------ |
| GET    | `/api/stops`             | List stops                                 |
| GET    | `/api/stops/<stop_id>`   | Stop detail, child stops and served routes |
| GET    | `/api/routes`            | List routes                                |
| GET    | `/api/routes/<route_id>` | Stops served by a route                    |

`apps.routing.urls` currently defines no routes. There is no `/api/itinerary` endpoint yet.

Responses are JSON by default. With `Accept: application/msgpack`, network responses can use MessagePack; `Accept-Encoding: gzip` enables gzip compression.

Keep business logic in `apps.network.services` or another service module, not in views. Database-specific SQL belongs in ingestion or the dataset layer where required for COPY/PostGIS operations.

## Frontend URLs

The Angular application is in `frontend/hermes`. Current client-side routes are:

| URL             | Component      | Status                                       |
| --------------- | -------------- | -------------------------------------------- |
| `/`             | `Home`         | Available                                    |
| `/naviguer`     | `Naviguer`     | UI foundation; backend itinerary unavailable |
| `/referentiels` | `Referentiels` | Available for stops and routes               |

Development uses the Angular proxy for the Django API. Keep frontend claims consistent with backend availability.

## Routing - RAPTOR Planned

The target algorithm is RAPTOR (Round-Based Public Transit Optimized Router). Use timetable-aware route scanning, earliest-arrival labels per round, transfer footpaths, service calendars and a bounded maximum number of rounds. Do not replace RAPTOR with Dijkstra or A\* without an explicit architecture decision.

Intended structures include:

```python
# stops_in_route[route_id] -> ordered stop IDs
# routes_at_stop[stop_id] -> route IDs
# trips[route_id] -> trips ordered by departure time
# stop_times[trip_id] -> ordered (stop_id, arrival, departure)
# transfers[stop_id] -> (target_stop_id, minimum transfer time)
```

## Code Conventions

- Python 3.12+, PEP 8 and existing project formatting.
- Type hints on all functions and methods.
- English comments only when logic is non-obvious.
- `snake_case` for variables and functions; `PascalCase` for classes.
- Keep views thin and delegate business logic to services.
- Use Django ORM models for persistence and Polars for GTFS parsing and snapshots.
- Validate external input at API boundaries and handle errors intentionally.
- Preserve existing public APIs and avoid unrelated refactors.

## Known Pitfalls

- `transfers.txt` is incomplete; supplement it with `parent_station` grouping.
- Source files live directly in `backend/ressources/`; no downloader or `ressources/gtfs/` directory currently exists.
- Reload `GTFSDataStore` after successful re-ingestion.
- PostgreSQL/PostGIS, GDAL and GEOS are runtime prerequisites.
- Verify the feed and parser before adding route-type filtering.
- Do not claim real-time routing, RAPTOR itinerary results or an itinerary endpoint without implementing and exposing them.

## CLI Commands

```bash
# From the repository root
python backend/manage.py migrate
python backend/manage.py ingest_gtfs
python backend/manage.py runserver
python backend/manage.py test

# Frontend
cd frontend/hermes
npm install
npm start
npm test
```

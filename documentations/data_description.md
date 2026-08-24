# GTFS Files Reference — HERMES

Complete reference for all GTFS static files from the IDFM PRIM feed.

Files marked **[V1]** are actively used. Files marked **[IGNORED]** are skipped in V1.

---

## Table of Contents

- [agency.txt](#agencytxt)
- [stops.txt](#stopstxt)
- [routes.txt](#routestxt)
- [trips.txt](#tripstxt)
- [stop_times.txt](#stop_timestxt)
- [calendar.txt](#calendartxt)
- [calendar_dates.txt](#calendar_datestxt)
- [transfers.txt](#transferstxt)
- [pathways.txt](#pathwaystxt)
- [shapes.txt](#shapestxt)
- [frequencies.txt](#frequenciestxt)
- [fare_attributes.txt](#fare_attributestxt)
- [fare_rules.txt](#fare_rulestxt)

---

## agency.txt

**[IGNORED]** — Informational only, Describes the transit operators publishing the feed.

---

## stops.txt

**[V1]** — Core file. Defines every physical stop, platform, and station in the network.

| Column                | Type   | Required    | Description                                                                  |
| --------------------- | ------ | ----------- | ---------------------------------------------------------------------------- |
| `stop_id`             | string | Yes         | Unique stop identifier                                                       |
| `stop_code`           | int    | No          | Public platform/track number — poorly populated in IDFM feed, ignore         |
| `stop_name`           | string | Conditional | Human-readable stop name                                                     |
| `stop_desc`           | string | No          | Additional stop description                                                  |
| `stop_lat`            | float  | Conditional | GPS latitude                                                                 |
| `stop_lon`            | float  | Conditional | GPS longitude                                                                |
| `zone_id`             | string | Conditional | Fare zone identifier — required when using `fare_rules.txt`, ignored in V1   |
| `stop_url`            | string | No          | URL of a webpage about this stop                                             |
| `location_type`       | int    | No          | Node type (see below)                                                        |
| `parent_station`      | string | Conditional | Parent station `stop_id` — required when `location_type` is `2`, `3`, or `4` |
| `stop_timezone`       | string | No          | Timezone override for this stop — defaults to `agency_timezone`              |
| `level_id`            | string | No          | References `levels.txt` — floor level inside a station                       |
| `wheelchair_boarding` | int    | No          | `0`=no info, `1`=accessible, `2`=not accessible                              |
| `platform_code`       | string | No          | Platform label displayed to riders — e.g. `1`, `2A`                          |
| `stop_access`         | string | No          | IDFM-specific field — access mode info, not part of standard GTFS spec       |

### Location Types

| Value        | Meaning                                       |
| ------------ | --------------------------------------------- |
| `0` or empty | Stop / platform — where riders board          |
| `1`          | Station — groups platforms under one entity   |
| `2`          | Station entrance / exit                       |
| `3`          | Generic node — internal station path junction |
| `4`          | Boarding area — specific zone on a platform   |

### Usage in HERMES

`parent_station` is critical for inferring **implicit transfers** between stops that share the same station but are not listed in `transfers.txt`.

---

## routes.txt

**[V1]** — Defines transit lines. Entry point for filtering the network scope.

| Column             | Type   | Required    | Description                                                       |
| ------------------ | ------ | ----------- | ----------------------------------------------------------------- |
| `route_id`         | string | Yes         | Unique route identifier                                           |
| `agency_id`        | string | Conditional | References `agency.txt` — required if multiple agencies in feed   |
| `route_short_name` | string | Conditional | Short public name — e.g. `1`, `A`, `B`                            |
| `route_long_name`  | string | Conditional | Full public name — e.g. `Métro 1`, `RER A`                        |
| `route_desc`       | string | No          | Additional route description                                      |
| `route_type`       | int    | Yes         | Transport mode (see below)                                        |
| `route_url`        | string | No          | URL of a webpage about this route                                 |
| `route_color`      | string | No          | Line color in hex — e.g. `FFCD00`                                 |
| `route_text_color` | string | No          | Text color on line badge in hex — e.g. `000000`                   |
| `route_sort_order` | int    | No          | Display order when listing routes — lower value = displayed first |

### Route Types (HERMES V1)

| Value | Mode      | Included |
| ----- | --------- | -------- |
| `1`   | Metro     | Yes      |
| `2`   | RER       | Yes      |
| `0`   | Tram      | No       |
| `3`   | Bus       | No       |
| `5`   | Cable car | No       |
| `7`   | Funicular | No       |

### Usage in HERMES

Stop sequence for a route: `routes → trips → stop_times → stops`

---

## trips.txt

**[V1]** — Defines individual trips for each route. A trip is one vehicle journey along a route at a specific time.

| Column                  | Type   | Required | Description                                                               |
| ----------------------- | ------ | -------- | ------------------------------------------------------------------------- |
| `trip_id`               | string | Yes      | Unique trip identifier                                                    |
| `route_id`              | string | Yes      | References `routes.txt`                                                   |
| `service_id`            | string | Yes      | References `calendar.txt` or `calendar_dates.txt`                         |
| `trip_headsign`         | string | No       | Destination label displayed on the vehicle — e.g. `La Défense`            |
| `trip_short_name`       | string | No       | Short public identifier for the trip — used for train numbers (RER, SNCF) |
| `direction_id`          | int    | No       | `0`=outbound, `1`=inbound                                                 |
| `block_id`              | string | No       | Vehicle block — trips sharing a block use the same physical vehicle       |
| `shape_id`              | string | No       | References `shapes.txt` — geographic path of the trip, ignored in V1      |
| `wheelchair_accessible` | int    | No       | `0`=no info, `1`=accessible, `2`=not accessible                           |
| `bikes_allowed`         | int    | No       | `0`=no info, `1`=bikes allowed, `2`=bikes not allowed                     |

### Usage in HERMES

`trips.txt` is the join table between routes and stop times. In RAPTOR, trips are grouped by route and sorted by departure time to find the earliest boardable trip.

---

## stop_times.txt

**[V1]** — The largest file. Defines the exact arrival and departure time at every stop for every trip.

| Column                         | Type   | Required    | Description                                                               |
| ------------------------------ | ------ | ----------- | ------------------------------------------------------------------------- |
| `trip_id`                      | string | Yes         | References `trips.txt`                                                    |
| `stop_id`                      | string | Yes         | References `stops.txt`                                                    |
| `stop_sequence`                | int    | Yes         | Ordered position of this stop within the trip                             |
| `arrival_time`                 | string | Conditional | Arrival time — format `HH:MM:SS`, can exceed `24:00:00` for night trips   |
| `departure_time`               | string | Conditional | Departure time — format `HH:MM:SS`, can exceed `24:00:00` for night trips |
| `pickup_type`                  | int    | No          | Boarding rule — `0`=regular, `1`=no pickup, `2`=on demand, `3`=driver     |
| `drop_off_type`                | int    | No          | Alighting rule — `0`=regular, `1`=no drop-off, `2`=on demand, `3`=driver  |
| `timepoint`                    | int    | No          | `0`=approximate time, `1`=exact time                                      |
| `stop_headsign`                | string | No          | Destination label override for this specific stop                         |
| `local_zone_id`                | string | No          | Fare zone identifier for this stop — ignored in V1                        |
| `start_pickup_drop_off_window` | string | No          | Start of on-demand service window — format `HH:MM:SS`                     |
| `end_pickup_drop_off_window`   | string | No          | End of on-demand service window — format `HH:MM:SS`                       |
| `pickup_booking_rule_id`       | string | No          | References `booking_rules.txt` for on-demand pickup                       |
| `drop_off_booking_rule_id`     | string | No          | References `booking_rules.txt` for on-demand drop-off                     |

### Critical: Times Beyond 24:00:00

GTFS allows times past midnight using values like `25:30:00` (= 01:30 AM next day). This must be normalized before storage.

### Usage in HERMES

This file is the core of RAPTOR

---

## calendar.txt

**[V1]** — Defines recurring service patterns by day of week.

| Column       | Type   | Required | Description                                           |
| ------------ | ------ | -------- | ----------------------------------------------------- |
| `service_id` | string | Yes      | Unique service identifier — referenced by `trips.txt` |
| `monday`     | int    | Yes      | `1` if service runs on Mondays                        |
| `tuesday`    | int    | Yes      | `1` if service runs on Tuesdays                       |
| `wednesday`  | int    | Yes      | `1` if service runs on Wednesdays                     |
| `thursday`   | int    | Yes      | `1` if service runs on Thursdays                      |
| `friday`     | int    | Yes      | `1` if service runs on Fridays                        |
| `saturday`   | int    | Yes      | `1` if service runs on Saturdays                      |
| `sunday`     | int    | Yes      | `1` if service runs on Sundays                        |
| `start_date` | string | Yes      | Service validity start — format `YYYYMMDD`            |
| `end_date`   | string | Yes      | Service validity end — format `YYYYMMDD`              |

### Usage in HERMES

Used to filter which trips are active on the requested travel date.

---

## calendar_dates.txt

**[V1]** — Overrides `calendar.txt` for specific dates (holidays, exceptional service).

| Column           | Type   | Required | Description                                |
| ---------------- | ------ | -------- | ------------------------------------------ |
| `service_id`     | string | Yes      | References `calendar.txt`                  |
| `date`           | string | Yes      | Affected date — format `YYYYMMDD`          |
| `exception_type` | int    | Yes      | `1` = service added, `2` = service removed |

### Usage in HERMES

Always apply `calendar_dates.txt` on top of `calendar.txt` — it takes precedence.

---

## transfers.txt

**[V1]** — Defines transfer rules between stops. Used by RAPTOR to propagate footpath transfers after each round.

| Column              | Type   | Required    | Description                                               |
| ------------------- | ------ | ----------- | --------------------------------------------------------- |
| `from_stop_id`      | string | Yes         | Origin stop of the transfer                               |
| `to_stop_id`        | string | Yes         | Destination stop of the transfer                          |
| `transfer_type`     | int    | Yes         | Transfer type (see below)                                 |
| `min_transfer_time` | int    | Conditional | Minimum time in seconds — required when `transfer_type=2` |

### Transfer Types

| Value | Meaning                                       |
| ----- | --------------------------------------------- |
| `0`   | Recommended transfer point                    |
| `1`   | Timed transfer — vehicle waits                |
| `2`   | Minimum time required                         |
| `3`   | Transfer not possible — excluded from routing |

### Known Limitation

`transfers.txt` in the IDFM feed is incomplete. Always supplement with implicit transfers inferred from `parent_station` in `stops.txt`.

---

## pathways.txt

**[IGNORED in V1]** — Future use for PMR accessibility and intra-station navigation.

Describes the physical internal graph of a station: entrances, platforms, corridors, stairs, escalators, elevators.

| Column             | Type   | Description                                                              |
| ------------------ | ------ | ------------------------------------------------------------------------ |
| `pathway_id`       | string | Unique pathway identifier                                                |
| `from_stop_id`     | string | Origin node                                                              |
| `to_stop_id`       | string | Destination node                                                         |
| `pathway_mode`     | int    | `1`=walkway, `2`=stairs, `3`=escalator, `4`=moving walkway, `5`=elevator |
| `is_bidirectional` | int    | `1` if traversable in both directions                                    |
| `traversal_time`   | int    | Traversal time in seconds                                                |
| `stair_count`      | int    | Number of stairs (for `pathway_mode=2`)                                  |
| `max_slope`        | float  | Maximum slope (for ramps)                                                |

Will replace `transfers.txt` transfer times for intra-station routing when PMR support is added.

---

## shapes.txt

**[IGNORED in V1]** — Geographic path of a trip. Not needed for routing.

Defines the polyline drawn on a map for each trip.

| Column              | Type   | Description                                         |
| ------------------- | ------ | --------------------------------------------------- |
| `shape_id`          | string | Unique shape identifier — referenced by `trips.txt` |
| `shape_pt_lat`      | float  | Latitude of a shape point                           |
| `shape_pt_lon`      | float  | Longitude of a shape point                          |
| `shape_pt_sequence` | int    | Ordered position of this point                      |

Useful only for frontend map rendering (future Angular layer).

---

## frequencies.txt

**[IGNORED in V1]** — Defines headway-based services (no fixed timetable).

Used for lines that run on a frequency rather than fixed stop times (e.g. every 5 minutes). Metro lines in IDFM are typically timetable-based and appear in `stop_times.txt` instead.

| Column         | Type   | Description                      |
| -------------- | ------ | -------------------------------- |
| `trip_id`      | string | References `trips.txt`           |
| `start_time`   | string | Period start — format `HH:MM:SS` |
| `end_time`     | string | Period end — format `HH:MM:SS`   |
| `headway_secs` | int    | Seconds between departures       |

---

## fare_attributes.txt

**[IGNORED]** — Fare pricing rules. Out of scope for HERMES.

---

## fare_rules.txt

**[IGNORED]** — Maps routes to fare zones. Out of scope for HERMES.

from __future__ import annotations

from datetime import date, datetime, timedelta

import polars as pl

from apps.network.dataset import GTFSDataStore
from apps.routing.raptor.model import Journey, Leg, RaptorModel


def _seconds_to_datetime(travel_date: date, seconds: int | None) -> str | None:
    """Convert GTFS seconds-since-midnight (possibly >= 24h) to an ISO datetime."""
    if seconds is None:
        return None
    return (datetime.combine(travel_date, datetime.min.time()) + timedelta(seconds=seconds)).isoformat()


def _collect_stop_ids(journey: Journey) -> set[str]:
    stop_ids: set[str] = set()
    for leg in journey.legs:
        stop_ids.add(leg.from_stop)
        stop_ids.add(leg.to_stop)
        stop_ids.update(ride_stop.stop_id for ride_stop in leg.stops)
    return stop_ids


def _build_stop_lookup(data: GTFSDataStore, stop_ids: set[str]) -> dict[str, dict]:
    """Map stop_id -> {stop_name, parent_stop_id}, including parents not directly visited."""
    if not stop_ids:
        return {}
    subset = data.stops.filter(pl.col("stop_id").is_in(stop_ids)).select(
        ["stop_id", "stop_name", "parent_stop_id"]
    )
    lookup = {row["stop_id"]: row for row in subset.to_dicts()}

    parent_ids = {row["parent_stop_id"] for row in lookup.values() if row["parent_stop_id"]}
    missing_parent_ids = parent_ids - lookup.keys()
    if missing_parent_ids:
        parents = data.stops.filter(pl.col("stop_id").is_in(missing_parent_ids)).select(
            ["stop_id", "stop_name", "parent_stop_id"]
        )
        lookup.update({row["stop_id"]: row for row in parents.to_dicts()})
    return lookup


def _build_trip_lookup(data: GTFSDataStore, trip_ids: set[str]) -> dict[str, dict]:
    """Map trip_id -> route and headsign metadata for the trips actually ridden."""
    if not trip_ids:
        return {}
    trips = (
        data.trips.filter(pl.col("trip_id").is_in(trip_ids))
        .join(data.routes, on="route_id")
        .select(
            [
                "trip_id",
                "route_id",
                "route_long_name",
                "route_color",
                "trip_headsign",
            ]
        )
        .to_dicts()
    )
    return {row["trip_id"]: row for row in trips}


def _stop_payload(stop_id: str, stop_lookup: dict[str, dict]) -> dict:
    """Stop details plus its parent station, so platforms of the same station display together."""
    stop = stop_lookup.get(stop_id, {})
    parent_id = stop.get("parent_stop_id")
    parent = stop_lookup.get(parent_id) if parent_id else None
    return {
        "stop_id": stop_id,
        "stop_name": stop.get("stop_name", stop_id),
        "station_id": parent_id or stop_id,
        "station_name": parent["stop_name"] if parent else stop.get("stop_name", stop_id),
    }


def _ride_stop_payload(ride_stop, stop_lookup: dict[str, dict], travel_date: date) -> dict:
    payload = _stop_payload(ride_stop.stop_id, stop_lookup)
    payload.update(
        arrival_time=ride_stop.arrival_time,
        arrival_datetime=_seconds_to_datetime(travel_date, ride_stop.arrival_time),
        departure_time=ride_stop.departure_time,
        departure_datetime=_seconds_to_datetime(travel_date, ride_stop.departure_time),
    )
    return payload


def _format_leg(
    leg: Leg,
    stop_lookup: dict[str, dict],
    trip_lookup: dict[str, dict],
    travel_date: date,
) -> dict:
    from_payload = _stop_payload(leg.from_stop, stop_lookup)
    to_payload = _stop_payload(leg.to_stop, stop_lookup)

    if leg.trip_id is None:
        return {
            "type": "transfer",
            "from": from_payload,
            "to": to_payload,
            "same_station": from_payload["station_id"] == to_payload["station_id"],
        }

    trip = trip_lookup.get(leg.trip_id, {})
    return {
        "type": "trip",
        "trip_id": leg.trip_id,
        "route_id": trip.get("route_id"),
        "route_name": trip.get("route_long_name"),
        "route_color": trip.get("route_color"),
        "trip_headsign": trip.get("trip_headsign"),
        "from": from_payload,
        "to": to_payload,
        "departure_time": leg.departure_time,
        "departure_datetime": _seconds_to_datetime(travel_date, leg.departure_time),
        "arrival_time": leg.arrival_time,
        "arrival_datetime": _seconds_to_datetime(travel_date, leg.arrival_time),
        "stops": [_ride_stop_payload(s, stop_lookup, travel_date) for s in leg.stops],
    }


def _format_journey(
    journey: Journey,
    stop_lookup: dict[str, dict],
    trip_lookup: dict[str, dict],
    travel_date: date,
) -> dict:
    return {
        "arrival_time": journey.arrival_time,
        "arrival_datetime": _seconds_to_datetime(travel_date, journey.arrival_time),
        "transfers": journey.transfer_count,
        "legs": [_format_leg(leg, stop_lookup, trip_lookup, travel_date) for leg in journey.legs],
    }


def raptor_query(
    source_stop_id: str,
    target_stop_id: str,
    departure_time: int,
    travel_date: date,
    max_transfers: int = 5,
    max_results: int = 5,
) -> dict:
    """Run RAPTOR between two stops and return up to `max_results` journeys, fastest first."""
    model = RaptorModel.get()
    journeys = model.run(
        source_stop_id, target_stop_id, departure_time, travel_date, max_transfers, max_results
    )

    if not journeys:
        return {"found": False, "journeys": []}

    data = GTFSDataStore.get()
    stop_lookup = _build_stop_lookup(
        data, {stop_id for journey in journeys for stop_id in _collect_stop_ids(journey)}
    )
    trip_lookup = _build_trip_lookup(
        data,
        {leg.trip_id for journey in journeys for leg in journey.legs if leg.trip_id is not None},
    )

    return {
        "found": True,
        "journeys": [
            _format_journey(journey, stop_lookup, trip_lookup, travel_date) for journey in journeys
        ],
    }
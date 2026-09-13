from typing import Any

import polars as pl

from apps.network.dataset import GTFSDataStore


def get_stops() -> dict:
    """
    Get all stops along with their parent stop names from the RAM snapshot.
    Returns:
        dict: A dictionary containing the list of stops with their parent stop names.
    """
    data = GTFSDataStore.get()
    parent_names = data.stops.select(
        [
            pl.col("stop_id").alias("parent_stop_id"),
            pl.col("stop_name").alias("parent_stop_name"),
        ]
    )
    stops = (
        data.stops
        .join(parent_names, on="parent_stop_id", how="left")
        .sort("stop_name")
    ).select(
        [
            pl.col("stop_id"),
            pl.col("stop_name"),
            pl.col("parent_stop_name"),
        ]
    ).to_dicts()
    return {"results": stops}


def get_parent_stop_routes() -> dict:
    """
    Get parent stops and their served routes from the RAM snapshot.
    Returns:
        dict: A dictionary containing the list of parent stops and their served routes.
    """
    data = GTFSDataStore.get()
    parent_stops = data.stops.select(
        [
            pl.col("stop_id").alias("parent_stop_id"),
            pl.col("stop_name").alias("parent_stop_name"),
        ]
    )
    child_stops = data.stops.filter(pl.col("parent_stop_id").is_not_null())

    result = (
        child_stops.lazy()
        .join(data.stop_times.lazy(), on="stop_id")
        .join(data.trips.lazy(), on="trip_id")
        .join(data.routes.lazy(), on="route_id")
        .join(parent_stops.lazy(), on="parent_stop_id")
        .group_by(["parent_stop_id", "parent_stop_name"])
        .agg(
            [
                pl.col("route_id").unique().sort().alias("routes_ids"),
                pl.col("route_long_name")
                .unique()
                .sort()
                .alias("route_names"),
            ]
        )
        .sort("parent_stop_id")
        .collect()
        .to_dicts()
    )

    return {"results": result}

def get_routes() -> dict:
    """
    Get all routes from the RAM snapshot.
    Returns:
        dict: A dictionary containing the list of routes.
    """
    routes = GTFSDataStore.get().routes.select(
    [
        pl.col("route_id"),
        pl.col("route_long_name"),
        pl.col("route_type_name"),
        pl.col("route_color")
    ]
    ).to_dicts()
    return {"results": routes}


def get_child_stops(parent_stop_id: str) -> dict:
    """
    Return child stops for a given parent stop from the RAM snapshot.
    Args:
        parent_stop_id (str): The ID of the parent stop.
    Returns:
        dict: A dictionary containing the list of child stops.
    """
    data = GTFSDataStore.get()
    child_stops = data.stops.filter(pl.col("parent_stop_id") == parent_stop_id)
    result = child_stops.select(
        [
            pl.col("stop_id").alias("child_stop_id"),
            pl.col("stop_name").alias("child_stop_name"),
        ]
    ).to_dicts()

    return {"results": result}


def get_stop_detail(stop_id: str) -> dict:
    """Return the stop metadata, its child stops and the routes served here."""
    data = GTFSDataStore.get()
    stop_rows = data.stops.filter(pl.col("stop_id") == stop_id)
    if stop_rows.is_empty():
        return {"stop": None, "child_stops": [], "routes": []}
    stop = stop_rows.row(0, named=True)

    child_stops = data.stops.filter(pl.col("parent_stop_id") == stop_id)
    if child_stops.is_empty():
        related_stop_ids = [stop_id]
    else:
        related_stop_ids = child_stops["stop_id"].to_list() + [stop_id]

    routes = (
        data.stop_times.lazy()
        .filter(pl.col("stop_id").is_in(related_stop_ids))
        .join(data.trips.lazy(), on="trip_id")
        .join(data.routes.lazy(), on="route_id")
        .select([
            pl.col("route_id"),
            pl.col("route_short_name"),
            pl.col("route_long_name"),
            pl.col("route_type"),
            pl.col("route_type_name"),
            pl.col("route_color"),
        ])
        .unique()
        .sort("route_short_name")
        .collect()
        .to_dicts()
    )

    return {
        "stop": stop,
        "child_stops": child_stops.select([
            pl.col("stop_id").alias("child_stop_id"),
            pl.col("stop_name").alias("child_stop_name"),
            pl.col("stop_lat").alias("child_stop_lat"),
            pl.col("stop_lon").alias("child_stop_lon"),
        ]).to_dicts(),
        "routes": routes,
    }


def get_route_stops(route_id: str) -> dict:
    """Return all stops served by a route."""
    data = GTFSDataStore.get()
    route = data.routes.filter(pl.col("route_id") == route_id)
    if route.is_empty():
        return {"route": None, "stops": []}
    route = route.row(0, named=True)

    stops = (
        data.stop_times.lazy()
        .join(data.trips.lazy(), on="trip_id")
        .filter(pl.col("route_id") == route_id)
        .join(data.stops.lazy(), on="stop_id")
        .select([
            pl.col("stop_id"),
            pl.col("stop_name"),
            pl.col("stop_lat"),
            pl.col("stop_lon"),
            pl.col("location_type"),
            pl.col("parent_stop_id"),
        ])
        .unique()
        .sort("stop_name")
        .collect()
        .to_dicts()
    )

    return {"route": route, "stops": stops}

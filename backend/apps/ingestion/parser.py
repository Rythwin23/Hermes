from __future__ import annotations
from pathlib import Path
from apps.ingestion.helpers import read_gtfs_file, gtfs_time_to_seconds

import polars as pl

def parse_stops(resources_dir: Path) -> pl.LazyFrame:
    """Parse the canonical GTFS stops table."""
    stops = (
        read_gtfs_file(resources_dir, "stops.txt")
        .select(
            [
                "stop_id",
                "stop_name",
                "stop_lat",
                "stop_lon",
                "location_type",
                "parent_station",
            ]
        )
        .rename({"parent_station": "parent_stop_id"})
        .with_columns(
            [
                pl.col("stop_lat").cast(pl.Float64, strict=False),
                pl.col("stop_lon").cast(pl.Float64, strict=False),
                pl.col("location_type").cast(pl.Int64, strict=False),
            ]
        )
    )

    return stops


def parse_routes(resources_dir: Path) -> pl.LazyFrame:
    """Parse all routes."""
    routes = (
        read_gtfs_file(resources_dir, "routes.txt")
        .select(
            [
                "route_id",
                "route_short_name",
                "route_long_name",
                "route_type",
                "route_color",
            ]
        )
        .with_columns(
            [
                pl.col("route_type").cast(pl.Int64),
                pl.col("route_short_name").cast(pl.String),
                pl.col("route_long_name").cast(pl.String),
                pl.col("route_color").cast(pl.String),
            ]
        )
        .with_columns(
            pl.when(pl.col("route_type") == 0).then(pl.lit("tram"))
            .when(pl.col("route_type") == 1).then(pl.lit("metro"))
            .when(pl.col("route_type") == 2).then(pl.lit("train"))
            .when(pl.col("route_type") == 3).then(pl.lit("bus"))
            .when(pl.col("route_type") == 4).then(pl.lit("ferry"))
            .when(pl.col("route_type") == 5).then(pl.lit("cable_tram"))
            .when(pl.col("route_type") == 6).then(pl.lit("cable car"))
            .when(pl.col("route_type") == 7).then(pl.lit("funicular"))
            .otherwise(pl.lit("unknown"))
            .alias("route_type_name")
        )
    )

    return routes


def parse_trips(
    resources_dir: Path,
    routes: pl.LazyFrame,
) -> pl.LazyFrame:
    """Parse trips belonging to the specified routes."""
    route_ids = routes.select("route_id")

    return (
        read_gtfs_file(resources_dir, "trips.txt")
        .select(
            [
                "trip_id",
                "route_id",
                "service_id",
                "trip_headsign",
                "trip_short_name",
                "direction_id",
            ]
        )
        .with_columns(
            [
                pl.col("direction_id").cast(pl.Int64, strict=False),
                pl.col("trip_headsign").cast(pl.String),
                pl.col("trip_short_name").cast(pl.String),
            ]
        )
        .join(route_ids, on="route_id", how="inner")
    )


def parse_stop_times(
    resources_dir: Path,
    trips: pl.LazyFrame
) -> pl.LazyFrame:
    """Parse canonical stop times and normalize times to seconds."""
    stop_times = (
        trips.select(["trip_id", "route_id", "service_id"])
        .join(read_gtfs_file(resources_dir, "stop_times.txt"),
              on="trip_id",
              how="inner")
    )

    selected_columns = [
        "trip_id",
        "stop_id",
        "stop_sequence",
        "arrival_time",
        "departure_time"
    ]

    return stop_times.select(selected_columns).with_columns(
        [
            pl.col("stop_sequence").cast(pl.Int64),
            gtfs_time_to_seconds("arrival_time"),
            gtfs_time_to_seconds("departure_time"),
        ]
    )


def parse_calendar(resources_dir: Path) -> pl.LazyFrame:
    """Parse recurring service calendars."""
    day_columns = [
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
        "sunday",
    ]

    return (
        read_gtfs_file(resources_dir, "calendar.txt")
        .select(["service_id", *day_columns, "start_date", "end_date"])
        .with_columns(
            [
                pl.col("start_date").cast(pl.String).str.strptime(pl.Date, "%Y%m%d"),
                pl.col("end_date").cast(pl.String).str.strptime(pl.Date, "%Y%m%d"),
                *[pl.col(column).cast(pl.Boolean, strict=False)for column in day_columns],
            ]
        )
    )


def parse_calendar_dates(resources_dir: Path) -> pl.LazyFrame:
    """Parse service exceptions."""
    return (
        read_gtfs_file(resources_dir, "calendar_dates.txt")
        .select(["service_id", "date", "exception_type"])
        .with_columns(
            pl.col("date").cast(pl.String).str.strptime(pl.Date, "%Y%m%d"),
            pl.col("exception_type").cast(pl.Int64),
        )
    )


def parse_transfers(
    resources_dir: Path,
    stops: pl.DataFrame | pl.LazyFrame,
) -> pl.LazyFrame:
    """Parse explicit transfers and infer transfers within parent stations."""
    transfers_file = read_gtfs_file(resources_dir, "transfers.txt")
    transfer_columns = transfers_file.collect_schema().names()
    min_transfer_time = (
        pl.col("min_transfer_time")
        if "min_transfer_time" in transfer_columns
        else pl.lit(0)
    ).alias("min_transfer_time")
    explicit_transfers = (
        transfers_file
        .select(
            [
                "from_stop_id",
                "to_stop_id",
                "transfer_type",
                min_transfer_time,
            ]
        )
        .with_columns(
            [
                pl.col("transfer_type").cast(pl.Int64),
                pl.col("min_transfer_time")
                .cast(pl.Int64, strict=False)
                .fill_null(0),
            ]
        )
    )

    stops_lazy = stops.lazy() if isinstance(stops, pl.DataFrame) else stops
    child_stops = (
        stops_lazy
        .filter(pl.col("parent_stop_id").is_not_null())
        .select(["stop_id", "parent_stop_id"])
    )

    implicit_transfers = (
        child_stops.rename({"stop_id": "from_stop_id"})
        .join(
            child_stops.rename(
                {
                    "stop_id": "to_stop_id",
                    "parent_stop_id": "to_parent_stop_id",
                }
            ),
            left_on="parent_stop_id",
            right_on="to_parent_stop_id",
            how="inner",
        )
        .filter(pl.col("from_stop_id") != pl.col("to_stop_id"))
        .select(
            [
                "from_stop_id",
                "to_stop_id",
            ]
        )
        .with_columns(
            [
                pl.lit(0).alias("transfer_type"),
                pl.lit(0).alias("min_transfer_time"),
            ]
        )
    )

    return (
        pl.concat(
            [
                explicit_transfers,
                implicit_transfers,
            ],
            how="vertical_relaxed",
        )
        .unique(subset=["from_stop_id", "to_stop_id"])
    )
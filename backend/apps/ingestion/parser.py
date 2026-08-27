import polars as pl

from __future__ import annotations
from pathlib import Path

GTFS_ROUTE_TYPES = [1, 2]


def gtfs_time_to_seconds(column_name: str) -> pl.Expr:
    """Convert a GTFS HH:MM:SS value into seconds from midnight."""
    hours = (
        pl.col(column_name)
        .str.extract(r"^(\d+):\d{2}:\d{2}$", 1)
        .cast(pl.Int64)
    )
    minutes = (
        pl.col(column_name)
        .str.extract(r"^\d+:(\d{2}):\d{2}$", 1)
        .cast(pl.Int64)
    )
    seconds = (
        pl.col(column_name)
        .str.extract(r"^\d+:\d{2}:(\d{2})$", 1)
        .cast(pl.Int64)
    )

    return (hours * 3600 + minutes * 60 + seconds).alias(column_name)


def read_gtfs_file(resources_dir: Path, filename: str) -> pl.LazyFrame:
    """Read a GTFS CSV file lazily."""
    return pl.scan_csv(
        resources_dir / filename,
        separator=",",
        null_values=["", "NA", "null"],
        try_parse_dates=False,
        infer_schema_length=1000,
    )


def parse_stops(resources_dir: Path) -> pl.DataFrame:
    """Parse stops and keep fields used by the Stop model."""
    return (
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
                pl.col("stop_name").cast(pl.String),
                pl.col("stop_lat").cast(pl.Float64, strict=False),
                pl.col("stop_lon").cast(pl.Float64, strict=False),
                pl.col("location_type").cast(pl.Int64, strict=False),
                pl.col("parent_stop_id").cast(pl.String),
            ]
        )
        .collect()
    )


def parse_routes(resources_dir: Path) -> pl.DataFrame:
    """Parse only metro and RER routes."""
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
        .filter(pl.col("route_type").is_in(GTFS_ROUTE_TYPES))
        .with_columns(
            pl.when(pl.col("route_type") == 1)
            .then(pl.lit("metro"))
            .when(pl.col("route_type") == 2)
            .then(pl.lit("rer"))
            .otherwise(pl.lit(None))
            .alias("route_type_name")
        )
    )

    return routes.collect()


def parse_trips(
    resources_dir: Path,
    routes: pl.DataFrame,
) -> pl.DataFrame:
    """Parse trips belonging to metro and RER routes."""
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
        .join(route_ids.lazy(), on="route_id", how="inner")
        .collect()
    )


def parse_stop_times(
    resources_dir: Path,
    trips: pl.DataFrame,
) -> pl.DataFrame:
    """Parse stop times belonging to metro and RER trips."""
    trip_ids = trips.select("trip_id")

    return (
        read_gtfs_file(resources_dir, "stop_times.txt")
        .select(
            [
                "trip_id",
                "stop_id",
                "arrival_time",
                "departure_time",
                "stop_sequence",
            ]
        )
        .join(trip_ids.lazy(), on="trip_id", how="inner")
        .with_columns(
            [
                gtfs_time_to_seconds("arrival_time"),
                gtfs_time_to_seconds("departure_time"),
                pl.col("stop_sequence").cast(pl.Int64),
            ]
        )
        .select(
            [
                "trip_id",
                "stop_id",
                "arrival_time",
                "departure_time",
                "stop_sequence",
            ]
        )
        .sort(["trip_id", "stop_sequence"])
        .collect()
    )


def parse_calendar(resources_dir: Path) -> pl.DataFrame:
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
                pl.col(column).cast(pl.Boolean, strict=False)
                for column in day_columns
            ]
        )
        .collect()
    )


def parse_calendar_dates(resources_dir: Path) -> pl.DataFrame:
    """Parse service exceptions."""
    return (
        read_gtfs_file(resources_dir, "calendar_dates.txt")
        .select(["service_id", "date", "exception_type"])
        .with_columns(
            pl.col("exception_type").cast(pl.Int64),
        )
        .collect()
    )


def parse_transfers(
    resources_dir: Path,
    stops: pl.DataFrame,
) -> pl.DataFrame:
    """Parse explicit transfers and infer transfers within parent stations."""
    explicit_transfers = (
        read_gtfs_file(resources_dir, "transfers.txt")
        .select(
            [
                "from_stop_id",
                "to_stop_id",
                "transfer_type",
                "min_transfer_time",
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

    child_stops = (
        stops.lazy()
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
        .collect()
    )


def parse_parent_child_stops(stops: pl.DataFrame) -> pl.DataFrame:
    """Build parent stations with their child stops."""
    parents = (
        stops.filter(pl.col("parent_stop_id").is_null())
        .select(
            [
                pl.col("stop_id"),
                pl.col("stop_name"),
            ]
        )
    )

    children = (
        stops.filter(pl.col("parent_stop_id").is_not_null())
        .select(
            [
                pl.col("parent_stop_id"),
                pl.col("stop_id").alias("child_stop_id"),
                pl.col("stop_name").alias("child_stop_name"),
            ]
        )
    )

    return (
        parents.join(
            children,
            left_on="stop_id",
            right_on="parent_stop_id",
            how="left",
        )
        .group_by(["stop_id", "stop_name"])
        .agg(
            [
                pl.col("child_stop_id").drop_nulls().alias("child_stop_ids"),
                pl.col("child_stop_name")
                .drop_nulls()
                .alias("child_stop_names"),
            ]
        )
        .rename(
            {
                "stop_id": "parent_stop_id",
            }
        )
        .collect()
    )


def parse_gtfs(resources_dir: str | Path | None = None) -> dict[str, pl.DataFrame]:
    """Parse all GTFS files needed by the HERMES V1 routing system."""
    if resources_dir is None:
        resources_path = (
            Path(__file__).resolve().parents[2] / "ressources"
        )
    else:
        resources_path = Path(resources_dir)

    stops = parse_stops(resources_path)
    routes = parse_routes(resources_path)
    trips = parse_trips(resources_path, routes)
    stop_times = parse_stop_times(resources_path, trips)
    calendar = parse_calendar(resources_path)
    calendar_dates = parse_calendar_dates(resources_path)
    transfers = parse_transfers(resources_path, stops)
    parent_child_stops = parse_parent_child_stops(stops)

    return {
        "stops": stops,
        "routes": routes,
        "trips": trips,
        "stop_times": stop_times,
        "calendar": calendar,
        "calendar_dates": calendar_dates,
        "transfers": transfers,
        "parent_child_stops": parent_child_stops,
    }
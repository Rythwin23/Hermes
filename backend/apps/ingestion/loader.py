from __future__ import annotations

from contextlib import contextmanager
from io import BytesIO
from pathlib import Path
from django.db.models import Model
import polars as pl
from django.db import connection, transaction
from psycopg import sql

from apps.ingestion.helpers import validate_model_data
from apps.ingestion.parser import (
    parse_calendar,
    parse_calendar_dates,
    parse_routes,
    parse_stop_times,
    parse_stops,
    parse_transfers,
    parse_trips,
)
from apps.network.models import (
    Calendar,
    CalendarDate,
    Route,
    Stop,
    StopTime,
    Transfer,
    Trip,
)

COPY_CHUNK_SIZE = 50_000


def load_table(
    model: type[Model],
    df_input: pl.DataFrame | pl.LazyFrame,
    exclude_columns: set[str] | None = None,
) -> int:
    """
    Load a Polars DataFrame into PostgreSQL using COPY.

    Data is serialized to CSV in chunks and streamed to PostgreSQL
    through psycopg3 COPY for efficient bulk insertion.

    Args:
        model: Django model representing the target PostgreSQL table.
        df_input: Polars DataFrame or LazyFrame containing the data.
        exclude_columns: Columns excluded from the INSERT.

    Returns:
        Number of rows inserted.
    """
    data = (
        df_input.collect()
        if isinstance(df_input, pl.LazyFrame)
        else df_input
    )

    excluded = exclude_columns or set()

    validate_model_data(model, data, excluded)

    columns = [
        column
        for column in data.columns
        if column not in excluded
    ]

    if not columns:
        return 0

    table_identifier = sql.Identifier(model._meta.db_table)

    column_identifiers = sql.SQL(", ").join(
        sql.Identifier(column)
        for column in columns
    )

    copy_statement = sql.SQL(
        "COPY {} ({}) FROM STDIN WITH (FORMAT CSV, NULL '')"
    ).format(
        table_identifier,
        column_identifiers,
    )
    chunk_nb = 0
    chunk_count = (data.height + COPY_CHUNK_SIZE - 1) // COPY_CHUNK_SIZE
    row_count = data.height

    with connection.cursor() as django_cursor:
        with django_cursor.cursor.copy(copy_statement) as copy:
            for chunk in data.iter_slices(
                n_rows=COPY_CHUNK_SIZE
            ):
                chunk_nb += 1
                print(
                    f"Loading chunk {chunk_nb}/{chunk_count} "
                    f"into {model._meta.db_table} table.",
                    end="\r",
                )
                buffer = BytesIO()

                chunk.select(columns).write_csv(
                    buffer,
                    include_header=False,
                    null_value="",
                )

                copy.write(buffer.getvalue())

    print(
        f"Loaded {row_count:,} rows into "
        f"{model._meta.db_table} table."
    )

    return row_count


def _update_stop_geography() -> None:
    """Populate the PostGIS point generated from stop coordinates."""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE gtfs_stops
            SET location = ST_SetSRID(
                ST_MakePoint(stop_lon, stop_lat), 4326
            )::geography
            WHERE stop_lat IS NOT NULL AND stop_lon IS NOT NULL
            """
        )


@contextmanager
def _without_stop_time_indexes():
    """Temporarily remove secondary stop-time indexes during bulk loading."""
    index_definitions: list[tuple[str, str]] = []

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT indexes.indexname, indexes.indexdef
            FROM pg_indexes AS indexes
            JOIN pg_class AS index_class
                ON index_class.relname = indexes.indexname
            JOIN pg_namespace AS index_schema
                ON index_schema.oid = index_class.relnamespace
               AND index_schema.nspname = indexes.schemaname
            JOIN pg_index AS index_info
                ON index_info.indexrelid = index_class.oid
               AND NOT index_info.indisunique
            LEFT JOIN pg_constraint AS constraints
                ON constraints.conindid = index_class.oid
            WHERE indexes.schemaname = current_schema()
              AND indexes.tablename = %s
              AND constraints.oid IS NULL
            """,
            [StopTime._meta.db_table],
        )
        index_definitions = cursor.fetchall()

        for index_name, _ in index_definitions:
            cursor.execute(
                sql.SQL("DROP INDEX IF EXISTS {}").format(
                    sql.Identifier(index_name)
                )
            )

    try:
        yield
    finally:
        transaction.on_commit(
            lambda: _recreate_indexes(index_definitions)
        )


def _recreate_indexes(index_definitions: list[tuple[str, str]]) -> None:
    """Recreate indexes after the transaction that loaded their table."""
    with connection.cursor() as cursor:
        for _, index_definition in index_definitions:
            cursor.execute(index_definition)


def load_stops(df_input: pl.DataFrame | pl.LazyFrame) -> int:
    """Load stops and populate their generated geography column."""
    count = load_table(Stop, df_input, exclude_columns={"location"})
    _update_stop_geography()
    return count


@transaction.atomic
def load_gtfs(resources_dir: str | None = None) -> dict[str, int]:
    """Parse GTFS files and replace PostgreSQL source tables atomically."""
    resources_path = (
        Path(resources_dir)
        if resources_dir is not None
        else Path(__file__).resolve().parents[2] / "ressources"
    )
    for model in (Transfer, StopTime, Trip, Stop, Route, CalendarDate, Calendar):
        if model is Stop:
            Stop.objects.update(parent_stop=None)
        model.objects.all().delete()

    stops = parse_stops(resources_path).collect()
    stops_count = load_stops(stops)
    print(f"Parsed {stops_count} stops")

    routes = parse_routes(resources_path)
    routes_count = load_table(Route, routes)
    print(f"Parsed {routes_count} routes")

    trips = parse_trips(resources_path, routes)
    trips_count = load_table(Trip, trips)
    print(f"Parsed {trips_count} trips")

    stop_times = parse_stop_times(resources_path, trips)
    with _without_stop_time_indexes():
        stop_times_count = load_table(StopTime, stop_times)
    print(f"Parsed {stop_times_count} stop times")

    del routes, trips, stop_times

    transfers = parse_transfers(resources_path, stops)
    transfers_count = load_table(Transfer, transfers)
    print(f"Parsed {transfers_count} transfers")
    del transfers

    del stops

    calendar = parse_calendar(resources_path)
    calendar_count = load_table(Calendar, calendar)
    print(f"Parsed {calendar_count} calendar entries")
    del calendar

    calendar_dates = parse_calendar_dates(resources_path)
    calendar_dates_count = load_table(
        CalendarDate, calendar_dates
    )
    print(f"Parsed {calendar_dates_count} calendar date entries")
    del calendar_dates

    counts = {
        "stops": stops_count,
        "routes": routes_count,
        "trips": trips_count,
        "stop_times": stop_times_count,
        "transfers": transfers_count,
        "calendar": calendar_count,
        "calendar_dates": calendar_dates_count,
    }
    transaction.on_commit(_reload_network_data)
    return counts


def _reload_network_data() -> None:
    from apps.network.dataset import reload_gtfs_data

    reload_gtfs_data()

if __name__ == "__main__":
    print("Parsing GTFS files")
    load_gtfs()
    print("GTFS data loaded successfully.")

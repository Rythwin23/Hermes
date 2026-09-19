from __future__ import annotations

from threading import Lock

import polars as pl
from django.db import connection


class GTFSDataStore:
    _instance: GTFSDataStore | None = None
    _lock = Lock()
    _table_queries = {
        "stops": """
            SELECT stop_id, stop_name, location_type, parent_stop_id
            FROM gtfs_stops
            """,
        "routes": """
            SELECT route_id, route_long_name, route_type, route_type_name, route_color
            FROM gtfs_routes
            """,
        "trips": """
            SELECT trip_id, route_id, service_id, trip_headsign, direction_id
            FROM gtfs_trips
            """,
        "stop_times": """
            SELECT trip_id, stop_id, arrival_time, departure_time, stop_sequence
            FROM gtfs_stop_times
            """,
        "transfers": """
            SELECT from_stop_id, to_stop_id, min_transfer_time
            FROM gtfs_transfers
            """,
        "calendars": """
            SELECT service_id, monday, tuesday, wednesday, thursday, friday, saturday, sunday, start_date, end_date
            FROM gtfs_calendar
            """,
        "calendar_dates": """
            SELECT service_id, date, exception_type
            FROM gtfs_calendar_dates
            """,
    }

    def __init__(self) -> None:
        self._tables: dict[str, pl.DataFrame] = {}

    def __getattr__(self, name: str) -> pl.DataFrame:
        if name in self._table_queries:
            if name not in self._tables:
                self._tables[name] = self._load_table(self._table_queries[name])
            return self._tables[name]
        raise AttributeError(f"GTFSDataStore has no attribute '{name}'")

    @staticmethod
    def _load_table(query: str) -> pl.DataFrame:
        with connection.cursor() as cursor:
            cursor.execute(query)
            columns = [column[0] for column in cursor.description]
            rows = cursor.fetchall()

        return pl.DataFrame(rows, schema=columns, orient="row")

    @classmethod
    def get(cls) -> GTFSDataStore:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @classmethod
    def reload(cls) -> GTFSDataStore:
        new_store = cls()
        with cls._lock:
            cls._instance = new_store
        return new_store


def reload_gtfs_data() -> None:
    """Reload the in-memory GTFS snapshot after a successful ingestion."""
    GTFSDataStore.reload()
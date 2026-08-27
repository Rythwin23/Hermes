from __future__ import annotations

from collections.abc import Iterable

import polars as pl
from mongoengine import Document

from apps.network.models import (
    Calendar,
    CalendarDate,
    ParentChildStop,
    Route,
    Stop,
    StopTime,
    Transfer,
    Trip,
)
from apps.ingestion.parser import parse_gtfs


BATCH_SIZE = 5_000


def dataframe_to_documents(
    model: type[Document],
    dataframe: pl.DataFrame,
) -> Iterable[dict]:
    """Convert a Polars DataFrame into MongoEngine documents."""
    for row in dataframe.to_dicts():
        document = model(**row)
        yield document.to_mongo().to_dict()


def replace_collection(
    model: type[Document],
    dataframe: pl.DataFrame,
    batch_size: int = BATCH_SIZE,
) -> int:
    """Replace a MongoDB collection with parsed GTFS data."""
    collection = model._get_collection()
    collection.delete_many({})

    inserted_count = 0
    batch: list[dict] = []

    for document in dataframe_to_documents(model, dataframe):
        batch.append(document)

        if len(batch) >= batch_size:
            collection.insert_many(batch, ordered=False)
            inserted_count += len(batch)
            batch.clear()

    if batch:
        collection.insert_many(batch, ordered=False)
        inserted_count += len(batch)

    model.ensure_indexes()
    return inserted_count


def load_gtfs(
    resources_dir: str | None = None,
    batch_size: int = BATCH_SIZE,
) -> dict[str, int]:
    """Parse GTFS files and replace MongoDB collections."""
    parsed_data = parse_gtfs(resources_dir)

    collections = {
        "stops": (Stop, parsed_data["stops"]),
        "routes": (Route, parsed_data["routes"]),
        "trips": (Trip, parsed_data["trips"]),
        "stop_times": (StopTime, parsed_data["stop_times"]),
        "calendar": (Calendar, parsed_data["calendar"]),
        "calendar_dates": (
            CalendarDate,
            parsed_data["calendar_dates"],
        ),
        "transfers": (Transfer, parsed_data["transfers"]),
        "parent_child_stops": (
            ParentChildStop,
            parsed_data["parent_child_stops"],
        ),
    }

    inserted_counts: dict[str, int] = {}

    for collection_name, (model, dataframe) in collections.items():
        inserted_counts[collection_name] = replace_collection(
            model=model,
            dataframe=dataframe,
            batch_size=batch_size,
        )

    return inserted_counts


if __name__ == "__main__":
    counts = load_gtfs()

    for collection_name, count in counts.items():
        print(f"{collection_name}: {count} documents inserted")
from pathlib import Path

import polars as pl


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


def validate_model_data(
    model,
    data: pl.DataFrame | pl.LazyFrame,
    exclude_columns: set[str] | None = None,
) -> None:
    """Validate source columns before loading them into Django models."""
    excluded = exclude_columns or set()
    columns = (
        data.collect_schema().names()
        if isinstance(data, pl.LazyFrame)
        else data.columns
    )
    model_columns = {
        field.attname for field in model._meta.concrete_fields
        if not field.auto_created and field.attname not in excluded
    }

    data_columns = set(columns)

    missing_columns = sorted(model_columns - data_columns)
    extra_columns = sorted(data_columns - model_columns - excluded)
    if missing_columns or extra_columns:
        details = []
        if missing_columns:
            details.append(f"missing={missing_columns}")
        if extra_columns:
            details.append(f"extra={extra_columns}")
        raise ValueError(
            f"Columns mismatch for {model.__name__}: {', '.join(details)}"
        )

    validation = pl.lit(True)
    for field in model._meta.concrete_fields:
        if field.attname in excluded or field.auto_created:
            continue
        column = pl.col(field.attname)
        if not field.null and not field.has_default():
            validation = validation & column.is_not_null()

    has_invalid_rows = data.select((~validation).any()).item()
    if has_invalid_rows:
        invalid_row = data.filter(~validation).row(0, named=True)
        raise ValueError(
            f"Invalid data for {model.__name__}: "
            f"{invalid_row}"
        )

    del data, validation

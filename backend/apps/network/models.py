from django.contrib.gis.db import models


class Stop(models.Model):
    stop_id = models.CharField(max_length=255, primary_key=True)
    stop_name = models.CharField(max_length=255)
    stop_lat = models.FloatField(null=True, blank=True)
    stop_lon = models.FloatField(null=True, blank=True)
    location = models.PointField(null=True, blank=True, geography=True)
    location_type = models.PositiveSmallIntegerField(null=True, blank=True)
    parent_stop = models.ForeignKey(
        "self",
        db_column="parent_stop_id",
        to_field="stop_id",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="child_stops",
    )

    class Meta:
        db_table = "gtfs_stops"
        indexes = [
            models.Index(fields=["stop_name"]),
            models.Index(fields=["parent_stop"]),
            models.Index(fields=["location_type"]),
        ]


class Route(models.Model):
    route_id = models.CharField(max_length=255, primary_key=True)
    route_short_name = models.CharField(
        max_length=255,
        null=True,
        blank=True,
    )
    route_long_name = models.CharField(max_length=255)
    route_type = models.PositiveSmallIntegerField()
    route_type_name = models.CharField(max_length=32, blank=True)
    route_color = models.CharField(max_length=6, blank=True)

    class Meta:
        db_table = "gtfs_routes"
        indexes = [
            models.Index(fields=["route_long_name"]),
            models.Index(fields=["route_type"]),
        ]


class Trip(models.Model):
    trip_id = models.CharField(max_length=255, primary_key=True)
    route = models.ForeignKey(Route, db_column="route_id", on_delete=models.PROTECT)
    service_id = models.CharField(max_length=255)
    trip_headsign = models.CharField(
        max_length=255,
        null=True,
        blank=True,
    )
    trip_short_name = models.CharField(
        max_length=255,
        null=True,
        blank=True,
    )
    direction_id = models.PositiveSmallIntegerField(null=True, blank=True)

    class Meta:
        db_table = "gtfs_trips"
        indexes = [
            models.Index(fields=["route", "service_id"]),
            models.Index(fields=["service_id"]),
        ]


class StopTime(models.Model):
    trip = models.ForeignKey(Trip, db_column="trip_id", on_delete=models.CASCADE)
    stop = models.ForeignKey(Stop, db_column="stop_id", on_delete=models.PROTECT)
    arrival_time = models.PositiveIntegerField()
    departure_time = models.PositiveIntegerField()
    stop_sequence = models.PositiveIntegerField()

    class Meta:
        db_table = "gtfs_stop_times"
        constraints = [
            models.UniqueConstraint(
                fields=["trip", "stop_sequence"],
                name="gtfs_stop_time_trip_sequence_unique",
            ),
        ]
        indexes = [
            models.Index(fields=["trip", "stop_sequence"]),
            models.Index(fields=["stop", "departure_time"]),
        ]


class Calendar(models.Model):
    service_id = models.CharField(max_length=255, primary_key=True)
    monday = models.BooleanField()
    tuesday = models.BooleanField()
    wednesday = models.BooleanField()
    thursday = models.BooleanField()
    friday = models.BooleanField()
    saturday = models.BooleanField()
    sunday = models.BooleanField()
    start_date = models.DateField()
    end_date = models.DateField()

    class Meta:
        db_table = "gtfs_calendar"


class CalendarDate(models.Model):
    service_id = models.CharField(max_length=255)
    date = models.DateField()
    exception_type = models.PositiveSmallIntegerField()

    class Meta:
        db_table = "gtfs_calendar_dates"
        constraints = [
            models.UniqueConstraint(
                fields=["service_id", "date"],
                name="gtfs_calendar_date_unique",
            ),
        ]
        indexes = [models.Index(fields=["service_id", "date"])]


class Transfer(models.Model):
    from_stop = models.ForeignKey(
        Stop, db_column="from_stop_id", on_delete=models.CASCADE,
        related_name="outgoing_transfers",
    )
    to_stop = models.ForeignKey(
        Stop, db_column="to_stop_id", on_delete=models.CASCADE,
        related_name="incoming_transfers",
    )
    transfer_type = models.PositiveSmallIntegerField()
    min_transfer_time = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "gtfs_transfers"
        constraints = [
            models.UniqueConstraint(
                fields=["from_stop", "to_stop"],
                name="gtfs_transfer_stops_unique",
            ),
        ]
        indexes = [
            models.Index(fields=["from_stop"]),
            models.Index(fields=["to_stop"]),
        ]
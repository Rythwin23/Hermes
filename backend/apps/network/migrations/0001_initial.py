from django.contrib.gis.db import models as gis_models
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Calendar",
            fields=[
                ("service_id", models.CharField(max_length=255, primary_key=True, serialize=False)),
                ("monday", models.BooleanField()),
                ("tuesday", models.BooleanField()),
                ("wednesday", models.BooleanField()),
                ("thursday", models.BooleanField()),
                ("friday", models.BooleanField()),
                ("saturday", models.BooleanField()),
                ("sunday", models.BooleanField()),
                ("start_date", models.DateField()),
                ("end_date", models.DateField()),
            ],
            options={"db_table": "gtfs_calendar"},
        ),
        migrations.CreateModel(
            name="Route",
            fields=[
                ("route_id", models.CharField(max_length=255, primary_key=True, serialize=False)),
                ("route_short_name", models.CharField(blank=True, max_length=255)),
                ("route_long_name", models.CharField(max_length=255)),
                ("route_type", models.PositiveSmallIntegerField()),
                ("route_type_name", models.CharField(blank=True, max_length=32)),
                ("route_color", models.CharField(blank=True, max_length=6)),
            ],
            options={"db_table": "gtfs_routes"},
        ),
        migrations.CreateModel(
            name="Stop",
            fields=[
                ("stop_id", models.CharField(max_length=255, primary_key=True, serialize=False)),
                ("stop_name", models.CharField(max_length=255)),
                ("stop_lat", models.FloatField(blank=True, null=True)),
                ("stop_lon", models.FloatField(blank=True, null=True)),
                ("location", gis_models.PointField(blank=True, geography=True, null=True, srid=4326)),
                ("location_type", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("parent_stop", models.ForeignKey(blank=True, db_column="parent_stop_id", null=True, on_delete=django.db.models.deletion.PROTECT, related_name="child_stops", to="network.stop")),
            ],
            options={"db_table": "gtfs_stops"},
        ),
        migrations.CreateModel(
            name="Trip",
            fields=[
                ("trip_id", models.CharField(max_length=255, primary_key=True, serialize=False)),
                ("service_id", models.CharField(max_length=255)),
                ("trip_headsign", models.CharField(blank=True, max_length=255)),
                ("trip_short_name", models.CharField(blank=True, max_length=255)),
                ("direction_id", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("route", models.ForeignKey(db_column="route_id", on_delete=django.db.models.deletion.PROTECT, to="network.route")),
            ],
            options={"db_table": "gtfs_trips"},
        ),
        migrations.CreateModel(
            name="CalendarDate",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("service_id", models.CharField(max_length=255)),
                ("date", models.DateField()),
                ("exception_type", models.PositiveSmallIntegerField()),
            ],
            options={"db_table": "gtfs_calendar_dates"},
        ),
        migrations.CreateModel(
            name="StopTime",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("arrival_time", models.PositiveIntegerField()),
                ("departure_time", models.PositiveIntegerField()),
                ("stop_sequence", models.PositiveIntegerField()),
                ("stop", models.ForeignKey(db_column="stop_id", on_delete=django.db.models.deletion.PROTECT, to="network.stop")),
                ("trip", models.ForeignKey(db_column="trip_id", on_delete=django.db.models.deletion.CASCADE, to="network.trip")),
            ],
            options={"db_table": "gtfs_stop_times"},
        ),
        migrations.CreateModel(
            name="Transfer",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("transfer_type", models.PositiveSmallIntegerField()),
                ("min_transfer_time", models.PositiveIntegerField(default=0)),
                ("from_stop", models.ForeignKey(db_column="from_stop_id", on_delete=django.db.models.deletion.CASCADE, related_name="outgoing_transfers", to="network.stop")),
                ("to_stop", models.ForeignKey(db_column="to_stop_id", on_delete=django.db.models.deletion.CASCADE, related_name="incoming_transfers", to="network.stop")),
            ],
            options={"db_table": "gtfs_transfers"},
        ),
        migrations.AddIndex(model_name="stop", index=models.Index(fields=["stop_name"], name="gtfs_stops_stop_nam_0a1f32_idx")),
        migrations.AddIndex(model_name="stop", index=models.Index(fields=["parent_stop"], name="gtfs_stops_parent__6dbf91_idx")),
        migrations.AddIndex(model_name="stop", index=models.Index(fields=["location_type"], name="gtfs_stops_locatio_6a05e7_idx")),
        migrations.AddIndex(model_name="route", index=models.Index(fields=["route_long_name"], name="gtfs_routes_route_l_8a71ce_idx")),
        migrations.AddIndex(model_name="route", index=models.Index(fields=["route_type"], name="gtfs_routes_route_t_4f13f5_idx")),
        migrations.AddIndex(model_name="trip", index=models.Index(fields=["route", "service_id"], name="gtfs_trips_route_i_3f3ce4_idx")),
        migrations.AddIndex(model_name="trip", index=models.Index(fields=["service_id"], name="gtfs_trips_service_6f8b54_idx")),
        migrations.AddIndex(model_name="calendardate", index=models.Index(fields=["service_id", "date"], name="gtfs_calenda_servic_8aa0cc_idx")),
        migrations.AddIndex(model_name="stoptime", index=models.Index(fields=["trip", "stop_sequence"], name="gtfs_stop_ti_trip_i_5c0b7a_idx")),
        migrations.AddIndex(model_name="stoptime", index=models.Index(fields=["stop", "departure_time"], name="gtfs_stop_ti_stop_i_9fbb4d_idx")),
        migrations.AddConstraint(model_name="stoptime", constraint=models.UniqueConstraint(fields=("trip", "stop_sequence"), name="gtfs_stop_time_trip_sequence_unique")),
        migrations.AddIndex(model_name="transfer", index=models.Index(fields=["from_stop"], name="gtfs_transf_from_st_9e6db6_idx")),
        migrations.AddIndex(model_name="transfer", index=models.Index(fields=["to_stop"], name="gtfs_transf_to_stop__d8d0d7_idx")),
        migrations.AddConstraint(model_name="transfer", constraint=models.UniqueConstraint(fields=("from_stop", "to_stop"), name="gtfs_transfer_stops_unique")),
        migrations.AddConstraint(model_name="calendardate", constraint=models.UniqueConstraint(fields=("service_id", "date"), name="gtfs_calendar_date_unique")),
    ]

from mongoengine import BooleanField, Document, IntField, StringField, FloatField, ListField, DateTimeField

# Représente une station, par exemple la station Auber.

class Stop(Document):
    stop_id = StringField(primary_key=True)
    stop_name = StringField(required=True)
    stop_lat = FloatField()
    stop_lon = FloatField()
    location_type = IntField(choices=[0, 1, 2, 3, 4])
    parent_stop_id = StringField(null=True)
    parent_stop_name = StringField(null=True)

    meta = {
        "collection": "stops",
        "indexes": [
            "stop_name",
            "parent_stop_id",
            "location_type",
        ],
    }


# Représente les parents station qui regroupent plusieurs sous stations.
class ParentChildStop(Document):
    stop_id = StringField(primary_key=True)
    stop_name = StringField(required=True)
    child_stop_ids = ListField(StringField())
    child_stop_names = ListField(StringField())

    meta = {
        "collection": "parent_child_stops",
    }

# Représente une ligne de transport
class Route(Document):
	route_id = StringField(primary_key=True)
	route_short_name = StringField()
	route_long_name = StringField(required=True)
	route_type = IntField(required=True, choices=[0,1,2,3,4,5,7])
	route_type_name = StringField()
	route_color = StringField()
	
	meta = {"collection": "routes"}


# Représente un trajet planifié d'une ligne.
class Trip(Document):
	trip_id = StringField(primary_key=True)
	route_id = StringField(required=True)
	service_id = StringField(required=True)
	trip_headsign = StringField(null=True)
	trip_short_name = StringField(null=True)
	direction_id = IntField(null=True, choices=[0,1])

	meta = {
        "collection": "trips",
        "indexes": [
            "route_id",
            "service_id",
            ("route_id", "service_id"),
        ],
    }


# Représente l'horaire d'un trajet à un arrêt précis.
class StopTime(Document):
	trip_id = StringField(primary_key=True)
	stop_id = StringField(required=True)
	arrival_time = IntField(required=True)  # second from minuit (gère > 86400)
	departure_time = IntField(required=True)  
	stop_sequence = IntField(unique=True, required=True)

	meta = {
        "collection": "stop_times",
        "indexes": [
            "trip_id",
            "stop_id",
            ("trip_id", "stop_sequence"),
            ("stop_id", "departure_time"),
        ],
    }


class Calendar(Document):
    service_id = StringField(primary_key=True)
    monday = BooleanField(required=True)
    tuesday = BooleanField(required=True)
    wednesday = BooleanField(required=True)
    thursday = BooleanField(required=True)
    friday = BooleanField(required=True)
    saturday = BooleanField(required=True)
    sunday = BooleanField(required=True)
    start_date = StringField(required=True)  # format YYYYMMDD
    end_date = StringField(required=True)    # format YYYYMMDD

    meta = {
        "collection": "calendar_dates",
        "indexes": [
            "service_id",
            ("service_id", "date"),
        ],
    }


class CalendarDate(Document):
    service_id = StringField(required=True)
    date = StringField(required=True)           # format YYYYMMDD
    exception_type = IntField(required=True, choices=[1, 2])  # 1=ajout, 2=suppression

    meta = {
        "collection": "calendar_dates",
        "indexes": ["service_id", "date"],
    }


class Transfer(Document):
    from_stop_id = StringField(required=True)
    to_stop_id = StringField(required=True)
    transfer_type = IntField(required=True, choices=[0, 1, 2, 3])
    min_transfer_time = IntField(default=0)  # en secondes

    meta = {
        "collection": "transfers",
        "indexes": [
            "from_stop_id",
            "to_stop_id",
            ("from_stop_id", "to_stop_id"),
        ],
    }


# Collection dérivée — pré-calculée après ingestion pour accélérer l'API
class ParentStopRoutes(Document):
    parent_stop_id = StringField(primary_key=True)
    parent_stop_name = StringField(required=True)
    stop_lat = FloatField()
    stop_lon = FloatField()
    route_names = ListField(StringField())       # noms des lignes ex: ["1", "A", "B"]
    routes_ids = ListField(StringField())   # route_id ex: ["IDFM:C01371", ...]

    meta = {
        "collection": "parent_stop_routes",
        "indexes": ["parent_stop_id"]
    }


# Sequence canonique des arrêts d'une ligne (dédupliquée, ordonnée)
# Evite de recalculer routes → trips → stop_times → stops à chaque requête API
class RouteStopSequence(Document):
    route_id = StringField(primary_key=True)
    route_short_name = StringField(required=True)
    route_long_name = StringField(required=True)
    direction_0 = ListField(StringField())  # stop_ids direction aller
    direction_1 = ListField(StringField())  # stop_ids direction retour

    meta = {
        "collection": "route_stop_sequences",
        "indexes": ["route_id", ]
    }
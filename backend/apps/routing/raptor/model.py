"""Static timetable structures and the round-based RAPTOR algorithm.

`RaptorModelBuilder` turns the GTFS RAM snapshot (`GTFSDataStore`) into
date-independent structures grouped by "pattern" (trips sharing the same
ordered stop sequence, since a single GTFS route can have several branches).
`RaptorModel` filters those patterns to the trips active on a given service
date and runs the RAPTOR rounds to find the earliest arrival journey.
"""

from __future__ import annotations

import bisect
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from threading import Lock

import polars as pl

from apps.network.dataset import GTFSDataStore

INF = float("inf")
_WEEKDAYS = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)


@dataclass(frozen=True)
class PatternTrip:
    trip_id: str
    arrivals: tuple[int, ...]  # arrival_time per stop index of the pattern
    departures: tuple[int, ...]  # departure_time per stop index of the pattern


@dataclass(frozen=True)
class Pattern:
    pattern_id: int
    stop_ids: tuple[str, ...]
    trips: tuple[PatternTrip, ...]  # sorted by departures[0]


@dataclass(frozen=True)
class RideStop:
    """A stop served while riding a trip leg, with its own schedule."""

    stop_id: str
    arrival_time: int
    departure_time: int


@dataclass(frozen=True)
class Leg:
    """One boarded trip, or a foot transfer when trip_id is None."""

    from_stop: str
    to_stop: str
    departure_time: int | None
    arrival_time: int | None
    trip_id: str | None
    stops: tuple[RideStop, ...] = ()  # boarding to alighting inclusive, trip legs only


@dataclass(frozen=True)
class Journey:
    arrival_time: int
    legs: tuple[Leg, ...]

    @property
    def transfer_count(self) -> int:
        boarded_trips = sum(1 for leg in self.legs if leg.trip_id is not None)
        return max(boarded_trips - 1, 0)


class RaptorModelBuilder:
    """Builds the static, date-independent timetable used by RAPTOR."""

    def __init__(self, data: GTFSDataStore | None = None) -> None:
        self._data = data or GTFSDataStore.get()

    def build(self) -> RaptorModel:
        patterns = self._build_patterns()
        patterns_at_stop = self._build_patterns_at_stop(patterns)
        transfers_by_stop = self._build_transfers()
        trip_service = dict(
            zip(
                self._data.trips["trip_id"].to_list(),
                self._data.trips["service_id"].to_list(),
            )
        )
        return RaptorModel(
            patterns=patterns,
            patterns_at_stop=patterns_at_stop,
            transfers_by_stop=transfers_by_stop,
            trip_service=trip_service,
            calendars=self._data.calendars,
            calendar_dates=self._data.calendar_dates,
        )

    def _build_patterns(self) -> list[Pattern]:
        stop_times = self._data.stop_times.sort(["trip_id", "stop_sequence"])

        rows_by_trip: dict[str, list[tuple[str, int, int]]] = defaultdict(list)
        for trip_id, stop_id, arrival, departure in zip(
            stop_times["trip_id"].to_list(),
            stop_times["stop_id"].to_list(),
            stop_times["arrival_time"].to_list(),
            stop_times["departure_time"].to_list(),
        ):
            rows_by_trip[trip_id].append((stop_id, arrival, departure))

        trips_by_stop_sequence: dict[tuple[str, ...], list[PatternTrip]] = defaultdict(list)
        for trip_id, rows in rows_by_trip.items():
            stop_sequence = tuple(row[0] for row in rows)
            trips_by_stop_sequence[stop_sequence].append(
                PatternTrip(
                    trip_id=trip_id,
                    arrivals=tuple(row[1] for row in rows),
                    departures=tuple(row[2] for row in rows),
                )
            )

        patterns = []
        for pattern_id, (stop_sequence, trips) in enumerate(trips_by_stop_sequence.items()):
            trips.sort(key=lambda trip: trip.departures[0])
            patterns.append(Pattern(pattern_id, stop_sequence, tuple(trips)))
        return patterns

    @staticmethod
    def _build_patterns_at_stop(patterns: list[Pattern]) -> dict[str, list[tuple[int, int]]]:
        patterns_at_stop: dict[str, list[tuple[int, int]]] = defaultdict(list)
        for pattern in patterns:
            for stop_index, stop_id in enumerate(pattern.stop_ids):
                patterns_at_stop[stop_id].append((pattern.pattern_id, stop_index))
        return patterns_at_stop

    def _build_transfers(self) -> dict[str, list[tuple[str, int]]]:
        transfers = self._data.transfers
        transfers_by_stop: dict[str, list[tuple[str, int]]] = defaultdict(list)
        for from_stop, to_stop, min_time in zip(
            transfers["from_stop_id"].to_list(),
            transfers["to_stop_id"].to_list(),
            transfers["min_transfer_time"].to_list(),
        ):
            transfers_by_stop[from_stop].append((to_stop, min_time or 0))

        # Implicit free transfer between a station and each of its child platforms (both ways),
        # so a name resolved to the parent station can board from any of its platforms.
        for stop_id, parent_id in zip(
            self._data.stops["stop_id"].to_list(),
            self._data.stops["parent_stop_id"].to_list(),
        ):
            if parent_id:
                transfers_by_stop[parent_id].append((stop_id, 0))
                transfers_by_stop[stop_id].append((parent_id, 0))
        return transfers_by_stop


class RaptorModel:
    """Static timetable plus the RAPTOR round-based search."""

    _instance: RaptorModel | None = None
    _lock = Lock()

    def __init__(
        self,
        patterns: list[Pattern],
        patterns_at_stop: dict[str, list[tuple[int, int]]],
        transfers_by_stop: dict[str, list[tuple[str, int]]],
        trip_service: dict[str, str],
        calendars: pl.DataFrame,
        calendar_dates: pl.DataFrame,
    ) -> None:
        self.patterns = patterns
        self.patterns_at_stop = patterns_at_stop
        self.transfers_by_stop = transfers_by_stop
        self.trip_service = trip_service
        self._calendars = calendars
        self._calendar_dates = calendar_dates
        self._trip_lookup: dict[str, PatternTrip] = {}
        self._trip_pattern_stops: dict[str, tuple[str, ...]] = {}
        for pattern in patterns:
            for trip in pattern.trips:
                self._trip_lookup[trip.trip_id] = trip
                self._trip_pattern_stops[trip.trip_id] = pattern.stop_ids

    @classmethod
    def get(cls) -> RaptorModel:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = RaptorModelBuilder().build()
        return cls._instance

    @classmethod
    def reload(cls) -> RaptorModel:
        new_model = RaptorModelBuilder().build()
        with cls._lock:
            cls._instance = new_model
        return new_model

    def _active_service_ids(self, travel_date: date) -> set[str]:
        weekday_column = _WEEKDAYS[travel_date.weekday()]
        base_services = self._calendars.filter(
            pl.col(weekday_column)
            & (pl.col("start_date") <= travel_date)
            & (pl.col("end_date") >= travel_date)
        )["service_id"].to_list()
        active_services = set(base_services)

        exceptions = self._calendar_dates.filter(pl.col("date") == travel_date)
        for service_id, exception_type in zip(
            exceptions["service_id"].to_list(),
            exceptions["exception_type"].to_list(),
        ):
            if exception_type == 1:
                active_services.add(service_id)
            elif exception_type == 2:
                active_services.discard(service_id)
        return active_services

    def _active_trip_ids(self, travel_date: date) -> set[str]:
        active_services = self._active_service_ids(travel_date)
        return {
            trip_id
            for trip_id, service_id in self.trip_service.items()
            if service_id in active_services
        }

    def run(
        self,
        origin_stop_id: str,
        destination_stop_id: str,
        departure_time: int,
        travel_date: date,
        max_transfers: int = 5,
        max_results: int = 5,
    ) -> list[Journey]:
        """Return up to `max_results` journeys, fastest first, using at most `max_transfers` correspondances."""
        active_trip_ids = self._active_trip_ids(travel_date)
        # Cache per-pattern filtered/sorted trips and their departure columns, reused across rounds.
        pattern_trips_cache: dict[int, list[PatternTrip]] = {}
        departures_cache: dict[int, list[list[int]]] = {}

        best_arrival: dict[str, float] = defaultdict(lambda: INF)
        best_arrival[origin_stop_id] = departure_time
        parents: dict[str, tuple] = {}
        prev_round_arrival: dict[str, float] = {origin_stop_id: departure_time}
        marked_stops = {origin_stop_id}

        # One journey per number of correspondances actually used, in increasing order
        # (arrival time only improves as more rounds/correspondances are allowed).
        journeys: list[Journey] = []

        def snapshot_destination() -> None:
            if destination_stop_id not in marked_stops:
                return
            arrival = best_arrival[destination_stop_id]
            if arrival < INF and (not journeys or arrival < journeys[-1].arrival_time):
                journeys.append(
                    Journey(
                        arrival_time=int(arrival),
                        legs=tuple(self._reconstruct_legs(destination_stop_id, parents)),
                    )
                )

        # A parent station has no stop_times of its own; reach its platforms once, up front.
        for to_stop_id, min_transfer_time in self.transfers_by_stop.get(origin_stop_id, []):
            arrival = departure_time + min_transfer_time
            if arrival < best_arrival[to_stop_id]:
                best_arrival[to_stop_id] = arrival
                prev_round_arrival[to_stop_id] = arrival
                parents[to_stop_id] = ("transfer", origin_stop_id, to_stop_id)
                marked_stops.add(to_stop_id)
        snapshot_destination()

        for _ in range(max_transfers + 1):
            if not marked_stops:
                break

            queue: dict[int, int] = {}
            for stop_id in marked_stops:
                for pattern_id, stop_index in self.patterns_at_stop.get(stop_id, []):
                    if pattern_id not in queue or stop_index < queue[pattern_id]:
                        queue[pattern_id] = stop_index

            round_arrival = dict(prev_round_arrival)
            next_marked: set[str] = set()

            for pattern_id, start_index in queue.items():
                pattern = self.patterns[pattern_id]
                trips = pattern_trips_cache.get(pattern_id)
                if trips is None:
                    trips = [trip for trip in pattern.trips if trip.trip_id in active_trip_ids]
                    pattern_trips_cache[pattern_id] = trips
                    departures_cache[pattern_id] = [
                        [trip.departures[i] for trip in trips] for i in range(len(pattern.stop_ids))
                    ]
                if not trips:
                    continue
                departures_by_index = departures_cache[pattern_id]

                boarded_trip_index: int | None = None
                boarded_at_index: int | None = None

                for stop_index in range(start_index, len(pattern.stop_ids)):
                    stop_id = pattern.stop_ids[stop_index]

                    if boarded_trip_index is not None:
                        trip = trips[boarded_trip_index]
                        arrival = trip.arrivals[stop_index]
                        if arrival < best_arrival[stop_id] and arrival < round_arrival.get(stop_id, INF):
                            round_arrival[stop_id] = arrival
                            best_arrival[stop_id] = arrival
                            parents[stop_id] = (
                                "trip",
                                trip.trip_id,
                                pattern.stop_ids[boarded_at_index],
                                boarded_at_index,
                                stop_index,
                            )
                            next_marked.add(stop_id)

                    # Board the earliest trip we can still catch given last round's arrival here.
                    earliest_reach = prev_round_arrival.get(stop_id, INF)
                    if earliest_reach < INF:
                        candidate_index = bisect.bisect_left(
                            departures_by_index[stop_index], earliest_reach
                        )
                        if candidate_index < len(trips) and (
                            boarded_trip_index is None or candidate_index < boarded_trip_index
                        ):
                            boarded_trip_index = candidate_index
                            boarded_at_index = stop_index

            for stop_id in list(next_marked):
                arrival_here = round_arrival[stop_id]
                for to_stop_id, min_transfer_time in self.transfers_by_stop.get(stop_id, []):
                    arrival = arrival_here + min_transfer_time
                    if arrival < best_arrival[to_stop_id]:
                        best_arrival[to_stop_id] = arrival
                        round_arrival[to_stop_id] = arrival
                        parents[to_stop_id] = ("transfer", stop_id, to_stop_id)
                        next_marked.add(to_stop_id)

            prev_round_arrival = round_arrival
            marked_stops = next_marked
            snapshot_destination()

        journeys.sort(key=lambda journey: journey.arrival_time)
        return journeys[:max_results]

    def _reconstruct_legs(self, destination_stop_id: str, parents: dict[str, tuple]) -> list[Leg]:
        legs: list[Leg] = []
        stop_id = destination_stop_id
        while stop_id in parents:
            entry = parents[stop_id]
            if entry[0] == "trip":
                _, trip_id, from_stop, boarded_at_index, arrival_index = entry
                trip = self._trip_lookup[trip_id]
                stop_sequence = self._trip_pattern_stops[trip_id]
                ride_stops = tuple(
                    RideStop(stop_sequence[i], trip.arrivals[i], trip.departures[i])
                    for i in range(boarded_at_index, arrival_index + 1)
                )
                legs.append(
                    Leg(
                        from_stop=from_stop,
                        to_stop=stop_id,
                        departure_time=trip.departures[boarded_at_index],
                        arrival_time=trip.arrivals[arrival_index],
                        trip_id=trip_id,
                        stops=ride_stops,
                    )
                )
                stop_id = from_stop
            else:
                _, from_stop, to_stop = entry
                legs.append(
                    Leg(
                        from_stop=from_stop,
                        to_stop=to_stop,
                        departure_time=None,
                        arrival_time=None,
                        trip_id=None,
                    )
                )
                stop_id = from_stop
        legs.reverse()
        return legs

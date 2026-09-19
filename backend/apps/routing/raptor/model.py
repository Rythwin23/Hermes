"""RAPTOR routing engine: simple, fast and functional.

Version multicritère (McRAPTOR) : un seul bag de labels Pareto-optimaux
par arrêt (pas par round). Critères comparés : heure d'arrivée, nombre
de correspondances physiques (changements de trip_id réels, pas de
segments de route), temps de marche cumulé. Le round ne sert plus qu'à
borner l'exploration (nombre max de correspondances autorisées).
"""

from __future__ import annotations

import bisect
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
import logging
import polars as pl

from apps.network.dataset import GTFSDataStore

logger = logging.getLogger(__name__)

INF = float("inf")
MIN_TRANSFER_SECONDS = 60
MAX_LABELS_PER_STOP = 5  # borne le coût mémoire/temps du front de Pareto par arrêt
WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


@dataclass
class Timetable:
    """Structure mémoire plate et optimisée pour RAPTOR."""
    stops: list[str]                         # index int -> stop_id
    stop_to_idx: dict[str, int]              # stop_id -> index int
    routes_stops: list[list[int]]            # [route_idx] -> liste de stop_idx
    routes_trips: list[list[dict]]           # [route_idx] -> [{trip_id, service_id, dep, arr}]
    routes_at_stop: list[list[tuple[int, int]]] # [stop_idx] -> [(route_idx, stop_pos)]
    transfers: list[list[tuple[int, int]]]   # [stop_idx] -> [(target_stop_idx, duration)]


@dataclass(frozen=True)
class JourneyLeg:
    trip_id: str | None  # None = marche
    from_stop: str
    to_stop: str
    departure_time: int
    arrival_time: int


@dataclass(frozen=True)
class Journey:
    departure_time: int
    arrival_time: int
    duration_minutes: int
    walk_seconds: int
    transfers: int
    legs: list[JourneyLeg]


@dataclass(frozen=True)
class Label:
    """État Pareto-optimal à un arrêt donné.

    parent référence directement le Label précédent dans la chaîne :
    la reconstruction du trajet suit cette chaîne sans avoir à
    rechercher/deviner quel label antérieur correspond.

    transfers compte les correspondances PHYSIQUES : un changement de
    trip_id, pas un changement de segment de route GTFS. Rester sur le
    même trip_id d'un segment au suivant (trips consécutifs d'un même
    service découpés en tronçons) n'incrémente pas ce compteur.

    visited_stops est un cache du chemin parcouru pour éviter de remonter
    toute la chaîne parent à chaque contrôle de redondance.
    """
    arrival: int
    walk_seconds: int
    transfers: int
    stop_idx: int
    trip_id: str | None        # None si ce label vient d'un leg à pied ou est l'origine
    route_idx: int | None      # index de route (pattern) emprunté pour atteindre ce label
    from_stop: int | None      # stop_idx de départ du leg (None si origine)
    departure_time: int | None # heure de départ du leg (None si origine)
    parent: "Label | None"     # label précédent dans la chaîne (None si origine)
    visited_stops: frozenset[int] = frozenset()


# =====================================================================
# Détection de trajectoire redondante — isolée du Pareto multicritère
# =====================================================================

def visits_stop(label: Label, stop_idx: int) -> bool:
    """Vérifie rapidement si un arrêt a déjà été traversé sur ce chemin.

    Le cache `visited_stops` évite la remontée coûteuse dans `parent`,
    sans changer la sémantique du test de redondance utilisée pour
    éliminer les trajets rétrogrades sur un même service GTFS.
    """
    return stop_idx in label.visited_stops


# =====================================================================
# Dominance Pareto — isolée pour ajuster facilement les critères
# =====================================================================

def dominates(a: Label, b: Label) -> bool:
    """Vrai si le label a domine le label b : au moins aussi bon sur
    tous les critères, strictement meilleur sur au moins un.

    Pour ajouter un critère, ajouter la comparaison ici uniquement —
    add_label() n'a pas à changer.
    """
    at_least_as_good = (
        a.arrival <= b.arrival
        and a.transfers <= b.transfers
        and a.walk_seconds <= b.walk_seconds
    )
    strictly_better = (
        a.arrival < b.arrival
        or a.transfers < b.transfers
        or a.walk_seconds < b.walk_seconds
    )
    return at_least_as_good and strictly_better


def same_label(a: Label, b: Label) -> bool:
    """Vrai si deux labels décrivent exactement la même solution semantique.

    On ignore `parent` et `visited_stops` car ce sont des détails
    d'implémentation du chemin ; le candidat reste identique si son
    état final et sa trajectoire embarquée sont les mêmes.
    """
    return (
        a.arrival == b.arrival
        and a.walk_seconds == b.walk_seconds
        and a.transfers == b.transfers
        and a.stop_idx == b.stop_idx
        and a.trip_id == b.trip_id
        and a.route_idx == b.route_idx
        and a.from_stop == b.from_stop
        and a.departure_time == b.departure_time
    )


def add_label(bag: list[Label], candidate: Label, max_size: int = MAX_LABELS_PER_STOP) -> bool:
    """Insère candidate dans bag en maintenant le front de Pareto.

    Retourne True si candidate a été retenu (l'arrêt doit alors être
    marqué pour exploration au round suivant). Retire de bag tout label
    dominé par candidate ; rejette candidate s'il est lui-même dominé.
    Si bag dépasse max_size, garde les labels arrivant le plus tôt.
    """
    for existing in bag:
        if same_label(existing, candidate):
            return False
        if dominates(existing, candidate):
            return False

    bag[:] = [existing for existing in bag if not dominates(candidate, existing)]
    bag.append(candidate)

    if len(bag) > max_size:
        bag.sort(key=lambda label: label.arrival)
        del bag[max_size:]

    return True


# =====================================================================
# 1. PRÉTRAITEMENT GTFS (exécuté 1 seule fois au démarrage)
# =====================================================================

_timetable: Timetable | None = None

def get_timetable() -> Timetable:
    global _timetable
    if _timetable is None:
        _timetable = build_timetable()
    return _timetable


def reload_timetable() -> None:
    global _timetable
    _timetable = build_timetable()

def build_timetable() -> Timetable:
    """Transforme les DataFrames GTFS bruts en tableaux RAPTOR indexés par entiers."""

    data = GTFSDataStore.get()
    stops_df = data.stops
    stop_times_df = data.stop_times
    trips_df = data.trips
    transfers_df = data.transfers

    # 1. Mapping continu des arrêts : stop_id -> int
    all_stop_ids = sorted(stops_df["stop_id"].unique().to_list())
    stop_to_idx = {sid: i for i, sid in enumerate(all_stop_ids)}
    n_stops = len(all_stop_ids)

    # 2. Joindre trips et stop_times pour avoir le service_id
    st = stop_times_df.join(trips_df.select(["trip_id", "service_id"]), on="trip_id")
    st = st.sort(["trip_id", "stop_sequence"])

    # 3. Agrégation Polars (rapide en RAM et vectorisée en Rust)
    grouped = st.group_by("trip_id", maintain_order=True).agg([
        pl.col("service_id").first(),
        pl.col("stop_id"),
        pl.col("arrival_time"),
        pl.col("departure_time"),
    ])

    # 4. Regroupement par "Pattern" (séquence unique d'arrêts)
    pattern_trips = defaultdict(list)
    for row in grouped.iter_rows(named=True):
        stop_seq = tuple(stop_to_idx[sid] for sid in row["stop_id"])
        pattern_trips[stop_seq].append({
            "trip_id": row["trip_id"],
            "service_id": row["service_id"],
            "dep": row["departure_time"],
            "arr": row["arrival_time"],
        })

    routes_stops: list[list[int]] = []
    routes_trips: list[list[dict]] = []
    routes_at_stop: list[list[tuple[int, int]]] = [[] for _ in range(n_stops)]

    for r_idx, (stop_seq, trips) in enumerate(pattern_trips.items()):
        # Tri des trips par heure de départ au premier arrêt
        trips.sort(key=lambda t: t["dep"][0])
        routes_stops.append(list(stop_seq))
        routes_trips.append(trips)
        for pos, s_idx in enumerate(stop_seq):
            routes_at_stop[s_idx].append((r_idx, pos))

    # 5. Correspondances & liaisons parent_station
    transfers: list[list[tuple[int, int]]] = [[] for _ in range(n_stops)]
    if transfers_df is not None:
        for r in transfers_df.iter_rows(named=True):
            if r["from_stop_id"] in stop_to_idx and r["to_stop_id"] in stop_to_idx:
                u, v = stop_to_idx[r["from_stop_id"]], stop_to_idx[r["to_stop_id"]]
                transfers[u].append((v, r.get("min_transfer_time") or 0))

    if "parent_stop_id" in stops_df.columns:
        for r in stops_df.iter_rows(named=True):
            p = r["parent_stop_id"]
            if p and p in stop_to_idx and r["stop_id"] in stop_to_idx:
                u, v = stop_to_idx[r["stop_id"]], stop_to_idx[p]
                transfers[u].append((v, 0))
                transfers[v].append((u, 0))

    return Timetable(
        stops=all_stop_ids,
        stop_to_idx=stop_to_idx,
        routes_stops=routes_stops,
        routes_trips=routes_trips,
        routes_at_stop=routes_at_stop,
        transfers=transfers,
    )


# =====================================================================
# 2. FILTRAGE CALENDRIER (rapide, fait à la requête)
# =====================================================================

def get_active_services(travel_date: date) -> set[str]:
    data = GTFSDataStore.get()
    calendars_df = data.calendars
    calendar_dates_df = data.calendar_dates
    col = WEEKDAYS[travel_date.weekday()]
    base = calendars_df.filter(
        pl.col(col) & (pl.col("start_date") <= travel_date) & (pl.col("end_date") >= travel_date)
    )["service_id"].to_list()
    active = set(base)

    exceptions = calendar_dates_df.filter(pl.col("date") == travel_date)
    for row in exceptions.iter_rows(named=True):
        if row["exception_type"] == 1:
            active.add(row["service_id"])
        elif row["exception_type"] == 2:
            active.discard(row["service_id"])
    return active


# =====================================================================
# 3. L'ALGORITHME McRAPTOR
# =====================================================================

def raptor_search(
    origin_id: str,
    dest_id: str,
    dep_time: int,
    active_services: set[str],
    max_rounds: int,
    max_results: int,
) -> list[Journey]:
    """Recherche multicritère : renvoie tous les trajets Pareto-optimaux
    (arbitrage arrivée / correspondances physiques / marche à pied),
    triés par heure d'arrivée croissante, jusqu'à max_results.

    Le round k borne uniquement le nombre de tours d'exploration RAPTOR
    (donc un plafond sur les correspondances possibles) ; les bags sont
    indexés par arrêt seul, pas par (round, arrêt), pour que Pareto
    compare des labels de "profondeur" d'exploration différente — ce qui
    élimine les faux changements créés par des trips GTFS découpés en
    plusieurs tronçons consécutifs d'un même service.
    """
    tt = get_timetable()
    if origin_id not in tt.stop_to_idx or dest_id not in tt.stop_to_idx:
        logger.warning("Origin or destination stop not found in the timetable.")
        return []

    src = tt.stop_to_idx[origin_id]
    dst = tt.stop_to_idx[dest_id]
    n_stops = len(tt.stops)

    # bags[stop] : liste de Label Pareto-optimaux, tous rounds confondus
    bags: list[list[Label]] = [[] for _ in range(n_stops)]

    origin_label = Label(
        arrival=dep_time,
        walk_seconds=0,
        transfers=0,
        stop_idx=src,
        trip_id=None,
        route_idx=None,
        from_stop=None,
        departure_time=None,
        parent=None,
        visited_stops=frozenset({src}),
    )
    bags[src] = [origin_label]
    marked = {src}

    # Transferts initiaux à pied depuis le départ
    for neighbor, duration in tt.transfers[src]:
        arr = dep_time + duration
        candidate = Label(
            arrival=arr,
            walk_seconds=duration,
            transfers=0,
            stop_idx=neighbor,
            trip_id=None,
            route_idx=None,
            from_stop=src,
            departure_time=dep_time,
            parent=origin_label,
            visited_stops=frozenset({src, neighbor}),
        )
        if add_label(bags[neighbor], candidate):
            marked.add(neighbor)

    route_active_trips = {
        r_idx: [trip for trip in tt.routes_trips[r_idx] if trip["service_id"] in active_services]
        for r_idx in range(len(tt.routes_trips))
    }

    for _round in range(1, max_rounds + 1):
        if not marked:
            break

        # A. Accumulation des routes à explorer, avec les labels marqués
        # présents à chaque arrêt (pas juste la position la plus en amont).
        routes_to_scan: dict[int, list[tuple[int, Label]]] = defaultdict(list)
        for s in marked:
            for r_idx, pos in tt.routes_at_stop[s]:
                for label in bags[s]:
                    routes_to_scan[r_idx].append((pos, label))

        marked.clear()
        newly_marked: set[int] = set()

        # B. Parcours des routes
        for r_idx, entries in routes_to_scan.items():
            stops = tt.routes_stops[r_idx]
            trips = route_active_trips.get(r_idx)
            if not trips:
                continue

            # Un embarquement possible par label marqué présent sur la route,
            # trié par position pour parcourir le pattern dans l'ordre.
            pending_boardings = sorted(entries, key=lambda e: e[0])
            start_pos = pending_boardings[0][0]

            # boardings : embarquements actifs, liste de (trip, board_pos, boarding_label)
            boardings: list[tuple[dict, int, Label]] = []
            boarding_idx = 0

            for pos in range(start_pos, len(stops)):
                s = stops[pos]

                # 1. Évaluer l'arrivée pour chaque embarquement actif
                for trip, board_pos, boarding_label in boardings:
                    arr = trip["arr"][pos]
                    # Correspondance physique seulement si on change de trip_id
                    # par rapport au dernier leg en trajet (pas de marche) du label.
                    is_new_transfer = (
                        boarding_label.trip_id is not None
                        and boarding_label.trip_id != trip["trip_id"]
                    )
                    candidate = Label(
                        arrival=arr,
                        walk_seconds=boarding_label.walk_seconds,
                        transfers=boarding_label.transfers + (1 if is_new_transfer else 0),
                        stop_idx=s,
                        trip_id=trip["trip_id"],
                        route_idx=r_idx,
                        from_stop=stops[board_pos],
                        departure_time=trip["dep"][board_pos],
                        parent=boarding_label,
                        visited_stops=boarding_label.visited_stops | {s},
                    )
                    if add_label(bags[s], candidate):
                        newly_marked.add(s)

                # 2. Chercher un embarquement pour chaque label marqué à cette position
                while boarding_idx < len(pending_boardings) and pending_boardings[boarding_idx][0] == pos:
                    _, prev_label = pending_boardings[boarding_idx]
                    boarding_idx += 1

                    boarding_time = prev_label.arrival
                    if prev_label.trip_id is not None:
                        # Un vrai changement de véhicule impose un délai minimal ;
                        # rester sur le même trip_id (tronçon suivant) n'en a pas besoin.
                        boarding_time += MIN_TRANSFER_SECONDS
                    deps = [t["dep"][pos] for t in trips]
                    idx = bisect.bisect_left(deps, boarding_time)
                    if idx < len(trips):
                        candidate_trip = trips[idx]
                        already_boarded = any(
                            t is candidate_trip and b.walk_seconds <= prev_label.walk_seconds
                            and b.transfers <= prev_label.transfers
                            for t, _, b in boardings
                        )
                        # Rejette un embarquement dont le trajet repasserait par
                        # des arrêts déjà traversés par prev_label : signe d'une
                        # trajectoire redondante (même service GTFS découpé en
                        # plusieurs trip_id consécutifs), pas d'une vraie correspondance.
                        stop_seq = tt.routes_stops[r_idx]
                        retraces_path = any(
                            stop_idx in prev_label.visited_stops
                            for stop_idx in stop_seq[pos + 1:]
                        )
                        # Rejette un ré-embarquement sur la MÊME route (r_idx)
                        # que celle dont prev_label vient justement de descendre
                        # à cet arrêt : descendre puis remonter sur un passage
                        # suivant de la même ligne n'est jamais utile, rester à
                        # bord du premier passage est toujours au moins aussi
                        # bon (même trajet restant, zéro correspondance en plus).
                        same_route_reboarding = (
                            prev_label.route_idx == r_idx
                            and prev_label.stop_idx == s
                        )
                        if not already_boarded and not retraces_path and not same_route_reboarding:
                            boardings.append((candidate_trip, pos, prev_label))

        # C. Transferts à pied, à partir des labels nouvellement ajoutés ce round
        for s in list(newly_marked):
            for label in list(bags[s]):
                for neighbor, duration in tt.transfers[s]:
                    arr_neighbor = label.arrival + duration
                    walk_neighbor = label.walk_seconds + duration
                    candidate = Label(
                        arrival=arr_neighbor,
                        walk_seconds=walk_neighbor,
                        transfers=label.transfers,
                        stop_idx=neighbor,
                        trip_id=None,
                        route_idx=None,
                        from_stop=s,
                        departure_time=label.arrival,
                        parent=label,
                        visited_stops=label.visited_stops | {neighbor},
                    )
                    if add_label(bags[neighbor], candidate):
                        newly_marked.add(neighbor)

        marked = newly_marked

    # 4. Reconstruction de tous les trajets Pareto-optimaux à destination
    all_dest_labels = bags[dst]

    if not all_dest_labels:
        logger.warning("No route found from %s to %s", src, dst)
        return []

    journeys: list[Journey] = []

    for label in all_dest_labels:
        legs: list[JourneyLeg] = []
        cursor = label

        while cursor.parent is not None:
            legs.append(JourneyLeg(
                trip_id=cursor.trip_id,
                from_stop=tt.stops[cursor.from_stop],
                to_stop=tt.stops[cursor.stop_idx],
                departure_time=cursor.departure_time,
                arrival_time=cursor.arrival,
            ))
            cursor = cursor.parent

        if not legs:
            continue

        legs.reverse()
        depart_time = next((leg.departure_time for leg in legs if leg.trip_id is not None), dep_time)

        journeys.append(Journey(
            departure_time=depart_time,
            arrival_time=int(label.arrival),
            duration_minutes=round((int(label.arrival) - depart_time) / 60),
            walk_seconds=label.walk_seconds,
            transfers=label.transfers,
            legs=legs,
        ))

    journeys.sort(key=lambda j: j.arrival_time)
    journeys = journeys[:max_results]

    logger.info("Found %s Pareto-optimal journeys from %s to %s", len(journeys), src, dst)
    return journeys
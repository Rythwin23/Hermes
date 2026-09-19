from apps.routing.raptor.model import Label, add_label, visits_stop


def test_same_candidate_is_not_inserted_twice():
    bag: list[Label] = []
    candidate = Label(
        arrival=8_100,
        walk_seconds=30,
        transfers=1,
        stop_idx=2,
        trip_id="trip-1",
        route_idx=7,
        from_stop=1,
        departure_time=8_000,
        parent=None,
        visited_stops=frozenset({1, 2}),
    )

    assert add_label(bag, candidate) is True
    assert add_label(bag, candidate) is False
    assert len(bag) == 1


def test_visits_stop_uses_visited_stop_cache():
    origin = Label(
        arrival=8_000,
        walk_seconds=0,
        transfers=0,
        stop_idx=1,
        trip_id=None,
        route_idx=None,
        from_stop=None,
        departure_time=None,
        parent=None,
        visited_stops=frozenset({1}),
    )

    child = Label(
        arrival=8_100,
        walk_seconds=30,
        transfers=0,
        stop_idx=2,
        trip_id="trip-1",
        route_idx=7,
        from_stop=1,
        departure_time=8_000,
        parent=origin,
        visited_stops=frozenset({1, 2}),
    )

    assert visits_stop(child, 1) is True
    assert visits_stop(child, 2) is True
    assert visits_stop(child, 9) is False

from __future__ import annotations

from collections import defaultdict

from .models import FreightLoad, RoutedLoad


def route_load(load: FreightLoad) -> RoutedLoad:
    return RoutedLoad(load=load, route_key=load.route_key)


def route_loads(loads: list[FreightLoad]) -> dict[str, list[RoutedLoad]]:
    routed: dict[str, list[RoutedLoad]] = defaultdict(list)
    for load in loads:
        item = route_load(load)
        routed[item.route_key].append(item)
    return dict(routed)

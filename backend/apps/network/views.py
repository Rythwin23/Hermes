from django.views.decorators.http import require_GET
from apps.network.responses import api_response
from apps.network.services import(
    get_parent_stop_routes,
    get_route_stops,
    get_stop_detail,
    get_stops,
    get_routes,
)


# method to get the list of routes
@require_GET
def routes_list(request):
    return api_response(request, get_routes())


@require_GET
def stops_list(request):
    return api_response(request, get_stops())


@require_GET
def parent_stop_route_list(request):
    return api_response(request, get_parent_stop_routes())


@require_GET
def stop_detail(request, stop_id: str):
    return api_response(request, get_stop_detail(stop_id))


@require_GET
def route_detail(request, route_id: str):
    return api_response(request, get_route_stops(route_id))

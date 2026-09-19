from __future__ import annotations

from datetime import date
import json
import polars as pl
from django.http import JsonResponse, HttpRequest
from apps.network.dataset import GTFSDataStore
from django.views.decorators.http import require_POST

from apps.network.responses import api_response
from apps.routing.services import raptor_query


def _stop_id_from_name(stop_name: str) -> str | None:
	"""
	Resolve a stop name to its station id: the parent station if one exists (RAPTOR can
	reach any of its platforms via the parent<->child transfers), otherwise the stop itself.
	Args:
		stop_name (str): The name of the stop.
	Returns:
		str | None: The matching stop ID, or None if no stop has this name.
	"""
	matches = GTFSDataStore.get().stops.filter(pl.col("stop_name") == stop_name)
	if matches.is_empty():
		return None
	station = matches.filter(pl.col("parent_stop_id").is_null())
	if not station.is_empty():
		return station.select("stop_id").to_series()[0]
	parent_ids = {p for p in matches["parent_stop_id"].to_list() if p}
	if len(parent_ids) == 1:
		return next(iter(parent_ids))
	return matches.select("stop_id").to_series()[0]

def _DateTime_to_seconds(time: str | int) -> int:
	"""
	Convert a DateTime HH:MM:SS to seconds.
	Args:
		time (str): Time string in HH:MM:SS format.
	Returns:
		int: Time in seconds.
	"""
	if isinstance(time, int):
		if time < 0:
			raise ValueError
		return time
	if not isinstance(time, str):
		raise ValueError
	if time.isdigit():
		return int(time)

	# Manual split (not datetime.strptime) because GTFS allows hours >= 24
	# for trips continuing past midnight (e.g. "25:30:00").
	hours_str, minutes_str, seconds_str = time.split(":")
	hours = int(hours_str)
	minutes = int(minutes_str)
	seconds = int(seconds_str)
	if minutes >= 60 or seconds >= 60:
		raise ValueError
	return hours * 3600 + minutes * 60 + seconds


@require_POST
def raptor_test(request: HttpRequest):
	try:
		json_data = json.loads(request.body or b"{}")
	except json.JSONDecodeError:
		return JsonResponse({"error": "invalid JSON body"}, status=400)
	
	source_stop_name = json_data.get("source_stop_name")
	target_stop_name = json_data.get("target_stop_name")
	stop_with_id = json_data.get("stop_with_id")
	departure_raw = json_data.get("departure_time")
	travel_date_raw = json_data.get("travel_date")

	if not stop_with_id and (not source_stop_name or not target_stop_name):
		return JsonResponse(
			{
				"error": "source_stop_name and target_stop_name are required if stop_with_id is not provided",
				"example": {
					"source_stop_name": "STOP_A",
					"target_stop_name": "STOP_B",
					"stop_with_id": None,
					"departure_time": "09:00:00",
					"travel_date": "2026-09-15"
				}
			},
			status=400,
		)

	if departure_raw is None:
		return JsonResponse(
			{
				"error": "departure_time is required (seconds or HH:MM:SS)",
			},
			status=400,
		)

	try:
		departure_time = _DateTime_to_seconds(departure_raw)
	except ValueError:
		return JsonResponse(
			{
				"error": "invalid departure_time, expected seconds or HH:MM:SS",
			},
			status=400,
		)

	try:
		travel_day = (
			date.fromisoformat(travel_date_raw)
			if travel_date_raw
			else date.today()
		)
	except ValueError:
		return JsonResponse(
			{
				"error": "invalid travel_date, expected YYYY-MM-DD",
			},
			status=400,
		)

	if not stop_with_id:
		source_stop_id = _stop_id_from_name(source_stop_name)
		target_stop_id = _stop_id_from_name(target_stop_name)
	else:
		source_stop_id = source_stop_name
		target_stop_id = target_stop_name

	if not source_stop_id or not target_stop_id:
		return JsonResponse(
			{
				"error": "unknown source_stop_name or target_stop_name, or missing stop_with_id",
			},
			status=404,
		)

	payload = raptor_query(
		source_stop_id=source_stop_id,
		target_stop_id=target_stop_id,
		departure_time=departure_time,
		travel_date=travel_day,
		max_rounds=7,
		max_results=5,
	)
	return api_response(request, payload)

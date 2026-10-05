import math
import requests

from django.http import JsonResponse

from .models import FuelStation


OSRM_URL = "https://router.project-osrm.org/route/v1/driving"

MAX_RANGE_MILES = 500
DEFAULT_MPG = 10
ROUTE_SEARCH_RADIUS_KM = 16


def haversine_miles(lat1, lon1, lat2, lon2):
    radius = 3958.8

    lat1 = math.radians(lat1)
    lat2 = math.radians(lat2)

    dlat = lat2 - lat1
    dlon = math.radians(lon2 - lon1)

    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1)
        * math.cos(lat2)
        * math.sin(dlon / 2) ** 2
    )

    return radius * 2 * math.asin(math.sqrt(a))


def route_position(station_lat, station_lon, route_coordinates):
    """
    Find approximate position of a station along the route.
    Returns distance from route start in miles and distance
    from the station to the nearest route point.
    """

    if not route_coordinates:
        return None, None

    # Limit calculations for better API performance.
    max_points = 1200
    step = max(1, len(route_coordinates) // max_points)

    sampled = route_coordinates[::step]

    best_distance = float("inf")
    best_index = 0

    for index, point in enumerate(sampled):
        lon, lat = point

        distance = haversine_miles(
            station_lat,
            station_lon,
            lat,
            lon,
        )

        if distance < best_distance:
            best_distance = distance
            best_index = index

    # Calculate approximate route distance to that point.
    route_distance = 0

    for i in range(best_index):
        lon1, lat1 = sampled[i]
        lon2, lat2 = sampled[i + 1]

        route_distance += haversine_miles(
            lat1,
            lon1,
            lat2,
            lon2,
        )

    return route_distance, best_distance


def get_station_candidates(route_coordinates):
    """
    Get stations close to the route and determine their
    approximate position along the route.
    """

    stations = (
        FuelStation.objects
        .filter(
            latitude__isnull=False,
            longitude__isnull=False,
        )
        .prefetch_related("prices")
    )

    candidates = []

    for station in stations:
        prices = list(station.prices.all())

        if not prices:
            continue

        route_position_miles, distance_from_route = (
            route_position(
                station.latitude,
                station.longitude,
                route_coordinates,
            )
        )

        if route_position_miles is None:
            continue

        if distance_from_route > ROUTE_SEARCH_RADIUS_KM * 0.621371:
            continue

        cheapest_price = min(
            prices,
            key=lambda price: price.retail_price,
        )

        candidates.append(
            {
                "id": station.id,
                "opis_truckstop_id": station.opis_truckstop_id,
                "name": station.truckstop_name,
                "city": station.city,
                "state": station.state,
                "latitude": station.latitude,
                "longitude": station.longitude,
                "fuel_price": float(
                    cheapest_price.retail_price
                ),
                "route_position_miles": round(
                    route_position_miles,
                    2,
                ),
                "distance_from_route_miles": round(
                    distance_from_route,
                    2,
                ),
            }
        )

    candidates.sort(
        key=lambda station: station["route_position_miles"]
    )

    return candidates


def optimize_fuel_stops(
    candidates,
    total_distance_miles,
    mpg,
):
    """
    Plan fuel stops while respecting the 500-mile maximum range.

    The vehicle starts with a full tank.
    At each stop:
      - If a cheaper station is reachable, buy only enough
        fuel to reach it.
      - Otherwise, fill enough for the next leg, up to 500 miles.
    """

    if total_distance_miles <= MAX_RANGE_MILES:
        return [], 0.0, 0.0

    fuel_remaining_miles = MAX_RANGE_MILES
    current_position = 0.0
    total_cost = 0.0
    total_gallons = 0.0

    stops = []

    available = [
        station
        for station in candidates
        if station["route_position_miles"] > 0
    ]

    while (
        total_distance_miles - current_position
        > fuel_remaining_miles
    ):

        reachable = [
            station
            for station in available
            if (
                station["route_position_miles"]
                > current_position + 1
                and station["route_position_miles"]
                - current_position
                <= fuel_remaining_miles
            )
        ]

        if not reachable:
            return None, None, None

        # Pick the cheapest reachable station.
        next_station = min(
            reachable,
            key=lambda station: (
                station["fuel_price"],
                station["route_position_miles"],
            ),
        )

        travel_miles = (
            next_station["route_position_miles"]
            - current_position
        )

        fuel_remaining_miles -= travel_miles
        current_position = (
            next_station["route_position_miles"]
        )

        # Look for a cheaper station within the next
        # 500 miles.
        cheaper_stations = [
            station
            for station in available
            if (
                station["route_position_miles"]
                > current_position + 1
                and station["route_position_miles"]
                - current_position
                <= MAX_RANGE_MILES
                and station["fuel_price"]
                < next_station["fuel_price"]
            )
        ]

        remaining_distance = (
            total_distance_miles - current_position
        )

        if cheaper_stations:
            target = min(
                cheaper_stations,
                key=lambda station: station[
                    "route_position_miles"
                ],
            )

            target_distance = (
                target["route_position_miles"]
                - current_position
            )

            required_miles = target_distance

        else:
            required_miles = min(
                MAX_RANGE_MILES,
                remaining_distance,
            )

        if fuel_remaining_miles < required_miles:
            miles_to_buy = (
                required_miles
                - fuel_remaining_miles
            )

            gallons = miles_to_buy / mpg
            cost = (
                gallons
                * next_station["fuel_price"]
            )

            fuel_remaining_miles += miles_to_buy
            total_gallons += gallons
            total_cost += cost

            stop = dict(next_station)

            stop["gallons_purchased"] = round(
                gallons,
                2,
            )

            stop["fuel_cost"] = round(
                cost,
                2,
            )

            stop["fuel_price"] = round(
                next_station["fuel_price"],
                4,
            )

            stops.append(stop)

        available = [
            station
            for station in available
            if station["route_position_miles"]
            > current_position + 1
        ]

    return (
        stops,
        round(total_gallons, 2),
        round(total_cost, 2),
    )


def route_api(request):
    if request.method != "GET":
        return JsonResponse(
            {"error": "Only GET requests are allowed"},
            status=405,
        )

    start = request.GET.get("start")
    destination = request.GET.get("destination")
    mpg_value = request.GET.get(
        "mpg",
        str(DEFAULT_MPG),
    )

    if not start or not destination:
        return JsonResponse(
            {
                "error": (
                    "Please provide start and destination "
                    "as latitude,longitude"
                )
            },
            status=400,
        )

    try:
        start_lat, start_lon = map(
            float,
            start.split(","),
        )

        dest_lat, dest_lon = map(
            float,
            destination.split(","),
        )

        mpg = float(mpg_value)

        if mpg <= 0:
            raise ValueError

    except ValueError:
        return JsonResponse(
            {
                "error": (
                    "Invalid coordinates or MPG. "
                    "Example: mpg=10"
                )
            },
            status=400,
        )

    try:
        coordinates = (
            f"{start_lon},{start_lat};"
            f"{dest_lon},{dest_lat}"
        )

        response = requests.get(
            f"{OSRM_URL}/{coordinates}",
            params={
                "overview": "full",
                "geometries": "geojson",
            },
            timeout=30,
        )

        response.raise_for_status()

        route_data = response.json()

        if route_data.get("code") != "Ok":
            return JsonResponse(
                {
                    "error": "Route could not be calculated"
                },
                status=400,
            )

        route = route_data["routes"][0]

        route_coordinates = (
            route["geometry"]["coordinates"]
        )

        total_distance_miles = (
            route["distance"] / 1609.344
        )

        total_distance_km = (
            route["distance"] / 1000
        )

        duration_minutes = (
            route["duration"] / 60
        )

        candidates = get_station_candidates(
            route_coordinates
        )

        result = optimize_fuel_stops(
            candidates,
            total_distance_miles,
            mpg,
        )

        if result[0] is None:
            return JsonResponse(
                {
                    "error": (
                        "Unable to plan the trip within "
                        "the 500-mile vehicle range. "
                        "There are not enough reachable "
                        "fuel stations along this route."
                    ),
                    "route": {
                        "distance_miles": round(
                            total_distance_miles,
                            2,
                        ),
                        "distance_km": round(
                            total_distance_km,
                            2,
                        ),
                    },
                    "stations_found": len(
                        candidates
                    ),
                },
                status=422,
            )

        fuel_stops, total_gallons, total_cost = result

        return JsonResponse(
            {
                "start": {
                    "latitude": start_lat,
                    "longitude": start_lon,
                },
                "destination": {
                    "latitude": dest_lat,
                    "longitude": dest_lon,
                },
                "vehicle": {
                    "mpg": mpg,
                    "maximum_range_miles": (
                        MAX_RANGE_MILES
                    ),
                },
                "route": {
                    "distance_miles": round(
                        total_distance_miles,
                        2,
                    ),
                    "distance_km": round(
                        total_distance_km,
                        2,
                    ),
                    "duration_minutes": round(
                        duration_minutes,
                        2,
                    ),
                    "geometry": route["geometry"],
                },
                "fuel_plan": {
                    "stops": fuel_stops,
                    "number_of_stops": len(
                        fuel_stops
                    ),
                    "total_gallons": total_gallons,
                    "total_fuel_cost": total_cost,
                },
                "stations_found_near_route": len(
                    candidates
                ),
            }
        )

    except requests.RequestException as error:
        return JsonResponse(
            {
                "error": (
                    "Routing service unavailable"
                ),
                "details": str(error),
            },
            status=503,
        )
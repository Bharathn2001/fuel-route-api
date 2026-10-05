import time
import requests

from django.core.management.base import BaseCommand
from routing.models import FuelStation


ARCGIS_URL = (
    "https://geocode.arcgis.com/arcgis/rest/services/"
    "World/GeocodeServer/findAddressCandidates"
)

REQUEST_DELAY = 1.0
TIMEOUT = 30
MAX_RETRIES = 3


class Command(BaseCommand):
    help = "Geocode pending fuel stations using ArcGIS"

    def handle(self, *args, **options):

        stations = FuelStation.objects.filter(
            geocoding_status="pending",
            latitude__isnull=True,
            longitude__isnull=True,
        )[:500]

        total = stations.count()

        self.stdout.write(
            f"Pending stations: {total}"
        )

        if total == 0:
            self.stdout.write(
                self.style.SUCCESS(
                    "No pending stations to geocode."
                )
            )
            return

        matched = 0
        approximate = 0
        failed = 0

        for index, station in enumerate(
            stations.iterator(),
            start=1,
        ):

            query = (
                f"{station.address}, "
                f"{station.city}, "
                f"{station.state}, USA"
            )

            self.stdout.write(
                f"\n[{index}/{total}] "
                f"Station {station.opis_truckstop_id}"
            )
            self.stdout.write(
                f"Query: {query}"
            )

            data = None

            for attempt in range(1, MAX_RETRIES + 1):

                try:
                    response = requests.get(
                        ARCGIS_URL,
                        params={
                            "singleLine": query,
                            "countryCode": "USA",
                            "maxLocations": 3,
                            "outFields": "*",
                            "f": "json",
                        },
                        timeout=TIMEOUT,
                    )

                    response.raise_for_status()
                    data = response.json()
                    break

                except (
                    requests.RequestException,
                    ValueError,
                ) as exc:

                    if attempt == MAX_RETRIES:
                        self.stdout.write(
                            self.style.ERROR(
                                f"Request failed: {exc}"
                            )
                        )
                    else:
                        self.stdout.write(
                            self.style.WARNING(
                                f"Retry {attempt}/{MAX_RETRIES}"
                            )
                        )
                        time.sleep(2 * attempt)

            if not data:
                failed += 1
                time.sleep(REQUEST_DELAY)
                continue

            candidates = data.get(
                "candidates",
                [],
            )

            if not candidates:
                self.stdout.write(
                    self.style.WARNING(
                        "No ArcGIS result"
                    )
                )
                failed += 1
                time.sleep(REQUEST_DELAY)
                continue

            best = candidates[0]

            score = float(
                best.get("score", 0)
            )

            location = best.get(
                "location",
                {},
            )

            latitude = location.get("y")
            longitude = location.get("x")

            match_type = (
                best.get("attributes", {})
                .get("Addr_type", "")
            )

            if latitude is None or longitude is None:
                failed += 1
                time.sleep(REQUEST_DELAY)
                continue

            # Strong result
            if score >= 90:

                station.latitude = float(latitude)
                station.longitude = float(longitude)
                station.geocoding_score = score

                if score >= 95:
                    station.geocoding_status = "arcgis_match"
                    matched += 1
                else:
                    station.geocoding_status = (
                        "arcgis_approximate"
                    )
                    approximate += 1

                station.save(
                    update_fields=[
                        "latitude",
                        "longitude",
                        "geocoding_status",
                        "geocoding_score",
                    ]
                )

                self.stdout.write(
                    self.style.SUCCESS(
                        f"Accepted: score={score:.2f}, "
                        f"type={match_type}"
                    )
                )

            else:
                self.stdout.write(
                    self.style.WARNING(
                        f"Rejected: score={score:.2f}, "
                        f"type={match_type}"
                    )
                )
                failed += 1

            time.sleep(REQUEST_DELAY)

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                f"ArcGIS matches: {matched}"
            )
        )
        self.stdout.write(
            self.style.WARNING(
                f"Approximate: {approximate}"
            )
        )
        self.stdout.write(
            self.style.WARNING(
                f"Failed/pending: {failed}"
            )
        )
import time
import requests

from django.core.management.base import BaseCommand
from routing.models import FuelStation


NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"

HEADERS = {
    "User-Agent": "fuel-route-api-geocoder/1.0"
}


class Command(BaseCommand):
    help = "Test OSM Nominatim geocoding on 10 pending fuel stations"

    def handle(self, *args, **options):

        stations = FuelStation.objects.filter(
            geocoding_status="pending"
        )[:10]

        for station in stations:

            query = (
                f"{station.address}, "
                f"{station.city}, "
                f"{station.state}, USA"
            )

            self.stdout.write(
                f"\nStation {station.opis_truckstop_id}"
            )
            self.stdout.write(
                f"Query: {query}"
            )

            try:
                response = requests.get(
                    NOMINATIM_URL,
                    params={
                        "q": query,
                        "format": "jsonv2",
                        "limit": 3,
                        "countrycodes": "us",
                    },
                    headers=HEADERS,
                    timeout=30,
                )

                response.raise_for_status()

                results = response.json()

                if not results:
                    self.stdout.write(
                        self.style.WARNING("No result")
                    )
                else:
                    for result in results:
                        self.stdout.write(
                            f"  {result.get('lat')}, "
                            f"{result.get('lon')} | "
                            f"{result.get('display_name')}"
                        )

            except requests.RequestException as exc:
                self.stdout.write(
                    self.style.ERROR(
                        f"Request failed: {exc}"
                    )
                )

            # Nominatim public-service limit:
            # maximum 1 request per second.
            time.sleep(1.1)
import requests

from django.core.management.base import BaseCommand
from routing.models import FuelStation


ARCGIS_URL = (
    "https://geocode.arcgis.com/arcgis/rest/services/"
    "World/GeocodeServer/findAddressCandidates"
)


class Command(BaseCommand):
    help = "Test ArcGIS geocoding on 10 pending fuel stations"

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
                    ARCGIS_URL,
                    params={
                        "singleLine": query,
                        "countryCode": "USA",
                        "maxLocations": 3,
                        "outFields": "*",
                        "f": "json",
                    },
                    timeout=30,
                )

                response.raise_for_status()

                data = response.json()
                candidates = data.get("candidates", [])

                if not candidates:
                    self.stdout.write(
                        self.style.WARNING("No result")
                    )
                    continue

                for candidate in candidates:
                    location = candidate.get("location", {})
                    attributes = candidate.get("attributes", {})

                    self.stdout.write(
                        f"  Score: {candidate.get('score')}"
                    )
                    self.stdout.write(
                        f"  Coordinates: "
                        f"{location.get('y')}, "
                        f"{location.get('x')}"
                    )
                    self.stdout.write(
                        f"  Address: "
                        f"{candidate.get('address')}"
                    )
                    self.stdout.write(
                        f"  Type: "
                        f"{attributes.get('Addr_type')}"
                    )

            except requests.RequestException as exc:
                self.stdout.write(
                    self.style.ERROR(
                        f"Request failed: {exc}"
                    )
                )
import csv
import io
import time

import requests
from django.core.management.base import BaseCommand

from routing.models import FuelStation


CENSUS_URL = (
    "https://geocoding.geo.census.gov/"
    "geocoder/locations/addressbatch"
)

BATCH_SIZE = 1000
MAX_RETRIES = 3


class Command(BaseCommand):
    help = "Batch geocode fuel stations using the U.S. Census Geocoder"

    def handle(self, *args, **options):

        stations = list(
            FuelStation.objects.filter(
                latitude__isnull=True,
                longitude__isnull=True,
            )
        )

        total = len(stations)

        self.stdout.write(
            f"Stations waiting for geocoding: {total}"
        )

        if total == 0:
            self.stdout.write(
                self.style.SUCCESS(
                    "All stations already have coordinates."
                )
            )
            return

        total_updated = 0
        total_failed = 0

        # -----------------------------------------------
        # Process stations in smaller batches
        # -----------------------------------------------

        for batch_start in range(0, total, BATCH_SIZE):

            batch = stations[
                batch_start:batch_start + BATCH_SIZE
            ]

            batch_number = (
                batch_start // BATCH_SIZE
            ) + 1

            total_batches = (
                (total + BATCH_SIZE - 1)
                // BATCH_SIZE
            )

            self.stdout.write(
                f"\nProcessing batch "
                f"{batch_number}/{total_batches} "
                f"({len(batch)} stations)..."
            )

            csv_buffer = io.StringIO()

            writer = csv.writer(csv_buffer)

            for station in batch:
                writer.writerow(
                    [
                        station.opis_truckstop_id,
                        station.address,
                        station.city,
                        station.state,
                        "",
                    ]
                )

            csv_buffer.seek(0)

            files = {
                "addressFile": (
                    "stations.csv",
                    csv_buffer.getvalue(),
                    "text/csv",
                )
            }

            params = {
                "benchmark": "Public_AR_Current",
            }

            response = None

            # -------------------------------------------
            # Retry temporary server errors
            # -------------------------------------------

            for attempt in range(1, MAX_RETRIES + 1):

                try:
                    response = requests.post(
                        CENSUS_URL,
                        params=params,
                        files=files,
                        timeout=120,
                    )

                    if response.status_code in (
                        502,
                        503,
                        504,
                    ):
                        self.stdout.write(
                            self.style.WARNING(
                                f"Census returned "
                                f"{response.status_code}. "
                                f"Retry {attempt}/"
                                f"{MAX_RETRIES}..."
                            )
                        )

                        time.sleep(3 * attempt)
                        continue

                    response.raise_for_status()
                    break

                except requests.RequestException as exc:

                    if attempt == MAX_RETRIES:
                        self.stdout.write(
                            self.style.ERROR(
                                f"Batch {batch_number} failed: "
                                f"{exc}"
                            )
                        )

                    time.sleep(3 * attempt)

            # -------------------------------------------
            # Skip batch if request ultimately failed
            # -------------------------------------------

            if response is None:
                total_failed += len(batch)
                continue

            if response.status_code >= 400:
                total_failed += len(batch)

                self.stdout.write(
                    self.style.ERROR(
                        f"Batch {batch_number} failed "
                        f"with HTTP {response.status_code}"
                    )
                )

                continue

            # -------------------------------------------
            # Save raw response for debugging
            # -------------------------------------------

            output_file = (
                f"data/"
                f"census_geocoding_batch_{batch_number}.csv"
            )

            with open(
                output_file,
                "w",
                encoding="utf-8",
                newline="",
            ) as file:
                file.write(response.text)

            # -------------------------------------------
            # Process Census results
            # -------------------------------------------

            batch_updated = 0
            batch_failed = 0

            reader = csv.reader(
                io.StringIO(response.text)
            )

            for row in reader:

                if len(row) < 6:
                    batch_failed += 1
                    continue

                try:
                    opis_id = int(row[0])
                except ValueError:
                    batch_failed += 1
                    continue

                match_status = row[2]

                if match_status != "Match":
                    batch_failed += 1
                    continue

                coordinates = row[5]

                if not coordinates:
                    batch_failed += 1
                    continue

                try:
                    longitude, latitude = (
                        coordinates.split(",")
                    )

                    longitude = float(longitude)
                    latitude = float(latitude)

                except (ValueError, AttributeError):
                    batch_failed += 1
                    continue

                try:
                    station = FuelStation.objects.get(
                        opis_truckstop_id=opis_id
                    )
                except FuelStation.DoesNotExist:
                    batch_failed += 1
                    continue

                station.latitude = latitude
                station.longitude = longitude
                station.geocoding_status = "census_match"

                station.save(
    update_fields=[
        "latitude",
        "longitude",
        "geocoding_status",
    ]
)

                batch_updated += 1

            total_updated += batch_updated
            total_failed += batch_failed

            self.stdout.write(
                self.style.SUCCESS(
                    f"Batch {batch_number}: "
                    f"{batch_updated} matched, "
                    f"{batch_failed} failed"
                )
            )

        # -----------------------------------------------
        # Final summary
        # -----------------------------------------------

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully geocoded: "
                f"{total_updated}"
            )
        )

        self.stdout.write(
            self.style.WARNING(
                f"Could not geocode: "
                f"{total_failed}"
            )
        )
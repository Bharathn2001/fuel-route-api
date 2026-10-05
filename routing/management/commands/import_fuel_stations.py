import pandas as pd

from django.core.management.base import BaseCommand
from routing.models import FuelStation, FuelPrice


class Command(BaseCommand):
    help = "Import fuel stations and fuel prices from the CSV file"

    def handle(self, *args, **options):
        file_path = "data/fuel-prices.csv"

        self.stdout.write("Reading CSV file...")

        df = pd.read_csv(file_path)

        self.stdout.write(
            self.style.SUCCESS(
                f"Found {len(df)} rows in CSV."
            )
        )

        # -------------------------------------------------
        # 1. Import unique physical fuel stations
        # -------------------------------------------------

        station_df = df.drop_duplicates(
            subset=["OPIS Truckstop ID"]
        )

        stations = []

        for _, row in station_df.iterrows():
            stations.append(
                FuelStation(
                    opis_truckstop_id=int(row["OPIS Truckstop ID"]),
                    truckstop_name=str(row["Truckstop Name"]),
                    address=str(row["Address"]),
                    city=str(row["City"]),
                    state=str(row["State"]),
                )
            )

        # Clear existing data so the command can safely be rerun
        FuelPrice.objects.all().delete()
        FuelStation.objects.all().delete()

        FuelStation.objects.bulk_create(
            stations,
            batch_size=1000,
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Imported {len(stations)} unique fuel stations."
            )
        )

        # -------------------------------------------------
        # 2. Import fuel prices
        # -------------------------------------------------

        station_map = {
            station.opis_truckstop_id: station
            for station in FuelStation.objects.all()
        }

        prices = []

        for _, row in df.iterrows():
            opis_id = int(row["OPIS Truckstop ID"])

            prices.append(
                FuelPrice(
                    station=station_map[opis_id],
                    rack_id=int(row["Rack ID"]),
                    retail_price=row["Retail Price"],
                )
            )

        FuelPrice.objects.bulk_create(
            prices,
            batch_size=1000,
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Imported {len(prices)} fuel price records."
            )
        )

        self.stdout.write(
            self.style.SUCCESS(
                "Fuel station import completed successfully."
            )
        )
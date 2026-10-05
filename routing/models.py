from django.db import models


class FuelStation(models.Model):
    opis_truckstop_id = models.IntegerField(unique=True)
    truckstop_name = models.CharField(max_length=255)
    address = models.CharField(max_length=255)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100, blank=True, default="") 

    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)

    geocoding_status = models.CharField(
        max_length=30,
        default="pending",
    )
    
    geocoding_score = models.FloatField(
    null=True,
    blank=True,
)

    class Meta:
        indexes = [
            models.Index(fields=["state"]),
            models.Index(fields=["geocoding_status"]),
        ]

    def __str__(self):
        return f"{self.truckstop_name} - {self.city}, {self.state}"

class FuelPrice(models.Model):
    station = models.ForeignKey(
        FuelStation,
        on_delete=models.CASCADE,
        related_name="prices",
    )
    rack_id = models.IntegerField()
    retail_price = models.DecimalField(
        max_digits=10,
        decimal_places=6,
    )

    class Meta:
        indexes = [
            models.Index(fields=["station"]),
        ]

    def __str__(self):
        return f"{self.station.truckstop_name}: ${self.retail_price}"
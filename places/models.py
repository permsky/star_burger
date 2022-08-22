from django.db import models


class Place(models.Model):
    address = models.CharField(
        'адрес места',
        max_length=255,
        unique=True,
        db_index=True,
    )
    longitude = models.FloatField(
        'долгота',
        blank=True,
        null=True,
    )
    lattitude = models.FloatField(
        'широта',
        blank=True,
        null=True,
    )
    geodata_update_date = models.DateTimeField(
        'дата обновления координат',
        db_index=True,
        auto_now=True,
    )

    class Meta:
        verbose_name = 'место'
        verbose_name_plural = 'места'

    def __str__(self):
        return f'{self.id} {self.address}'
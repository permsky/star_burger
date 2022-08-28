from operator import itemgetter

import requests
from django.db import models
from django.db.models import Prefetch
from django.conf import settings
from django.core.validators import MinValueValidator
from django.utils import timezone
from geopy import distance
from loguru import logger
from phonenumber_field.modelfields import PhoneNumberField

from places.models import Place
from places.utils import fetch_coordinates


class Restaurant(models.Model):
    name = models.CharField(
        'название',
        max_length=50
    )
    address = models.CharField(
        'адрес',
        max_length=100,
        blank=True,
    )
    contact_phone = models.CharField(
        'контактный телефон',
        max_length=50,
        blank=True,
    )

    class Meta:
        verbose_name = 'ресторан'
        verbose_name_plural = 'рестораны'

    def __str__(self):
        return self.name


class ProductQuerySet(models.QuerySet):
    def available(self):
        products = (
            RestaurantMenuItem.objects
            .filter(availability=True)
            .values_list('product')
        )
        return self.filter(pk__in=products)


class ProductCategory(models.Model):
    name = models.CharField(
        'название',
        max_length=50
    )

    class Meta:
        verbose_name = 'категория'
        verbose_name_plural = 'категории'

    def __str__(self):
        return self.name


class Product(models.Model):
    name = models.CharField(
        'название',
        max_length=50
    )
    category = models.ForeignKey(
        ProductCategory,
        verbose_name='категория',
        related_name='products',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    price = models.DecimalField(
        'цена',
        max_digits=8,
        decimal_places=2,
        validators=[MinValueValidator(0)]
    )
    image = models.ImageField(
        'картинка'
    )
    special_status = models.BooleanField(
        'спец.предложение',
        default=False,
        db_index=True,
    )
    description = models.TextField(
        'описание',
        max_length=200,
        blank=True,
    )

    objects = ProductQuerySet.as_manager()

    class Meta:
        verbose_name = 'товар'
        verbose_name_plural = 'товары'

    def __str__(self):
        return self.name


class RestaurantMenuItem(models.Model):
    restaurant = models.ForeignKey(
        Restaurant,
        related_name='menu_items',
        verbose_name="ресторан",
        on_delete=models.CASCADE,
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='menu_items',
        verbose_name='продукт',
    )
    availability = models.BooleanField(
        'в продаже',
        default=True,
        db_index=True
    )

    class Meta:
        verbose_name = 'пункт меню ресторана'
        verbose_name_plural = 'пункты меню ресторана'
        unique_together = [
            ['restaurant', 'product']
        ]

    def __str__(self):
        return f'{self.restaurant.name} - {self.product.name}'


class OrderQuerySet(models.QuerySet):
    def evaluate_distances(self):
        orders = self.prefetch_related(
            Prefetch(
                'items',
                queryset=OrderItem.objects.select_related('product')
            )
        )
        for order in orders:
            products_in_restaurants = list()
            for order_item in order.items.all():
                restaurants = list()
                for menu_item in order_item.product.menu_items.all():
                    restaurants.append(menu_item.restaurant)
                products_in_restaurants.append({
                    'product': order_item.product,
                    'restaurants': restaurants
                })
            restaurant_groups = [set(product['restaurants']) \
                for product in products_in_restaurants]
            order.restaurants = (
                restaurant_groups[0]
                .intersection(*restaurant_groups[1:])
            )
            distances = list()
            api_key = settings.YANDEX_GEO_API_KEY
            order_address = order.address
            client_place, is_created = Place.objects.get_or_create(
                address=order_address,
                defaults = {
                    'lattitude': None,
                    'longitude': None
                }
            )
            try:
                if not is_created:
                    client_coordinates = (
                        client_place.lattitude,
                        client_place.longitude
                    )
                else:
                    client_coordinates = fetch_coordinates(
                        api_key,
                        order_address
                    )
                    client_place.lattitude = client_coordinates[0]
                    client_place.longitude = client_coordinates[1]
                    client_place.save()
            except requests.exceptions.HTTPError:
                logger.exception("Ошибка HTTP запроса:")
                client_coordinates = None
            except Exception:
                logger.exception("Непредвиденная ошибка:")
                client_coordinates = None
            if client_coordinates:
                for restaurant in order.restaurants:
                    restaurant_address = restaurant.address
                    place, is_created = Place.objects.get_or_create(
                        address=restaurant_address,
                        defaults = {
                            'lattitude': None,
                            'longitude': None
                        }
                    )
                    try:
                        if not is_created:
                            restaurant_coordinates = (
                                place.lattitude,
                                place.longitude
                            )
                        else:
                            restaurant_coordinates = fetch_coordinates(
                                api_key,
                                restaurant_address
                            )
                            place.lattitude = restaurant_coordinates[0]
                            place.longitude = restaurant_coordinates[1]
                            place.save()
                    except requests.exceptions.HTTPError:
                        logger.exception("Ошибка HTTP запроса:")
                        order.distances = None
                        break
                    except Exception:
                        logger.exception("Непредвиденная ошибка:")
                        order.distances = None
                        break
                    distance_between_restaurant_and_client = (
                        distance.distance(
                            client_coordinates,
                            restaurant_coordinates
                        ).km
                    )
                    distances.append([
                        restaurant,
                        round(distance_between_restaurant_and_client, 3)
                    ])
                order.distances = sorted(distances, key=itemgetter(1))
            else:
                order.distances = None
        return orders


class Order(models.Model):
    STATUSES = [
        ('1', 'Необработанный'),
        ('2', 'В сборке'),
        ('3', 'В доставке'),
        ('4', 'Выполнен'),
    ]
    PAYMENT_METHODS = [
        ('1', 'Электронно'),
        ('2', 'Наличностью'),
        ('3', 'Не выбран'),
    ]
    firstname = models.CharField('имя клиента', max_length=255)
    lastname = models.CharField('фамилия клиента', max_length=255)
    phonenumber =  PhoneNumberField(
        region='RU',
        verbose_name='номер телефона клиента',
        db_index=True,
    )
    address = models.CharField(
        'адрес клиента',
        max_length=255,
        db_index=True,
    )
    status = models.CharField(
        'статус заказа',
        max_length=2,
        db_index=True,
        choices=STATUSES,
        default='1',
    )
    restaurant = models.ForeignKey(
        Restaurant,
        verbose_name='ресторан',
        related_name='orders',
        blank=True,
        null=True,
        on_delete=models.CASCADE,
    )
    comment = models.TextField('комментарий', blank=True)
    created_at = models.DateTimeField(
        'дата и время создания',
        default=timezone.now,
        db_index=True,
    )
    called_at = models.DateTimeField(
        'дата и время звонка',
        null=True,
        blank=True,
        db_index=True,
    )
    delivered_at = models.DateTimeField(
        'дата и время доставки',
        null=True,
        blank=True,
        db_index=True,
    )
    payment_method = models.CharField(
        'способ оплаты',
        max_length=2,
        db_index=True,
        choices=PAYMENT_METHODS,
        default='3',
    )
    objects = OrderQuerySet.as_manager()

    class Meta:
        verbose_name = 'заказ'
        verbose_name_plural = 'заказы'

    def __str__(self):
        return f'{self.phonenumber}'


class OrderItem(models.Model):
    product = models.ForeignKey(
        Product,
        verbose_name='товар',
        related_name='in_orders',
        on_delete=models.CASCADE,
    )
    quantity = models.PositiveSmallIntegerField(
        'количество',
        validators=[MinValueValidator(1)],
    )
    order = models.ForeignKey(
        Order,
        verbose_name='заказ',
        related_name='items',
        on_delete=models.CASCADE,
    )
    cost = models.DecimalField(
        'стоимость',
        max_digits=8,
        decimal_places=2,
        validators=[MinValueValidator(0)],
    )

    class Meta:
        verbose_name = 'товар в заказе'
        verbose_name_plural = 'товары в заказе'

    def __str__(self):
        return f'{self.product.name}: {self.quantity}'

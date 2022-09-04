from django.db import models
from django.db.models import Prefetch
from django.core.validators import MinValueValidator
from django.utils import timezone

from phonenumber_field.modelfields import PhoneNumberField


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
    def find_available_restaurants(self):
        orders = self.prefetch_related(
            Prefetch(
                'items',
                queryset=OrderItem.objects.select_related('product')
            )
        )
        for order in orders:
            products_in_restaurants = list()
            for order_item in order.items.all():
                restaurants = [menu_item.restaurant for menu_item \
                    in order_item.product.menu_items.all()]
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
    cooking_restaurant = models.ForeignKey(
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
        related_name='in_items',
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
        blank=True,
    )

    class Meta:
        verbose_name = 'товар в заказе'
        verbose_name_plural = 'товары в заказе'

    def __str__(self):
        return f'{self.product.name}: {self.quantity}'

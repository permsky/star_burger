from operator import itemgetter

import requests
from django import forms
from django.conf import settings
from django.contrib.auth import authenticate, login
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import user_passes_test
from django.db.models import Sum
from django.shortcuts import redirect, render
from django.views import View
from django.urls import reverse_lazy
from geopy import distance
from loguru import logger

from foodcartapp.models import Product, Restaurant, Order
from places.models import Place
from places.utils import fetch_coordinates


class Login(forms.Form):
    username = forms.CharField(
        label='Логин', max_length=75, required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Укажите имя пользователя'
        })
    )
    password = forms.CharField(
        label='Пароль', max_length=75, required=True,
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Введите пароль'
        })
    )


class LoginView(View):
    def get(self, request, *args, **kwargs):
        form = Login()
        return render(request, "login.html", context={
            'form': form
        })

    def post(self, request):
        form = Login(request.POST)

        if form.is_valid():
            username = form.cleaned_data['username']
            password = form.cleaned_data['password']

            user = authenticate(request, username=username, password=password)
            if user:
                login(request, user)
                if user.is_staff:  # FIXME replace with specific permission
                    return redirect("restaurateur:RestaurantView")
                return redirect("start_page")

        return render(request, "login.html", context={
            'form': form,
            'ivalid': True,
        })


class LogoutView(auth_views.LogoutView):
    next_page = reverse_lazy('restaurateur:login')


def is_manager(user):
    return user.is_staff  # FIXME replace with specific permission


@user_passes_test(is_manager, login_url='restaurateur:login')
def view_products(request):
    restaurants = list(Restaurant.objects.order_by('name'))
    products = list(Product.objects.prefetch_related('menu_items'))

    default_availability = {restaurant.id: False for restaurant in restaurants}
    products_with_restaurants = []
    for product in products:

        availability = {
            **default_availability,
            **{item.restaurant_id: item.availability for item in product.menu_items.all()},
        }
        orderer_availability = [availability[restaurant.id] for restaurant in restaurants]

        products_with_restaurants.append(
            (product, orderer_availability)
        )

    return render(request, template_name="products_list.html", context={
        'products_with_restaurants': products_with_restaurants,
        'restaurants': restaurants,
    })


@user_passes_test(is_manager, login_url='restaurateur:login')
def view_restaurants(request):
    return render(request, template_name="restaurants_list.html", context={
        'restaurants': Restaurant.objects.all(),
    })


def evaluate_distances_to_restaurants(order, api_key):
    distances = list()
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
            client_place.lattitude, client_place.longitude \
                = client_coordinates
            client_place.save()
    except requests.exceptions.HTTPError:
        logger.exception("Ошибка HTTP запроса:")
        client_coordinates = None
    except Exception:
        logger.exception("Непредвиденная ошибка:")
        client_coordinates = None
    if not client_coordinates:
        order.distances = None
        return order
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
                place.lattitude, place.longitude = restaurant_coordinates
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
    return order


@user_passes_test(is_manager, login_url='restaurateur:login')
def view_orders(request):
    orders = (
        Order.objects
        .exclude(status='4')
        .annotate(cost=Sum('items__cost'))
        .find_available_restaurants()
    )
    for order in orders:
        order = evaluate_distances_to_restaurants(
            order=order,
            api_key=settings.YANDEX_GEO_API_KEY
        )

    return render(request, template_name='order_items.html', context={
        'order_items': orders,
    })

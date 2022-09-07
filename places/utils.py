from operator import itemgetter

import requests
from geopy import distance
from loguru import logger

from places.models import Place


def fetch_coordinates(apikey, address):
    base_url = "https://geocode-maps.yandex.ru/1.x"
    response = requests.get(base_url, params={
        "geocode": address,
        "apikey": apikey,
        "format": "json",
    })
    response.raise_for_status()
    found_places = response.json()['response']['GeoObjectCollection']['featureMember']

    if not found_places:
        return None

    most_relevant = found_places[0]
    lon, lat = most_relevant['GeoObject']['Point']['pos'].split(" ")
    return lat, lon


def evaluate_distances_to_restaurants(order, api_key, place=None):
    distances = list()
    order_address = order.address
    try:
        if place:
            client_place = place
            if not client_place.lattitude and not client_place.longitude:
                order.distances = None
                return order
            client_coordinates = (
                client_place.lattitude,
                client_place.longitude
            )
        else:
            client_coordinates = fetch_coordinates(api_key, order_address)
            if not client_coordinates:
                order.distances = None
                return order
            Place.objects.create(
                address=order_address,
                lattitude=client_coordinates[0],
                longitude=client_coordinates[1]
            )
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
            defaults={
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

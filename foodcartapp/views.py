from django.http import JsonResponse
from django.templatetags.static import static
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response


from .models import (
    Order,
    OrderItem,
    Product
)


def banners_list_api(request):
    # FIXME move data to db?
    return JsonResponse([
        {
            'title': 'Burger',
            'src': static('burger.jpg'),
            'text': 'Tasty Burger at your door step',
        },
        {
            'title': 'Spices',
            'src': static('food.jpg'),
            'text': 'All Cuisines',
        },
        {
            'title': 'New York',
            'src': static('tasty.jpg'),
            'text': 'Food is incomplete without a tasty dessert',
        }
    ], safe=False, json_dumps_params={
        'ensure_ascii': False,
        'indent': 4,
    })


def product_list_api(request):
    products = Product.objects.select_related('category').available()

    dumped_products = []
    for product in products:
        dumped_product = {
            'id': product.id,
            'name': product.name,
            'price': product.price,
            'special_status': product.special_status,
            'description': product.description,
            'category': {
                'id': product.category.id,
                'name': product.category.name,
            } if product.category else None,
            'image': product.image.url,
            'restaurant': {
                'id': product.id,
                'name': product.name,
            }
        }
        dumped_products.append(dumped_product)
    return JsonResponse(dumped_products, safe=False, json_dumps_params={
        'ensure_ascii': False,
        'indent': 4,
    })


@api_view(['POST'])
def register_order(request):
    serialized_order = request.data
    products = serialized_order.get('products', list())
    if not isinstance(products, list) or products == list():
        content = {
            'error': 'products key not presented or not a list'
        }
        return Response(content, status=status.HTTP_400_BAD_REQUEST)
    order = Order.objects.create(
        customer_firstname=serialized_order['firstname'],
        customer_lastname=serialized_order['lastname'],
        address=serialized_order['address'],
        phonenumber=serialized_order['phonenumber'],
    )
    for order_item in products:
        OrderItem.objects.create(
            item=Product.objects.get(id=order_item['product']),
            order=order,
            quantity=order_item['quantity']
        )
    return Response(serialized_order)

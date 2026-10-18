"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path

from store.views import (
    products,
    product_detail,
    index,
    submit_review,
    register,
    login_view,
    profile,
    add_to_cart,
    cart_view,
    increase_cart,
    decrease_cart,
    remove_from_cart,
    checkout,
    orders_view,
    order_detail,
    seller_login,
    seller_dashboard,
    seller_add_product,
    seller_update_product,
    seller_delete_product,
    seller_logout,
    admin_login,
    admin_dashboard,
    admin_customers,
    admin_sellers,
    admin_products,
    admin_add_product,
    admin_update_product,
    admin_delete_product,
    admin_orders,
    admin_logout,
    payment_page,
    process_payment,
    admin_funnel_analysis,
    admin_product_funnel,
    customer_logout,
    buy_now,
    admin_analytics,
    product_image,
    admin_update_order_status,
    cancel_order,
)
urlpatterns = [
    path('admin/', admin.site.urls),
    path('', index, name='index'),

    path('products/', products),

    path(
        'product/<int:product_id>/',
        product_detail,
        name='product_detail'
    ),
path(
    'product/<int:product_id>/review/',
    submit_review,
    name='submit_review'
),

    path('register/', register),

    path('login/', login_view),

    path('profile/', profile),

    path(
        'cart/add/<int:product_id>/',
        add_to_cart,
        name='add_to_cart'
    ),

    path(
        'cart/',
        cart_view,
        name='cart'
    ),
    path(
    'cart/increase/<int:cart_id>/',
    increase_cart,
    name='increase_cart'
),

path(
    'cart/decrease/<int:cart_id>/',
    decrease_cart,
    name='decrease_cart'
),

path(
    'cart/remove/<int:cart_id>/',
    remove_from_cart,
    name='remove_from_cart'
),
path('checkout/', checkout, name='checkout'),
path(
    'orders/',
    orders_view,
    name='orders'
),
path(
    'order/<int:order_id>/',
    order_detail,
    name='order_detail'
),
path(
    'seller/login/',
    seller_login,
    name='seller_login'
),
path(
    'seller/dashboard/',
    seller_dashboard,
    name='seller_dashboard'
),
path(
    'seller/product/add/',
    seller_add_product,
    name='seller_add_product'
),
path(
    'seller/product/<int:product_id>/edit/',
    seller_update_product,
    name='seller_update_product'
),
path(
    'seller/product/<int:product_id>/delete/',
    seller_delete_product,
    name='seller_delete_product'
),
path(
    'seller/logout/',
    seller_logout,
    name='seller_logout'
),
path('adminpanel/login/', admin_login, name='admin_login'),
path('adminpanel/logout/', admin_logout, name='admin_logout'),
path('adminpanel/dashboard/', admin_dashboard, name='admin_dashboard'),
path('adminpanel/customers/', admin_customers, name='admin_customers'),
path('adminpanel/sellers/', admin_sellers, name='admin_sellers'),
path('adminpanel/products/', admin_products, name='admin_products'),
path('adminpanel/product/add/', admin_add_product, name='admin_add_product'),
path('adminpanel/product/<int:product_id>/edit/', admin_update_product, name='admin_update_product'),
path('adminpanel/product/<int:product_id>/delete/', admin_delete_product, name='admin_delete_product'),
path('adminpanel/orders/', admin_orders, name='admin_orders'),
path('payment/<int:order_id>/', payment_page, name='payment_page'),
path('payment/process/<int:order_id>/', process_payment, name='process_payment'),
path('adminpanel/funnel/', admin_funnel_analysis, name='admin_funnel'),
path('adminpanel/funnel/product/<int:product_id>/', admin_product_funnel, name='admin_product_funnel'),
path('logout/', customer_logout, name='customer_logout'),
path('buy-now/<int:product_id>/', buy_now, name='buy_now'),
path('adminpanel/analytics/', admin_analytics, name='admin_analytics'),
path('product-image/<int:product_id>/', product_image, name='product_image'),
path('adminpanel/order/<int:order_id>/status/', admin_update_order_status, name='admin_update_order_status'),
path('order/<int:order_id>/cancel/', cancel_order, name='cancel_order'),
]
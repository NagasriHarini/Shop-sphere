from django.db import models

class Admin(models.Model):
    admin_id = models.AutoField(primary_key=True)
    username = models.CharField(unique=True, max_length=50)
    password = models.CharField(max_length=255)
    email = models.CharField(unique=True, max_length=100)

    class Meta:
        managed = False
        db_table = 'admin'


class Cart(models.Model):
    cart_id = models.AutoField(primary_key=True)
    customer = models.ForeignKey('Customers', models.DO_NOTHING)
    product = models.ForeignKey('Products', models.DO_NOTHING)
    quantity = models.IntegerField()
    added_date = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'cart'


class Customers(models.Model):
    customer_id = models.AutoField(primary_key=True)
    first_name = models.CharField(max_length=50)
    last_name = models.CharField(max_length=50)
    email = models.CharField(unique=True, max_length=100)
    password = models.CharField(max_length=255)
    phone = models.CharField(max_length=15, blank=True, null=True)
    gender = models.CharField(max_length=20, blank=True, null=True)
    city = models.CharField(max_length=50, blank=True, null=True)
    state = models.CharField(max_length=50, blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'customers'


class OrderItems(models.Model):
    order_item_id = models.AutoField(primary_key=True)
    order = models.ForeignKey('Orders', models.DO_NOTHING)
    product = models.ForeignKey('Products', models.DO_NOTHING)
    quantity = models.IntegerField()
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        managed = False
        db_table = 'order_items'


class Orders(models.Model):
    order_id = models.AutoField(primary_key=True)
    customer = models.ForeignKey(Customers, models.DO_NOTHING)
    order_date = models.DateTimeField(blank=True, null=True)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    order_status = models.CharField(max_length=30, blank=True, null=True)
    shipping_addr = models.CharField(max_length=255, blank=True, null=True)
    delivery_date = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'orders'


class Payments(models.Model):
    payment_id = models.AutoField(primary_key=True)
    order = models.ForeignKey(Orders, models.DO_NOTHING)
    payment_method = models.CharField(max_length=30)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_date = models.DateTimeField(blank=True, null=True)
    payment_status = models.CharField(max_length=30, blank=True, null=True)
    transaction_id = models.CharField(max_length=100, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'payments'


class Products(models.Model):
    product_id = models.IntegerField(primary_key=True)
    seller = models.ForeignKey('Sellers', models.DO_NOTHING, blank=True, null=True)
    gender = models.CharField(max_length=20, blank=True, null=True)
    category = models.CharField(max_length=50, blank=True, null=True)
    sub_category = models.CharField(max_length=50, blank=True, null=True)
    product_type = models.CharField(max_length=50, blank=True, null=True)
    colour = models.CharField(max_length=30, blank=True, null=True)
    usage_type = models.CharField(max_length=50, blank=True, null=True)
    product_title = models.CharField(max_length=255, blank=True, null=True)
    image = models.CharField(max_length=255, blank=True, null=True)
    image_url = models.TextField(blank=True, null=True)
    brand = models.CharField(max_length=100, blank=True, null=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    stock_quantity = models.IntegerField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'products'


class Reviews(models.Model):
    review_id = models.AutoField(primary_key=True)
    customer = models.ForeignKey(Customers, models.DO_NOTHING)
    product = models.ForeignKey(Products, models.DO_NOTHING)
    rating = models.IntegerField()
    review_text = models.CharField(max_length=500, blank=True, null=True)
    review_date = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'reviews'


class Sellers(models.Model):
    seller_id = models.IntegerField(primary_key=True)
    seller_name = models.CharField(max_length=100)
    email = models.CharField(unique=True, max_length=100)
    password = models.CharField(max_length=255, blank=True, null=True)
    phone = models.CharField(max_length=15, blank=True, null=True)
    address = models.CharField(max_length=150, blank=True, null=True)
    rating = models.DecimalField(max_digits=2, decimal_places=1, blank=True, null=True)
    joined_date = models.DateField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'sellers'
class UserSessions(models.Model):
    session_id = models.AutoField(primary_key=True)

    customer = models.ForeignKey(
        'Customers',
        models.DO_NOTHING,
        db_column='customer_id'
    )

    start_time = models.DateTimeField()
    end_time = models.DateTimeField(blank=True, null=True)
    device_type = models.CharField(
        max_length=50,
        blank=True,
        null=True
    )

    class Meta:
        managed = False
        db_table = 'user_sessions'
class ProductViews(models.Model):
    view_id = models.AutoField(primary_key=True)

    customer = models.ForeignKey(
        'Customers',
        models.DO_NOTHING,
        db_column='customer_id'
    )

    product = models.ForeignKey(
        'Products',
        models.DO_NOTHING,
        db_column='product_id'
    )

    session = models.ForeignKey(
        'UserSessions',
        models.DO_NOTHING,
        db_column='session_id'
    )

    view_timestamp = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'product_views'
class CartEvents(models.Model):
    event_id = models.AutoField(primary_key=True)

    customer = models.ForeignKey(
        'Customers',
        models.DO_NOTHING,
        db_column='customer_id'
    )

    product = models.ForeignKey(
        'Products',
        models.DO_NOTHING,
        db_column='product_id'
    )

    cart = models.ForeignKey(
        'Cart',
        models.DO_NOTHING,
        db_column='cart_id',
        blank=True,
        null=True
    )

    event_type = models.CharField(max_length=30)

    event_timestamp = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'cart_events'
class FunnelEvents(models.Model):
    event_id = models.AutoField(primary_key=True)

    customer = models.ForeignKey(
        'Customers',
        models.DO_NOTHING,
        db_column='customer_id'
    )

    session = models.ForeignKey(
        'UserSessions',
        models.DO_NOTHING,
        db_column='session_id',
        blank=True,
        null=True
    )

    product = models.ForeignKey(
        'Products',
        models.DO_NOTHING,
        db_column='product_id',
        blank=True,
        null=True
    )

    event_stage = models.CharField(max_length=30)

    event_timestamp = models.DateTimeField()

    order = models.ForeignKey(
        'Orders',
        models.DO_NOTHING,
        db_column='order_id',
        blank=True,
        null=True
    )

    class Meta:
        managed = False
        db_table = 'funnel_events'
        

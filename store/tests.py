"""Automated tests for ShopSphere.

Run:  python manage.py test store -v 2

The test runner (store/test_runner.py) builds a separate database,
test_shopping_funnel, from database/01 ... 09, so the tests exercise the real
tables, CHECK/UNIQUE/FK constraints, triggers, views and stored procedures.
Your real shopping_funnel database is never touched. The MySQL login in
config/local_settings.py needs the CREATE / DROP privilege (root has it).

Each test runs in a transaction that is rolled back afterwards.
"""
from decimal import Decimal
from io import StringIO

from django.contrib.auth.models import User
from django.core.management import call_command
from django.db import IntegrityError, connection, transaction
from django.test import TestCase

from store.models import (Cart, CartEvents, Customers, FunnelEvents, OrderItems, Orders,
                          Payments, Products, ProductViews, Reviews, Sellers)

PASSWORD = 'pass123'


class ShopTestCase(TestCase):
    """Common data: the sample customer / seller / admin and one product in stock."""

    @classmethod
    def setUpTestData(cls):
        call_command('create_sample_data', stdout=StringIO())
        cls.customer = Customers.objects.get(email='customer@example.com')
        cls.seller = Sellers.objects.get(email='seller@example.com')
        cls.product = Products.objects.filter(stock_quantity__gte=5, price__isnull=False) \
                                      .order_by('product_id').first()

    def login_customer(self):
        r = self.client.post('/login/', {'email': 'customer@example.com', 'password': PASSWORD})
        self.assertEqual(r.status_code, 302)
        return r

    def stock(self, product=None):
        return Products.objects.get(pk=(product or self.product).pk).stock_quantity

    def place_order(self, qty=1):
        """Customer adds the product qty times and checks out. Returns the new order."""
        self.login_customer()
        for _ in range(qty):
            self.client.get(f'/cart/add/{self.product.pk}/')
        self.client.post('/checkout/', {'shipping_addr': '1 Test Street, Coimbatore'})
        return Orders.objects.filter(customer=self.customer).latest('order_id')


# ---------------------------------------------------------------------------
# 1. Database build: tables, triggers, views and procedures exist
# ---------------------------------------------------------------------------
class DatabaseBuildTests(ShopTestCase):
    def test_catalog_loaded(self):
        self.assertGreaterEqual(Sellers.objects.count(), 16)
        self.assertGreater(Products.objects.count(), 2900)

    def test_triggers_views_procedures_exist(self):
        with connection.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA = DATABASE()")
            self.assertEqual(cur.fetchone()[0], 4)
            cur.execute("SELECT COUNT(*) FROM information_schema.VIEWS WHERE TABLE_SCHEMA = DATABASE()")
            self.assertGreaterEqual(cur.fetchone()[0], 9)
            cur.execute("SELECT COUNT(*) FROM information_schema.ROUTINES "
                        "WHERE ROUTINE_SCHEMA = DATABASE() AND ROUTINE_TYPE = 'PROCEDURE'")
            self.assertEqual(cur.fetchone()[0], 3)


# ---------------------------------------------------------------------------
# 2. Constraints reject bad data
# ---------------------------------------------------------------------------
class ConstraintTests(ShopTestCase):
    def assertRejected(self, fn):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                fn()

    def test_review_rating_check(self):
        self.assertRejected(lambda: Reviews.objects.create(
            customer=self.customer, product=self.product, rating=6))

    def test_cart_quantity_check(self):
        self.assertRejected(lambda: Cart.objects.create(
            customer=self.customer, product=self.product, quantity=0))

    def test_unique_customer_email(self):
        self.assertRejected(lambda: Customers.objects.create(
            first_name='A', last_name='B', email='customer@example.com', password='x'))

    def test_order_status_check(self):
        self.assertRejected(lambda: Orders.objects.create(
            customer=self.customer, total_amount=10, order_status='Lost'))

    def test_foreign_key(self):
        self.assertRejected(lambda: Orders.objects.create(customer_id=99999999, total_amount=10))


# ---------------------------------------------------------------------------
# 3. Accounts and access control
# ---------------------------------------------------------------------------
class AccountTests(ShopTestCase):
    def test_register_hashes_password(self):
        r = self.client.post('/register/', {
            'first_name': 'Asha', 'last_name': 'K', 'email': 'asha@test.com',
            'password': 'secret123', 'confirm_password': 'secret123'})
        self.assertRedirects(r, '/login/', fetch_redirect_response=False)
        c = Customers.objects.get(email='asha@test.com')
        self.assertTrue(c.password.startswith('pbkdf2_'))     # never stored in plain text

    def test_register_validates_email(self):
        r = self.client.post('/register/', {
            'first_name': 'X', 'last_name': 'Y', 'email': 'admin',
            'password': 'secret123', 'confirm_password': 'secret123'})
        self.assertContains(r, 'valid email')
        r = self.client.post('/register/', {
            'first_name': 'X', 'last_name': 'Y', 'email': 'customer@example.com',
            'password': 'secret123', 'confirm_password': 'secret123'})
        self.assertContains(r, 'already exists')

    def test_wrong_password(self):
        r = self.client.post('/login/', {'email': 'customer@example.com', 'password': 'nope'})
        self.assertContains(r, 'Incorrect password')

    def test_login_creates_user_session(self):
        self.login_customer()
        self.assertIn('user_session_id', self.client.session)

    def test_protected_pages_redirect_to_login(self):
        for url, login in [('/orders/', '/login/'), ('/cart/', '/login/'),
                           ('/seller/dashboard/', '/seller/login/'),
                           ('/adminpanel/analytics/', '/adminpanel/login/')]:
            r = self.client.get(url)
            self.assertEqual(r.status_code, 302, url)
            self.assertTrue(r['Location'].startswith(login + '?next='), url)

    def test_next_cannot_redirect_to_other_site(self):
        r = self.client.post('/login/?next=https://evil.example.com/',
                             {'email': 'customer@example.com', 'password': PASSWORD})
        self.assertEqual(r['Location'], '/products/')

    def test_customer_is_not_admin(self):
        self.login_customer()
        r = self.client.get('/adminpanel/dashboard/')
        self.assertEqual(r.status_code, 302)


# ---------------------------------------------------------------------------
# 4. Shopping funnel: view -> cart -> checkout -> order -> payment -> review
# ---------------------------------------------------------------------------
class FunnelFlowTests(ShopTestCase):
    def test_public_pages(self):
        for url in ['/', '/products/', '/products/?gender=Men&sort=price_low',
                    f'/product/{self.product.pk}/', '/login/', '/register/']:
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_search_is_safe_from_sql_injection(self):
        r = self.client.get('/products/', {'q': "' OR 1=1 -- "})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context['page'].paginator.count, 0)

    def test_view_is_recorded(self):
        self.login_customer()
        self.client.get(f'/product/{self.product.pk}/')
        self.assertTrue(ProductViews.objects.filter(customer=self.customer, product=self.product).exists())
        self.assertTrue(FunnelEvents.objects.filter(customer_id=self.customer.pk,
                                                    product_id=self.product.pk, event_stage='VIEW').exists())

    def test_add_to_cart_is_recorded(self):
        self.login_customer()
        self.client.get(f'/cart/add/{self.product.pk}/')
        self.assertEqual(Cart.objects.get(customer=self.customer, product=self.product).quantity, 1)
        self.assertTrue(CartEvents.objects.filter(customer_id=self.customer.pk, event_type='ADD').exists())
        self.assertTrue(FunnelEvents.objects.filter(customer_id=self.customer.pk, event_stage='CART').exists())

    def test_checkout_creates_order_and_reduces_stock(self):
        before = self.stock()
        order = self.place_order(qty=2)
        item = OrderItems.objects.get(order=order)
        self.assertEqual(item.quantity, 2)
        self.assertEqual(item.subtotal, item.unit_price * 2)
        self.assertEqual(order.order_status, 'Pending')
        self.assertEqual(self.stock(), before - 2)                      # trigger
        self.assertFalse(Cart.objects.filter(customer=self.customer).exists())
        stages = set(FunnelEvents.objects.filter(order_id=order.pk).values_list('event_stage', flat=True))
        self.assertIn('ORDER', stages)

    def test_checkout_rolls_back_when_stock_runs_out(self):
        self.login_customer()
        self.client.get(f'/cart/add/{self.product.pk}/')
        self.client.get(f'/cart/add/{self.product.pk}/')
        Products.objects.filter(pk=self.product.pk).update(stock_quantity=1)   # sold elsewhere
        orders_before = Orders.objects.count()
        r = self.client.post('/checkout/', {'shipping_addr': '1 Test Street'})
        self.assertContains(r, 'Not enough stock')                        # SIGNAL from trigger
        self.assertEqual(Orders.objects.count(), orders_before)            # whole order rolled back
        self.assertEqual(self.stock(), 1)
        self.assertTrue(Cart.objects.filter(customer=self.customer).exists())

    def test_payment_marks_order_paid_and_logs_event(self):
        order = self.place_order()
        r = self.client.post(f'/payment/process/{order.pk}/', {'method': 'Card'})
        self.assertRedirects(r, '/orders/', fetch_redirect_response=False)
        order.refresh_from_db()
        self.assertEqual(order.order_status, 'Paid')
        pay = Payments.objects.get(order=order)
        self.assertEqual((pay.payment_status, pay.payment_method), ('Completed', 'Card'))
        self.assertTrue(FunnelEvents.objects.filter(order_id=order.pk, event_stage='PAYMENT').exists())

    def test_cannot_pay_twice(self):
        order = self.place_order()
        self.client.post(f'/payment/process/{order.pk}/', {'method': 'UPI'})
        self.client.post(f'/payment/process/{order.pk}/', {'method': 'UPI'})
        self.assertEqual(Payments.objects.filter(order=order).count(), 1)

    def test_cannot_pay_someone_elses_order(self):
        order = self.place_order()
        self.client.get('/logout/')
        User.objects.create_user('other@test.com', 'other@test.com', 'secret123')
        Customers.objects.create(first_name='O', last_name='T', email='other@test.com', password='x')
        self.client.post('/login/', {'email': 'other@test.com', 'password': 'secret123'})
        r = self.client.post(f'/payment/process/{order.pk}/', {'method': 'UPI'})
        self.assertEqual(r.status_code, 404)
        self.assertFalse(Payments.objects.filter(order=order).exists())

    def test_cancel_returns_stock(self):
        before = self.stock()
        order = self.place_order(qty=3)
        self.client.post(f'/order/{order.pk}/cancel/')
        order.refresh_from_db()
        self.assertEqual(order.order_status, 'Cancelled')
        self.assertEqual(self.stock(), before)

    def test_review_is_recorded(self):
        self.login_customer()
        self.client.post(f'/product/{self.product.pk}/review/', {'rating': 4, 'review_text': 'Nice'})
        self.assertTrue(Reviews.objects.filter(customer=self.customer, product=self.product, rating=4).exists())
        self.assertTrue(FunnelEvents.objects.filter(customer_id=self.customer.pk, event_stage='REVIEW').exists())

    def test_funnel_view_is_cumulative(self):
        order = self.place_order()
        self.client.post(f'/payment/process/{order.pk}/', {'method': 'UPI'})
        with connection.cursor() as cur:
            cur.execute("SELECT stage, customers FROM vw_funnel_summary ORDER BY stage_order")
            counts = dict(cur.fetchall())
        self.assertGreaterEqual(counts['PAYMENT'], 1)
        stages = ['VIEW', 'CART', 'CHECKOUT', 'ORDER', 'PAYMENT']
        for a, b in zip(stages, stages[1:]):
            self.assertGreaterEqual(counts[a], counts[b])     # a funnel never widens


# ---------------------------------------------------------------------------
# 5. Seller and admin
# ---------------------------------------------------------------------------
class SellerAdminTests(ShopTestCase):
    def test_seller_adds_product(self):
        self.client.post('/seller/login/', {'email': 'seller@example.com', 'password': PASSWORD})
        r = self.client.post('/seller/product/add/', {
            'product_id': 990001, 'product_title': 'Test Tee', 'brand': 'TestBrand',
            'gender': 'Men', 'category': 'Apparel', 'sub_category': 'Topwear',
            'product_type': 'Tshirts', 'colour': 'Blue', 'usage_type': 'Casual',
            'price': '499', 'stock_quantity': '10'})
        self.assertEqual(r.status_code, 302)
        p = Products.objects.get(pk=990001)
        self.assertEqual((p.seller_id, p.price), (self.seller.pk, Decimal('499.00')))

    def test_admin_pages_load(self):
        self.client.post('/adminpanel/login/', {'username': 'admin', 'password': 'adminpass'})
        for url in ['/adminpanel/dashboard/', '/adminpanel/customers/', '/adminpanel/sellers/',
                    '/adminpanel/products/', '/adminpanel/orders/', '/adminpanel/funnel/',
                    '/adminpanel/analytics/', f'/adminpanel/funnel/product/{self.product.pk}/']:
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_admin_order_status_flow(self):
        order = self.place_order()
        self.client.post(f'/payment/process/{order.pk}/', {'method': 'UPI'})
        self.client.post('/adminpanel/login/', {'username': 'admin', 'password': 'adminpass'})
        self.client.post(f'/adminpanel/order/{order.pk}/status/', {'status': 'Delivered'})  # skips Shipped
        order.refresh_from_db()
        self.assertEqual(order.order_status, 'Paid')
        r = self.client.post(f'/adminpanel/order/{order.pk}/status/',
                             {'status': 'Shipped', 'back': 'https://evil.example.com/'})
        order.refresh_from_db()
        self.assertEqual(order.order_status, 'Shipped')
        self.assertEqual(r['Location'], '/adminpanel/orders/')

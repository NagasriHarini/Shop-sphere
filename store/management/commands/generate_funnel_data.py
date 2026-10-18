"""
Generate realistic demo shoppers so the funnel reports have meaningful numbers.

    python manage.py generate_funnel_data                    # 300 customers, last 30 days
    python manage.py generate_funnel_data --customers 500 --days 60
    python manage.py generate_funnel_data --delete           # remove ALL demo data again

Every demo customer has an email ending in @demo.shop, so demo data can always
be told apart from real data and removed cleanly with --delete.
Demo customers can log in with password: demo1234

How a demo shopper behaves (one or more sessions on different days):
    VIEW      looks at 2-8 products (popular products are seen more often)
              ~60% of sessions are "just browsing" and rarely add anything
    CART      adds some of them to the cart          (~25% when shopping, higher for footwear)
    CHECKOUT  goes to checkout                       (~65% desktop, ~45% mobile)
    ORDER     places the order
    PAYMENT   pays                                   (~88%; the rest fail)
    REVIEW    reviews a bought product later         (~35%)
Carts that never reach checkout are left in the cart = abandoned carts.

All rows go through the normal tables, so the MySQL triggers fire exactly as
they do for real users: stock is checked and reduced, PAYMENT and REVIEW
funnel events are written by the database itself.
"""
import random
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.hashers import make_password
from django.core.management.base import BaseCommand
from django.db import DatabaseError, connection, transaction
from django.utils import timezone

from store.models import (Cart, CartEvents, Customers, FunnelEvents, OrderItems,
                          Orders, Payments, Products, ProductViews, Reviews,
                          UserSessions)

DEMO_DOMAIN = "@demo.shop"

FIRST_NAMES = ["Aarav", "Vivaan", "Aditya", "Vihaan", "Arjun", "Sai", "Reyansh", "Krishna",
               "Ishaan", "Rohan", "Karthik", "Rahul", "Nikhil", "Pranav", "Harsha", "Manoj",
               "Ananya", "Diya", "Aadhya", "Saanvi", "Pari", "Kavya", "Meera", "Sneha",
               "Divya", "Lakshmi", "Priya", "Swathi", "Keerthi", "Bhavana", "Nandini", "Riya"]
LAST_NAMES = ["Reddy", "Sharma", "Kumar", "Rao", "Naidu", "Iyer", "Nair", "Patel", "Gupta",
              "Verma", "Menon", "Pillai", "Chowdary", "Das", "Singh", "Joshi", "Krishnan"]
CITIES = [("Bengaluru", "Karnataka"), ("Chennai", "Tamil Nadu"), ("Coimbatore", "Tamil Nadu"),
          ("Hyderabad", "Telangana"), ("Vijayawada", "Andhra Pradesh"), ("Tirupati", "Andhra Pradesh"),
          ("Kochi", "Kerala"), ("Mumbai", "Maharashtra"), ("Pune", "Maharashtra"),
          ("Delhi", "Delhi"), ("Kolkata", "West Bengal"), ("Ahmedabad", "Gujarat")]
DEVICES = [("Mobile", 0.55), ("Desktop", 0.35), ("Tablet", 0.10)]
PAY_METHODS = ["UPI", "Card", "NetBanking", "COD"]
REVIEW_TEXT = {
    5: ["Excellent quality, totally worth it.", "Loved it! Fits perfectly.", "Great product, fast delivery."],
    4: ["Good product for the price.", "Nice, but size runs slightly small.", "Pretty good overall."],
    3: ["Average. Okay for daily use.", "Colour is a bit different from the photo."],
    2: ["Quality could be better.", "Not very comfortable."],
    1: ["Poor quality, would not buy again."],
}

# Behaviour knobs (probabilities)
P_SHOPPING_MOOD = 0.40          # share of sessions where the visitor intends to buy;
                                # the rest are "just browsing" and rarely add to cart
BROWSING_FACTOR = 0.12          # cart chance multiplier while just browsing
P_CART = {"Footwear": 0.30, "Apparel": 0.22}
P_CHECKOUT = {"Desktop": 0.65, "Tablet": 0.55, "Mobile": 0.45}
P_PAY_OK = 0.88
P_REVIEW = 0.35


def weighted_choice(rng, pairs):
    r, acc = rng.random(), 0.0
    for value, w in pairs:
        acc += w
        if r <= acc:
            return value
    return pairs[-1][0]


class Command(BaseCommand):
    help = "Generate (or --delete) demo shoppers and their funnel activity"

    def add_arguments(self, parser):
        parser.add_argument("--customers", type=int, default=300)
        parser.add_argument("--days", type=int, default=30)
        parser.add_argument("--seed", type=int, default=42, help="Same seed = same data")
        parser.add_argument("--delete", action="store_true", help="Remove all demo data")

    # ------------------------------------------------------------------
    def handle(self, *args, **o):
        if o["delete"]:
            self.delete_demo()
            return

        rng = random.Random(o["seed"])
        now = timezone.now().replace(microsecond=0)
        start = now - timedelta(days=o["days"])

        products = list(Products.objects.filter(price__isnull=False, price__lt=50000)
                        .values("product_id", "price", "category"))
        if not products:
            self.stderr.write("No products found.")
            return
        # Popularity: a few products get most of the attention (long tail)
        rng.shuffle(products)
        weights = [1.0 / (i + 1) ** 0.6 for i in range(len(products))]

        password_hash = make_password("demo1234")
        stats = dict(customers=0, sessions=0, views=0, carts=0, orders=0,
                     paid=0, failed=0, reviews=0, stock_blocked=0)

        next_no = Customers.objects.filter(email__endswith=DEMO_DOMAIN).count() + 1
        for n in range(o["customers"]):
            with transaction.atomic():
                self.make_customer(rng, next_no + n, start, now, products, weights,
                                   password_hash, stats)
            if (n + 1) % 50 == 0:
                self.stdout.write(f"  {n + 1} customers done...")

        self.stdout.write(self.style.SUCCESS(
            "Created {customers} customers, {sessions} sessions, {views} views, "
            "{carts} cart adds, {orders} orders ({paid} paid, {failed} failed payments), "
            "{reviews} reviews. Orders blocked by stock trigger: {stock_blocked}.".format(**stats)))

    # ------------------------------------------------------------------
    def make_customer(self, rng, no, start, now, products, weights, password_hash, stats):
        first, last = rng.choice(FIRST_NAMES), rng.choice(LAST_NAMES)
        city, state = rng.choice(CITIES)
        signup = start + timedelta(seconds=rng.randint(0, int((now - start).total_seconds() * 0.7)))
        cust = Customers.objects.create(
            first_name=first, last_name=last,
            email=f"{first.lower()}.{last.lower()}{no}{DEMO_DOMAIN}",
            password=password_hash,
            phone=f"9{rng.randint(100000000, 999999999)}",
            gender=rng.choice(["Male", "Female", "Other"]) if rng.random() < 0.97 else None,
            city=city, state=state, created_at=signup,
        )
        stats["customers"] += 1

        t = signup
        for _ in range(rng.choice([1, 1, 1, 2, 2, 3, 4])):
            if t >= now:
                break
            self.make_session(rng, cust, t, now, products, weights, stats)
            t += timedelta(days=rng.uniform(0.5, 7))

    # ------------------------------------------------------------------
    def make_session(self, rng, cust, t, now, products, weights, stats):
        device = weighted_choice(rng, DEVICES)
        sess = UserSessions.objects.create(customer=cust, start_time=t, device_type=device)
        stats["sessions"] += 1

        def tick(lo=15, hi=240):
            nonlocal t
            t += timedelta(seconds=rng.randint(lo, hi))
            return t

        shopping = rng.random() < P_SHOPPING_MOOD
        cart_factor = 1.0 if shopping else BROWSING_FACTOR

        # VIEW
        viewed = rng.choices(products, weights=weights, k=rng.randint(2, 8))
        carted = []
        for p in viewed:
            ts = tick()
            ProductViews.objects.create(customer=cust, product_id=p["product_id"],
                                        session=sess, view_timestamp=ts)
            FunnelEvents.objects.create(customer=cust, session=sess, product_id=p["product_id"],
                                        event_stage="VIEW", event_timestamp=ts)
            stats["views"] += 1

            # CART
            if rng.random() < P_CART.get(p["category"], 0.25) * cart_factor and \
                    p["product_id"] not in [c["product_id"] for c in carted]:
                ts = tick(10, 90)
                qty = rng.choice([1, 1, 1, 2])
                cart = Cart.objects.filter(customer=cust, product_id=p["product_id"]).first()
                if cart:
                    cart.quantity += qty
                    cart.save(update_fields=["quantity"])
                else:
                    cart = Cart.objects.create(customer=cust, product_id=p["product_id"],
                                               quantity=qty, added_date=ts)
                CartEvents.objects.create(customer=cust, product_id=p["product_id"], cart=cart,
                                          event_type="ADD", event_timestamp=ts)
                FunnelEvents.objects.create(customer=cust, session=sess, product_id=p["product_id"],
                                            event_stage="CART", event_timestamp=ts)
                carted.append({**p, "cart": cart, "qty": cart.quantity})
                stats["carts"] += 1

        sess.end_time = tick(30, 600)
        sess.save(update_fields=["end_time"])

        # CHECKOUT -> ORDER -> PAYMENT  (otherwise the cart is abandoned)
        if not carted or rng.random() >= P_CHECKOUT[device]:
            return

        ts = tick(60, 300)
        try:
            with transaction.atomic():           # savepoint: stock trigger may refuse
                for c in carted:
                    FunnelEvents.objects.create(customer=cust, session=sess, product_id=c["product_id"],
                                                event_stage="CHECKOUT", event_timestamp=ts)
                total = sum(Decimal(c["price"]) * c["qty"] for c in carted)
                order = Orders.objects.create(customer=cust, order_date=ts, total_amount=total,
                                              order_status="Pending",
                                              shipping_addr=f"{rng.randint(1, 250)}, Main Road, {cust.city}, {cust.state}")
                for c in carted:
                    OrderItems.objects.create(order=order, product_id=c["product_id"], quantity=c["qty"],
                                              unit_price=c["price"], subtotal=Decimal(c["price"]) * c["qty"])
                    FunnelEvents.objects.create(customer=cust, session=sess, product_id=c["product_id"],
                                                event_stage="ORDER", event_timestamp=ts, order=order)
                Cart.objects.filter(cart_id__in=[c["cart"].cart_id for c in carted]).delete()
        except DatabaseError:
            stats["stock_blocked"] += 1
            return
        stats["orders"] += 1

        pay_ts = tick(20, 180)
        ok = rng.random() < P_PAY_OK
        Payments.objects.create(order=order, payment_method=rng.choice(PAY_METHODS),
                                amount=order.total_amount, payment_date=pay_ts,
                                payment_status="Completed" if ok else "Failed",
                                transaction_id=f"DEMO{order.order_id}{rng.randint(100000, 999999)}")
        if not ok:
            stats["failed"] += 1
            return
        order.order_status = "Paid"
        order.delivery_date = pay_ts + timedelta(days=rng.randint(2, 7))
        order.save(update_fields=["order_status", "delivery_date"])
        stats["paid"] += 1

        # REVIEW (some days after delivery, only if that date has already passed)
        review_ts = order.delivery_date + timedelta(days=rng.randint(1, 5))
        if review_ts < now and rng.random() < P_REVIEW:
            c = rng.choice(carted)
            rating = weighted_choice(rng, [(5, 0.40), (4, 0.30), (3, 0.15), (2, 0.10), (1, 0.05)])
            Reviews.objects.create(customer=cust, product_id=c["product_id"], rating=rating,
                                   review_text=rng.choice(REVIEW_TEXT[rating]), review_date=review_ts)
            stats["reviews"] += 1

    # ------------------------------------------------------------------
    def delete_demo(self):
        ids = list(Customers.objects.filter(email__endswith=DEMO_DOMAIN)
                   .values_list("customer_id", flat=True))
        if not ids:
            self.stdout.write("No demo data found.")
            return
        with transaction.atomic():
            # Give back the stock that demo orders took
            with connection.cursor() as cur:
                placeholders = ",".join(["%s"] * len(ids))
                cur.execute(f"""
                    UPDATE products p
                    JOIN (SELECT oi.product_id, SUM(oi.quantity) AS qty
                          FROM order_items oi JOIN orders o ON o.order_id = oi.order_id
                          WHERE o.customer_id IN ({placeholders})
                          GROUP BY oi.product_id) d ON d.product_id = p.product_id
                    SET p.stock_quantity = p.stock_quantity + d.qty
                    WHERE p.stock_quantity IS NOT NULL""", ids)
            order_ids = list(Orders.objects.filter(customer_id__in=ids).values_list("order_id", flat=True))
            Reviews.objects.filter(customer_id__in=ids).delete()
            FunnelEvents.objects.filter(customer_id__in=ids).delete()
            Payments.objects.filter(order_id__in=order_ids).delete()
            OrderItems.objects.filter(order_id__in=order_ids).delete()
            Orders.objects.filter(order_id__in=order_ids).delete()
            CartEvents.objects.filter(customer_id__in=ids).delete()
            Cart.objects.filter(customer_id__in=ids).delete()
            ProductViews.objects.filter(customer_id__in=ids).delete()
            UserSessions.objects.filter(customer_id__in=ids).delete()
            Customers.objects.filter(customer_id__in=ids).delete()
        self.stdout.write(self.style.SUCCESS(f"Deleted {len(ids)} demo customers and all their activity "
                                             f"(stock restored)."))

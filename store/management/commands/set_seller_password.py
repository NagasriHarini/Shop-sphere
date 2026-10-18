"""
Set a login password for a seller (or for every seller).

    python manage.py set_seller_password trendstyle@gmail.com seller123
    python manage.py set_seller_password --all seller123      # every seller in the sellers table

Updates both the sellers table (hashed) and the matching Django login,
so the seller can sign in at /seller/login/ straight away.
"""
from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from store.models import Sellers


class Command(BaseCommand):
    help = "Set a seller's login password"

    def add_arguments(self, parser):
        parser.add_argument("email", nargs="?", help="seller email (omit with --all)")
        parser.add_argument("password")
        parser.add_argument("--all", action="store_true", help="set this password for every seller")

    def handle(self, *args, **o):
        password = o["password"]
        if len(password) < 6:
            raise CommandError("Use at least 6 characters.")

        if o["all"]:
            sellers = list(Sellers.objects.all())
        else:
            if not o["email"]:
                raise CommandError("Give a seller email, or use --all.")
            sellers = list(Sellers.objects.filter(email__iexact=o["email"]))
            if not sellers:
                emails = ", ".join(Sellers.objects.values_list("email", flat=True)[:20])
                raise CommandError(f"No seller with email {o['email']}. Seller emails: {emails}")

        hashed = make_password(password)
        with transaction.atomic():
            for s in sellers:
                s.password = hashed
                s.save(update_fields=["password"])
                user, _ = User.objects.get_or_create(
                    username=s.email, defaults={"email": s.email, "first_name": s.seller_name[:150]})
                user.password = hashed
                user.save(update_fields=["password"])
                self.stdout.write(f"  {s.seller_name:25} {s.email}")
        self.stdout.write(self.style.SUCCESS(f"Password set for {len(sellers)} seller(s)."))

"""
Hash every plain-text password in customers, sellers and admin.

    python manage.py hash_plain_passwords            # do it
    python manage.py hash_plain_passwords --dry-run  # only show what would change

For each account whose stored password is not already a Django hash:
  * the table's password column gets a pbkdf2 hash (same format Django uses),
  * a matching Django auth user is created/updated with that same hash,
    so login keeps working with the same password as before.
Rows with an empty password (e.g. sellers who never set one) are skipped.
"""
from django.contrib.auth.hashers import make_password, identify_hasher
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import transaction

from store.models import Admin, Customers, Sellers


def is_hashed(value):
    try:
        identify_hasher(value)
        return True
    except Exception:
        return False


class Command(BaseCommand):
    help = "Hash plain-text passwords in customers, sellers and admin tables"

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true",
                            help="List affected accounts without changing anything")

    def handle(self, *args, **opts):
        dry = opts["dry_run"]
        groups = [
            ("customer", Customers.objects.all(), lambda o: o.email, lambda o: o.first_name, lambda o: o.last_name),
            ("seller",   Sellers.objects.all(),   lambda o: o.email, lambda o: o.seller_name, lambda o: ""),
            ("admin",    Admin.objects.all(),     lambda o: o.username, lambda o: "Admin", lambda o: ""),
        ]
        changed = 0
        with transaction.atomic():
            for kind, qs, username_of, first_of, last_of in groups:
                for obj in qs:
                    pw = obj.password
                    if not pw or is_hashed(pw):
                        continue
                    username = username_of(obj)
                    self.stdout.write(f"  {kind:8} {username}")
                    changed += 1
                    if dry:
                        continue
                    hashed = make_password(pw)
                    obj.password = hashed
                    obj.save(update_fields=["password"])

                    user, _ = User.objects.get_or_create(
                        username=username,
                        defaults={"email": getattr(obj, "email", "") or "",
                                  "first_name": first_of(obj)[:150],
                                  "last_name": last_of(obj)[:150]},
                    )
                    user.password = hashed
                    user.save(update_fields=["password"])
            if dry:
                transaction.set_rollback(True)

        verb = "would be hashed" if dry else "hashed"
        self.stdout.write(self.style.SUCCESS(f"{changed} password(s) {verb}."))

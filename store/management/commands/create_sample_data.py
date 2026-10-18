from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.utils import timezone
from django.db.models import Max

from store.models import Customers, Sellers, Admin


class Command(BaseCommand):
    help = 'Create sample customer, seller and admin accounts for testing'

    def handle(self, *args, **options):
        # Customer
        cust_email = 'customer@example.com'
        cust_pass = 'pass123'
        cust_first = 'Test'
        cust_last = 'Customer'

        user, created = User.objects.get_or_create(username=cust_email, defaults={'email': cust_email, 'first_name': cust_first, 'last_name': cust_last})
        if created:
            user.set_password(cust_pass)
            user.save()

        cust_obj, ccreated = Customers.objects.get_or_create(email=cust_email, defaults={
            'first_name': cust_first,
            'last_name': cust_last,
            'password': user.password,
            'phone': '1234567890',
            'gender': 'Other',
            'city': 'City',
            'state': 'State',
            'created_at': timezone.now()
        })

        # Seller
        seller_email = 'seller@example.com'
        seller_pass = 'pass123'
        seller_name = 'Test Seller'

        suser, screated = User.objects.get_or_create(username=seller_email, defaults={'email': seller_email, 'first_name': seller_name})
        if screated:
            suser.set_password(seller_pass)
            suser.save()

        # determine next seller_id (model uses IntegerField primary key)
        max_id = Sellers.objects.aggregate(max_id=Max('seller_id'))['max_id']
        next_id = (max_id or 0) + 1

        seller_obj, sold = Sellers.objects.get_or_create(email=seller_email, defaults={
            'seller_id': next_id,
            'seller_name': seller_name,
            'password': suser.password,
            'phone': '0987654321',
            'address': 'Seller Address',
            'joined_date': timezone.now().date()
        })

        # Admin
        admin_username = 'admin'
        admin_pass = 'adminpass'
        admin_email = 'admin@example.com'

        auser, acreated = User.objects.get_or_create(username=admin_username, defaults={'email': admin_email, 'first_name': 'Admin'})
        if acreated:
            auser.set_password(admin_pass)
            auser.is_staff = True
            auser.is_superuser = True
            auser.save()

        admin_obj, acreated2 = Admin.objects.get_or_create(username=admin_username, defaults={
            'password': auser.password,
            'email': admin_email
        })

        self.stdout.write(self.style.SUCCESS('Sample accounts created/verified:'))
        self.stdout.write(f' Customer: email={cust_email} password={cust_pass}')
        self.stdout.write(f' Seller: email={seller_email} password={seller_pass}')
        self.stdout.write(f' Admin: username={admin_username} password={admin_pass}')

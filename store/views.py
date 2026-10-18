from django.shortcuts import render, get_object_or_404, redirect
from .models import Products, Customers, Cart, Orders, OrderItems, Sellers, Reviews, Payments, Admin,UserSessions,ProductViews,CartEvents,FunnelEvents
from django.contrib.auth.hashers import make_password, check_password
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.contrib.auth.models import User
from django.utils import timezone
from django.template import RequestContext
from django.db import IntegrityError, DatabaseError, transaction
from django.contrib import messages
from django.core.paginator import Paginator
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from django.db.models import Q, Avg, F
from decimal import Decimal, InvalidOperation
import os
from django.conf import settings
from django.http import FileResponse, HttpResponse, Http404
from django.db.models import Count




# ---------------------------------------------------------------------
# Login redirects: send people back to the page they were on
# ---------------------------------------------------------------------
from urllib.parse import urlencode, urlparse
from django.utils.http import url_has_allowed_host_and_scheme


def _to_login(request, login_url):
    """Redirect to a login page, remembering where the visitor was going."""
    if request.method == 'GET':
        target = request.get_full_path()
    else:   # a POST (e.g. a review form): go back to the page the form was on
        ref = urlparse(request.META.get('HTTP_REFERER', ''))
        target = ref.path if ref.path and ref.netloc in ('', request.get_host()) else ''
    if target and target != login_url:
        return redirect(f"{login_url}?{urlencode({'next': target})}")
    return redirect(login_url)


def _next_url(request, default):
    """The safe 'next' page after logging in, or the default."""
    nxt = request.POST.get('next') or request.GET.get('next')
    if nxt and url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()},
                                               require_https=request.is_secure()):
        return nxt
    return default

_IMAGE_DIRS = None


def _image_dirs():
    global _IMAGE_DIRS
    if _IMAGE_DIRS is None:
        root = os.path.join(settings.BASE_DIR, 'datasets')
        dirs = []
        for dirpath, dirnames, filenames in os.walk(root):
            if any(f.lower().endswith('.jpg') for f in filenames):
                dirs.append(dirpath)
        _IMAGE_DIRS = dirs
    return _IMAGE_DIRS


def product_image(request, product_id):
    """Serve a product photo from datasets/<Category>/<Gender>/Images/...;
    fall back to the stored image_url, then to a neutral placeholder."""
    for d in _image_dirs():
        path = os.path.join(d, f'{product_id}.jpg')
        if os.path.exists(path):
            resp = FileResponse(open(path, 'rb'), content_type='image/jpeg')
            resp['Cache-Control'] = 'public, max-age=86400'
            return resp
    product = Products.objects.filter(product_id=product_id).first()
    if product and product.image_url and product.image_url.startswith('http'):
        return redirect(product.image_url)
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 400">'
           '<rect width="400" height="400" fill="#eef0f6"/>'
           '<path d="M140 250l50-60 40 45 30-35 50 50z" fill="#c9cede"/>'
           '<circle cx="250" cy="150" r="22" fill="#c9cede"/></svg>')
    return HttpResponse(svg, content_type='image/svg+xml')


def products(request):
    qs = Products.objects.all()

    q = request.GET.get('q', '').strip()
    gender = request.GET.get('gender', '')
    category = request.GET.get('category', '')
    sort = request.GET.get('sort', '')

    if q:
        qs = qs.filter(Q(product_title__icontains=q) | Q(brand__icontains=q) |
                       Q(product_type__icontains=q) | Q(colour__icontains=q))
    if gender:
        qs = qs.filter(gender=gender)
    if category:
        qs = qs.filter(category=category)

    qs = qs.order_by({'price_asc': 'price', 'price_desc': '-price',
                      'name': 'product_title'}.get(sort, 'product_id'))

    page = Paginator(qs, 24).get_page(request.GET.get('page'))

    params = request.GET.copy()
    params.pop('page', None)

    error = None
    if request.GET.get('error') == 'notfound':
        error = 'Product not found. Please choose another item.'

    return render(request, 'store/products.html', {
        'products': page,
        'page': page,
        'total': qs.count(),
        'q': q, 'gender': gender, 'category': category, 'sort': sort,
        'genders': ['Men', 'Women', 'Boys', 'Girls'],
        'categories': ['Footwear', 'Apparel'],
        'querystring': params.urlencode(),
        'error': error,
    })


def index(request):
    featured = (Products.objects.filter(stock_quantity__gt=0, price__lt=10000)
                .order_by('?')[:8])
    return render(request, 'store/index.html', {
        'featured': featured,
        'product_count': Products.objects.count(),
        'brand_count': Products.objects.values('brand').distinct().count(),
        'seller_count': Sellers.objects.count(),
    })


def orders_view(request):
    if 'customer_id' not in request.session:
        return _to_login(request, '/login/')

    customer_id = request.session['customer_id']

    orders = Orders.objects.filter(
        customer_id=customer_id
    ).order_by('-order_date')

    for order in orders:
        order.items_list = OrderItems.objects.filter(
            order_id=order.order_id
        ).select_related('product')

    return render(
        request,
        'store/orders.html',
        {'orders': orders}
    )

def product_detail(request, product_id):
    product = Products.objects.filter(product_id=product_id).first()
    if not product:
        return redirect('/products/?error=notfound')

    if 'customer_id' in request.session and 'user_session_id' in request.session:
        try:
            with transaction.atomic():
                ProductViews.objects.create(
                    customer_id=request.session['customer_id'],
                    product_id=product_id,
                    session_id=request.session['user_session_id'],
                    view_timestamp=timezone.now()
                )
                FunnelEvents.objects.create(
                    customer_id=request.session['customer_id'],
                    session_id=request.session['user_session_id'],
                    product_id=product_id,
                    event_stage='VIEW',
                    event_timestamp=timezone.now()
                )
        except Exception:
            pass

    reviews = Reviews.objects.filter(product_id=product_id) \
                             .select_related('customer').order_by('-review_date')
    avg = reviews.aggregate(a=Avg('rating'))['a']
    related = (Products.objects.filter(category=product.category, gender=product.gender,
                                       stock_quantity__gt=0)
               .exclude(product_id=product_id).order_by('?')[:4])

    return render(request, 'store/product_detail.html', {
        'product': product,
        'reviews': reviews,
        'avg_rating': round(avg, 1) if avg else None,
        'related': related,
    })


def submit_review(request, product_id):
    if request.method != 'POST':
        return redirect('product_detail', product_id=product_id)
    if 'customer_id' not in request.session:
        return _to_login(request, '/login/')

    try:
        rating = int(request.POST.get('rating', 5))
    except (TypeError, ValueError):
        rating = 0
    if not 1 <= rating <= 5:
        messages.error(request, 'Please choose a rating from 1 to 5.')
        return redirect('product_detail', product_id=product_id)

    try:
        Reviews.objects.create(
            customer_id=request.session['customer_id'],
            product_id=product_id,
            rating=rating,
            review_text=request.POST.get('review_text', '')[:500],
            review_date=timezone.now()
        )
        messages.success(request, 'Thanks! Your review was posted.')
    except Exception:
        messages.error(request, 'Could not save your review.')

    return redirect('product_detail', product_id=product_id)


def register(request):
    if request.method == 'POST':

        first_name = request.POST['first_name'].strip()
        last_name = request.POST['last_name'].strip()
        email = request.POST['email'].strip().lower()
        password = request.POST['password']
        confirm_password = request.POST.get('confirm_password', '')
        phone = request.POST.get('phone')
        gender = request.POST.get('gender') or None
        city = request.POST.get('city')
        state = request.POST.get('state')

        # 1. Check if passwords match
        if password != confirm_password:
            return render(
                request,
                'store/register.html',
                {'error': 'Passwords do not match.'}
            )

        # 2. Check minimum password length
        if len(password) < 8:
            return render(
                request,
                'store/register.html',
                {'error': 'Password must be at least 8 characters long.'}
            )

        # 3. Email must be a real address
        try:
            validate_email(email)
        except ValidationError:
            return render(
                request,
                'store/register.html',
                {'error': 'Please enter a valid email address.'}
            )

        # 4. Email must not belong to ANY existing login (customer, seller or admin).
        #    Previously an existing login's password was reset here, which let anyone
        #    take over the admin or a seller account by "registering" with its name.
        if Customers.objects.filter(email__iexact=email).exists() or \
                User.objects.filter(username__iexact=email).exists():
            return render(
                request,
                'store/register.html',
                {'error': 'An account with this email already exists. Please log in.'}
            )

        # Create the Django login and the customer row together
        try:
            with transaction.atomic():
                user = User.objects.create_user(
                    username=email, email=email, password=password,
                    first_name=first_name, last_name=last_name
                )
                Customers.objects.create(
                    first_name=first_name,
                    last_name=last_name,
                    email=email,
                    password=user.password,
                    phone=phone,
                    gender=gender,
                    city=city,
                    state=state,
                    created_at=timezone.now()
                )
        except IntegrityError:
            return render(
                request,
                'store/register.html',
                {'error': 'An account with this email already exists. Please log in.'}
            )

        messages.success(request, 'Account created. Please log in.')
        nxt = _next_url(request, '')
        return redirect(f"/login/?{urlencode({'next': nxt})}" if nxt else '/login/')

    return render(request, 'store/register.html')

def profile(request):
    customer_id = request.session.get('customer_id')

    if not customer_id:
        return _to_login(request, '/login/')

    customer = Customers.objects.get(
        customer_id=customer_id
    )

    return render(
        request,
        'store/profile.html',
        {'customer': customer}
    )

def cart_view(request):
    if 'customer_id' not in request.session:
        return _to_login(request, '/login/')

    customer_id = request.session['customer_id']

    cart_items = Cart.objects.filter(
        customer_id=customer_id
    ).select_related('product')

    total = 0

    for item in cart_items:
        item.line_total = (item.product.price or 0) * item.quantity
        total += item.line_total

    return render(
        request,
        'store/cart.html',
        {
            'cart_items': cart_items,
            'total': total
        }
    )


def login_view(request):
    if request.method == 'POST':
        email = request.POST['email']
        password = request.POST['password']

        # Prefer Django auth
        user = authenticate(request, username=email, password=password)

        if user is not None:
            auth_login(request, user)

            try:
                customer = Customers.objects.get(email=email)

                request.session['customer_id'] = customer.customer_id
                request.session['customer_name'] = customer.first_name

                # CREATE USER SESSION
                user_session = UserSessions.objects.create(
                    customer=customer,
                    start_time=timezone.now(),
                    device_type='Desktop'
                )

                request.session['user_session_id'] = user_session.session_id

            except Customers.DoesNotExist:
                auth_logout(request)
                return render(request, 'store/login.html',
                              {'error': 'This is not a customer account.'})

            return redirect(_next_url(request, '/products/'))

        # Fallback: legacy plaintext password
        try:
            customer = Customers.objects.get(email=email)

            stored = customer.password or ''
            if stored.startswith('pbkdf2_'):
                password_ok = check_password(password, stored)
            else:
                password_ok = (stored == password)   # legacy plain text

            if password_ok:

                # Create Django user
                u, created = User.objects.get_or_create(
                    username=email,
                    defaults={
                        'email': email,
                        'first_name': customer.first_name,
                        'last_name': customer.last_name
                    }
                )

                u.set_password(password)
                u.save()

                # Update stored password
                customer.password = u.password
                customer.save()

                auth_login(request, u)

                request.session['customer_id'] = customer.customer_id
                request.session['customer_name'] = customer.first_name

                # CREATE USER SESSION
                user_session = UserSessions.objects.create(
                    customer=customer,
                    start_time=timezone.now(),
                    device_type='Desktop'
                )

                request.session['user_session_id'] = user_session.session_id

                return redirect(_next_url(request, '/products/'))

            else:
                return render(
                    request,
                    'store/login.html',
                    {'error': 'Incorrect password'}
                )

        except Customers.DoesNotExist:
            return render(
                request,
                'store/login.html',
                {'error': 'Customer does not exist'}
            )

    return render(request, 'store/login.html')
def add_to_cart(request, product_id):
    if 'customer_id' not in request.session:
        return _to_login(request, '/login/')

    customer_id = request.session['customer_id']
    product = Products.objects.filter(product_id=product_id).first()
    if not product:
        return redirect('/products/?error=notfound')

    cart_item = Cart.objects.filter(customer_id=customer_id, product=product).first()
    wanted = (cart_item.quantity if cart_item else 0) + 1
    if product.stock_quantity is not None and product.stock_quantity < wanted:
        messages.error(request, f'Sorry, only {product.stock_quantity} of "{product.product_title}" left in stock.')
        return redirect('product_detail', product_id=product_id)

    if cart_item:
        cart_item.quantity += 1
        cart_item.save()
    else:
        cart_item = Cart.objects.create(customer_id=customer_id, product=product,
                                        quantity=1, added_date=timezone.now())

    try:
        with transaction.atomic():
            CartEvents.objects.create(customer_id=customer_id, product_id=product_id,
                                      cart_id=cart_item.cart_id, event_type='ADD',
                                      event_timestamp=timezone.now())
            if request.session.get('user_session_id'):
                FunnelEvents.objects.create(customer_id=customer_id,
                                            session_id=request.session['user_session_id'],
                                            product_id=product_id, event_stage='CART',
                                            event_timestamp=timezone.now())
    except Exception:
        pass

    messages.success(request, f'Added "{product.product_title}" to your cart.')
    return redirect('/cart/')


def increase_cart(request, cart_id):
    if 'customer_id' not in request.session:
        return _to_login(request, '/login/')

    cart_item = Cart.objects.filter(cart_id=cart_id,
                                    customer_id=request.session['customer_id']) \
                            .select_related('product').first()
    if not cart_item:
        return redirect('/cart/')

    product = cart_item.product
    if product.stock_quantity is not None and cart_item.quantity + 1 > product.stock_quantity:
        messages.error(request, f'Only {product.stock_quantity} in stock.')
        return redirect('/cart/')
    cart_item.quantity += 1
    cart_item.save()
    try:
        with transaction.atomic():
            CartEvents.objects.create(
                customer_id=request.session['customer_id'],
                product_id=cart_item.product_id,
                cart_id=cart_item.cart_id,
                event_type='INCREASE',
                event_timestamp=timezone.now()
            )
    except Exception:
        pass

    return redirect('/cart/')


def decrease_cart(request, cart_id):
    if 'customer_id' not in request.session:
        return _to_login(request, '/login/')

    cart_item = Cart.objects.filter(cart_id=cart_id,
                                    customer_id=request.session['customer_id']) \
                            .select_related('product').first()
    if not cart_item:
        return redirect('/cart/')

    if cart_item.quantity <= 1:
        return redirect('/cart/')
    cart_item.quantity -= 1
    cart_item.save()
    try:
        with transaction.atomic():
            CartEvents.objects.create(
                customer_id=request.session['customer_id'],
                product_id=cart_item.product_id,
                cart_id=cart_item.cart_id,
                event_type='DECREASE',
                event_timestamp=timezone.now()
            )
    except Exception:
        pass

    return redirect('/cart/')


def remove_from_cart(request, cart_id):
    if 'customer_id' not in request.session:
        return _to_login(request, '/login/')

    cart_item = Cart.objects.filter(cart_id=cart_id,
                                    customer_id=request.session['customer_id']) \
                            .select_related('product').first()
    if not cart_item:
        return redirect('/cart/')


    try:
        with transaction.atomic():
            CartEvents.objects.create(
                customer_id=request.session['customer_id'],
                product_id=cart_item.product_id,
                cart_id=cart_item.cart_id,
                event_type='REMOVE',
                event_timestamp=timezone.now()
            )
    except Exception:
        pass

    cart_item.delete()
    return redirect('/cart/')


def checkout(request):
    if 'customer_id' not in request.session:
        return _to_login(request, '/login/')

    customer_id = request.session['customer_id']

    cart_items = Cart.objects.filter(
        customer_id=customer_id
    ).select_related('product')

    if not cart_items.exists():
        return redirect('/cart/')

    total = 0

    for item in cart_items:
        if item.product.price:
            total += item.product.price * item.quantity

    if request.method == 'POST':
        shipping_addr = request.POST.get('shipping_addr', '').strip()
        if not shipping_addr:
            return render(request, 'store/checkout.html', {
                'cart_items': cart_items, 'total': total,
                'error': 'Please enter a shipping address.'})

        cart_items_list = list(cart_items)
        cart_ids = [item.cart_id for item in cart_items_list]
        user_session_id = request.session.get('user_session_id')

        # Whole order is one transaction: if the stock trigger rejects any
        # item, the order, its items and the cart changes are all rolled back.
        try:
            with transaction.atomic():
                if user_session_id:
                    for item in cart_items_list:
                        FunnelEvents.objects.create(
                            customer_id=customer_id,
                            session_id=user_session_id,
                            product_id=item.product_id,
                            event_stage='CHECKOUT',
                            event_timestamp=timezone.now()
                        )

                order = Orders.objects.create(
                    customer_id=customer_id,
                    order_date=timezone.now(),
                    total_amount=total,
                    order_status='Pending',
                    shipping_addr=shipping_addr
                )

                for item in cart_items_list:
                    # DB triggers check stock and reduce it on this insert
                    OrderItems.objects.create(
                        order=order,
                        product=item.product,
                        quantity=item.quantity,
                        unit_price=item.product.price,
                        subtotal=item.product.price * item.quantity
                    )

                    if user_session_id:
                        FunnelEvents.objects.create(
                            customer_id=customer_id,
                            session_id=user_session_id,
                            product_id=item.product_id,
                            event_stage='ORDER',
                            event_timestamp=timezone.now(),
                            order_id=order.order_id
                        )

                # cart_events.cart_id is ON DELETE SET NULL, so cart history is kept
                cart_items.delete()

        except DatabaseError as e:
            # e.g. "Not enough stock for ..." raised by trg_order_items_before_insert
            msg = e.args[1] if len(e.args) > 1 else str(e)
            return render(request, 'store/checkout.html', {
                'cart_items': cart_items,
                'total': total,
                'error': msg,
            })

        # Redirect to simulated payment page
        return redirect(f'/payment/{order.order_id}/')

    return render(
        request,
        'store/checkout.html',
        {
            'cart_items': cart_items,
            'total': total
        }
    )
def order_detail(request, order_id):
    if 'customer_id' not in request.session:
        return _to_login(request, '/login/')

    customer_id = request.session['customer_id']

    order = get_object_or_404(
        Orders,
        order_id=order_id,
        customer_id=customer_id
    )

    items = OrderItems.objects.filter(
        order_id=order_id
    ).select_related('product')

    return render(
        request,
        'store/order_detail.html',
        {
            'order': order,
            'items': items
        }
    )
    
def seller_login(request):

    if request.method == 'POST':

        email = request.POST['email']
        password = request.POST['password']

        # Prefer Django auth
        user = authenticate(request, username=email, password=password)
        if user is not None:
            auth_login(request, user)
            try:
                seller = Sellers.objects.get(email=email)
                request.session['seller_id'] = seller.seller_id
                request.session['seller_name'] = seller.seller_name
            except Sellers.DoesNotExist:
                auth_logout(request)
                return render(request, 'store/seller_login.html',
                              {'error': 'This is not a seller account.'})

            return redirect(_next_url(request, '/seller/dashboard/'))

        # Fallback: legacy plaintext password check and migrate
        try:
            seller = Sellers.objects.get(email=email)
            if seller.password == password:
                u, created = User.objects.get_or_create(username=email, defaults={'email': email, 'first_name': seller.seller_name})
                u.set_password(password)
                u.save()
                seller.password = u.password
                seller.save()

                auth_login(request, u)
                request.session['seller_id'] = seller.seller_id
                request.session['seller_name'] = seller.seller_name

                return redirect(_next_url(request, '/seller/dashboard/'))
            else:
                return render(request, 'store/seller_login.html', {'error': 'Invalid email or password'})
        except Sellers.DoesNotExist:
            return render(request, 'store/seller_login.html', {'error': 'Invalid email or password'})

    return render(
        request,
        'store/seller_login.html'
    )
def seller_dashboard(request):
    if 'seller_id' not in request.session:
        return _to_login(request, '/seller/login/')

    seller_id = request.session['seller_id']
    seller = Sellers.objects.filter(seller_id=seller_id).first()
    if not seller:
        request.session.pop('seller_id', None)
        return _to_login(request, '/seller/login/')

    q = request.GET.get('q', '').strip()
    qs = Products.objects.filter(seller_id=seller_id).order_by('-product_id')
    if q:
        qs = qs.filter(Q(product_title__icontains=q) | Q(brand__icontains=q))
    page = Paginator(qs, 20).get_page(request.GET.get('page'))

    sales = _rows("SELECT * FROM vw_seller_sales WHERE seller_id = %s", [seller_id])
    return render(request, 'store/seller_dashboard.html', {
        'seller': seller,
        'products': page, 'page': page, 'q': q,
        'sales': sales[0] if sales else {},
        'low_stock': Products.objects.filter(seller_id=seller_id, stock_quantity__lte=5).count(),
        'querystring': _page_params(request),
    })


PRODUCT_TEXT_FIELDS = ['gender', 'category', 'sub_category', 'product_type', 'colour',
                       'usage_type', 'product_title', 'image', 'image_url', 'brand']


def _clean_product_form(post, need_id):
    """Validate the add/edit product form. Returns (data, error)."""
    data = {f: (post.get(f) or '').strip() or None for f in PRODUCT_TEXT_FIELDS if f in post}
    if need_id:
        raw = (post.get('product_id') or '').strip()
        if raw:
            if not raw.isdigit():
                return None, 'Product ID must be a whole number.'
            pid = int(raw)
        else:   # leave blank = next free id
            last = Products.objects.order_by('-product_id').first()
            pid = (last.product_id + 1) if last else 1
        if Products.objects.filter(product_id=pid).exists():
            return None, f'Product ID {pid} is already used.'
        data['product_id'] = pid
    try:
        price = (post.get('price') or '').strip()
        data['price'] = Decimal(price) if price else None
        if data['price'] is not None and data['price'] < 0:
            return None, 'Price cannot be negative.'
    except InvalidOperation:
        return None, 'Price must be a number.'
    stock = (post.get('stock_quantity') or '').strip()
    if stock and not stock.isdigit():
        return None, 'Stock must be a whole number (0 or more).'
    data['stock_quantity'] = int(stock) if stock else None
    if 'seller_id' in post:
        sid = (post.get('seller_id') or '').strip()
        if sid and (not sid.isdigit() or not Sellers.objects.filter(seller_id=int(sid)).exists()):
            return None, 'No seller with that ID.'
        data['seller_id'] = int(sid) if sid else None
    if not data.get('product_title') and need_id:
        return None, 'Please enter a product title.'
    return data, None


def _delete_or_retire(request, product):
    """Products that were ordered / reviewed can't be deleted (foreign keys keep the
    history). In that case take them off sale (stock 0) instead of crashing."""
    try:
        with transaction.atomic():
            product.delete()
        messages.success(request, f'Deleted "{product.product_title}".')
    except IntegrityError:
        product.stock_quantity = 0
        product.save(update_fields=['stock_quantity'])
        messages.warning(request, f'"{product.product_title}" has order or review history, so it was '
                                  f'taken off sale (stock set to 0) instead of deleted.')


def seller_add_product(request):
    if 'seller_id' not in request.session:
        return _to_login(request, '/seller/login/')

    if request.method == 'POST':
        data, error = _clean_product_form(request.POST, need_id=True)
        if error:
            return render(request, 'store/seller_add_product.html',
                          {'error': error, 'form': request.POST})
        data['seller_id'] = request.session['seller_id']
        Products.objects.create(**data)
        messages.success(request, 'Product added.')
        return redirect('/seller/dashboard/')

    return render(request, 'store/seller_add_product.html', {'form': {}})


def seller_update_product(request, product_id):
    if 'seller_id' not in request.session:
        return _to_login(request, '/seller/login/')

    product = Products.objects.filter(product_id=product_id,
                                      seller_id=request.session['seller_id']).first()
    if not product:
        return redirect('/seller/dashboard/')

    if request.method == 'POST':
        data, error = _clean_product_form(request.POST, need_id=False)
        if error:
            return render(request, 'store/seller_update_product.html',
                          {'product': product, 'error': error, 'form': {}})
        data.pop('seller_id', None)
        for k, v in data.items():
            setattr(product, k, v)
        product.save()
        messages.success(request, 'Product updated.')
        return redirect('/seller/dashboard/')

    return render(request, 'store/seller_update_product.html', {'product': product, 'form': {}})


def seller_delete_product(request, product_id):
    if 'seller_id' not in request.session:
        return _to_login(request, '/seller/login/')
    product = Products.objects.filter(product_id=product_id,
                                      seller_id=request.session['seller_id']).first()
    if product and request.method == 'POST':
        _delete_or_retire(request, product)
    return redirect('/seller/dashboard/')


def seller_logout(request):
    auth_logout(request)
    request.session.pop('seller_id', None)
    request.session.pop('seller_name', None)
    return redirect('/seller/login/')


def admin_login(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')

        # Prefer Django auth
        user = authenticate(request, username=username, password=password)
        if user is not None:
            auth_login(request, user)
            try:
                admin = Admin.objects.get(username=username)
                request.session['admin_id'] = admin.admin_id
                request.session['admin_name'] = admin.username
            except Admin.DoesNotExist:
                auth_logout(request)
                return render(request, 'store/admin_login.html',
                              {'error': 'This is not an admin account.'})

            return redirect(_next_url(request, '/adminpanel/dashboard/'))

        # Fallback: legacy Admin plaintext password migration
        try:
            admin = Admin.objects.get(username=username)
            if admin.password == password:
                u, created = User.objects.get_or_create(username=username, defaults={'email': admin.email, 'first_name': admin.username})
                u.set_password(password)
                u.save()
                admin.password = u.password
                admin.save()

                auth_login(request, u)
                request.session['admin_id'] = admin.admin_id
                request.session['admin_name'] = admin.username
                return redirect(_next_url(request, '/adminpanel/dashboard/'))
            else:
                return render(request, 'store/admin_login.html', {'error': 'Incorrect password'})
        except Admin.DoesNotExist:
            return render(request, 'store/admin_login.html', {'error': 'Admin does not exist'})

    return render(request, 'store/admin_login.html')


def admin_logout(request):
    auth_logout(request)
    request.session.pop('admin_id', None)
    request.session.pop('admin_name', None)
    return redirect('/adminpanel/login/')


def _page_params(request):
    params = request.GET.copy()
    params.pop('page', None)
    return params.urlencode()


def admin_dashboard(request):
    if 'admin_id' not in request.session:
        return _to_login(request, '/adminpanel/login/')

    paid = Payments.objects.filter(payment_status='Completed')
    revenue = sum(p.amount for p in paid.only('amount'))
    recent_orders = Orders.objects.select_related('customer').order_by('-order_date')[:6]
    low_stock = Products.objects.filter(stock_quantity__lte=5).order_by('stock_quantity')[:6]

    return render(request, 'store/admin_dashboard.html', {
        'customers_count': Customers.objects.count(),
        'sellers_count': Sellers.objects.count(),
        'products_count': Products.objects.count(),
        'orders_count': Orders.objects.count(),
        'paid_count': paid.count(),
        'pending_count': Orders.objects.filter(order_status='Pending').count(),
        'revenue': revenue,
        'recent_orders': recent_orders,
        'low_stock': low_stock,
    })


def admin_customers(request):
    if 'admin_id' not in request.session:
        return _to_login(request, '/adminpanel/login/')

    q = request.GET.get('q', '').strip()
    qs = Customers.objects.all().order_by('-customer_id')
    if q:
        qs = qs.filter(Q(first_name__icontains=q) | Q(last_name__icontains=q) |
                       Q(email__icontains=q) | Q(city__icontains=q))
    page = Paginator(qs, 25).get_page(request.GET.get('page'))
    return render(request, 'store/admin_customers.html', {
        'customers': page, 'page': page, 'q': q, 'total': qs.count(),
        'querystring': _page_params(request)})


def admin_sellers(request):
    if 'admin_id' not in request.session:
        return _to_login(request, '/adminpanel/login/')

    sellers = _rows("SELECT * FROM vw_seller_sales ORDER BY revenue DESC")
    return render(request, 'store/admin_sellers.html', {'sellers': sellers})


def admin_products(request):
    if 'admin_id' not in request.session:
        return _to_login(request, '/adminpanel/login/')

    q = request.GET.get('q', '').strip()
    qs = Products.objects.select_related('seller').order_by('product_id')
    if q:
        qs = qs.filter(Q(product_title__icontains=q) | Q(brand__icontains=q) |
                       Q(product_id__icontains=q))
    if request.GET.get('stock') == 'low':
        qs = qs.filter(stock_quantity__lte=5)
    page = Paginator(qs, 25).get_page(request.GET.get('page'))
    return render(request, 'store/admin_products.html', {
        'products': page, 'page': page, 'q': q, 'total': qs.count(),
        'low': request.GET.get('stock') == 'low', 'querystring': _page_params(request)})


def admin_add_product(request):
    if 'admin_id' not in request.session:
        return _to_login(request, '/adminpanel/login/')

    if request.method == 'POST':
        data, error = _clean_product_form(request.POST, need_id=True)
        if error:
            return render(request, 'store/admin_add_product.html',
                          {'error': error, 'form': request.POST})
        Products.objects.create(**data)
        messages.success(request, 'Product added.')
        return redirect('/adminpanel/products/')

    return render(request, 'store/admin_add_product.html', {'form': {}})


def admin_update_product(request, product_id):
    if 'admin_id' not in request.session:
        return _to_login(request, '/adminpanel/login/')

    product = Products.objects.filter(product_id=product_id).first()
    if not product:
        return redirect('/adminpanel/products/')

    if request.method == 'POST':
        data, error = _clean_product_form(request.POST, need_id=False)
        if error:
            return render(request, 'store/admin_update_product.html',
                          {'product': product, 'error': error, 'form': {}})
        for k, v in data.items():
            setattr(product, k, v)
        product.save()
        messages.success(request, 'Product updated.')
        return redirect('/adminpanel/products/')

    return render(request, 'store/admin_update_product.html', {'product': product, 'form': {}})


def admin_delete_product(request, product_id):
    if 'admin_id' not in request.session:
        return _to_login(request, '/adminpanel/login/')
    product = Products.objects.filter(product_id=product_id).first()
    if product and request.method == 'POST':
        _delete_or_retire(request, product)
    return redirect('/adminpanel/products/')


def admin_orders(request):
    if 'admin_id' not in request.session:
        return _to_login(request, '/adminpanel/login/')

    status = request.GET.get('status', '')
    qs = Orders.objects.select_related('customer').order_by('-order_date')
    if status:
        qs = qs.filter(order_status=status)
    page = Paginator(qs, 20).get_page(request.GET.get('page'))
    for order in page:
        order.items_list = OrderItems.objects.filter(order_id=order.order_id).select_related('product')
    return render(request, 'store/admin_orders.html', {
        'orders': page, 'page': page, 'status': status, 'total': qs.count(),
        'statuses': ['Pending', 'Paid', 'Shipped', 'Delivered', 'Cancelled'],
        'querystring': _page_params(request)})


def payment_page(request, order_id):
    if 'customer_id' not in request.session:
        return _to_login(request, '/login/')

    order = get_object_or_404(Orders, order_id=order_id,
                              customer_id=request.session['customer_id'])
    if order.order_status != 'Pending':
        return redirect('/orders/')

    return render(request, 'store/payment_page.html', {'order': order})


def process_payment(request, order_id):
    if request.method != 'POST':
        return redirect('payment_page', order_id=order_id)
    if 'customer_id' not in request.session:
        return _to_login(request, '/login/')

    with transaction.atomic():
        # lock the order row so a double click can't pay twice
        order = get_object_or_404(
            Orders.objects.select_for_update(),
            order_id=order_id, customer_id=request.session['customer_id'])
        if order.order_status != 'Pending':
            return redirect('/orders/')

        method = request.POST.get('method', 'UPI')
        if method not in ('UPI', 'Card', 'NetBanking', 'COD'):
            method = 'UPI'

        Payments.objects.create(
            order=order,
            payment_method=method,
            amount=order.total_amount,
            payment_date=timezone.now(),
            payment_status='Completed',
            transaction_id=f"SIM{order.order_id}{int(timezone.now().timestamp())}"
        )
        order.order_status = 'Paid'
        order.delivery_date = timezone.now() + timedelta(days=5)
        order.save()

    messages.success(request, f'Payment successful for order #{order.order_id}.')
    return redirect('/orders/')

def admin_funnel_analysis(request):
    if 'admin_id' not in request.session:
        return _to_login(request, '/adminpanel/login/')

    # Cumulative funnel from the database view (sql/06_cumulative_funnel.sql):
    # a customer who reached a later stage also counts in every earlier one.
    summary = _rows("SELECT stage, customers, pct_from_previous FROM vw_funnel_summary ORDER BY stage_order")
    top = summary[0]['customers'] if summary else 0
    rows = [{'stage': r['stage'], 'count': r['customers'], 'rate': r['pct_from_previous'],
             'width': round(100 * r['customers'] / top) if top else 0} for r in summary]
    funnel_data = {r['stage']: r['count'] for r in rows}
    return render(request, 'store/admin_funnel.html', {'rows': rows, 'funnel_data': funnel_data})


def admin_product_funnel(request, product_id):
    if 'admin_id' not in request.session:
        return _to_login(request, '/adminpanel/login/')

    product = Products.objects.filter(product_id=product_id).first()
    found = _rows("SELECT * FROM vw_product_funnel WHERE product_id = %s", [product_id])
    f = found[0] if found else {}
    stages = [('VIEW', 'viewed'), ('CART', 'carted'), ('CHECKOUT', 'checked_out'),
              ('ORDER', 'ordered'), ('PAYMENT', 'paid'), ('REVIEW', 'reviewed')]
    rows, prev = [], None
    top = int(f.get('viewed') or 0)
    for stage, col in stages:
        count = int(f.get(col) or 0)
        rows.append({'stage': stage, 'count': count,
                     'rate': round(100 * count / prev, 1) if prev else None,
                     'width': round(100 * count / top) if top else 0})
        prev = count
    return render(request, 'store/admin_funnel_product.html', {
        'rows': rows, 'product': product,
        'funnel_data': {r['stage']: r['count'] for r in rows}})


def customer_logout(request):
    session_id = request.session.get('user_session_id')
    if session_id:
        UserSessions.objects.filter(session_id=session_id, end_time__isnull=True) \
                            .update(end_time=timezone.now())
    auth_logout(request)
    request.session.pop('customer_id', None)
    request.session.pop('customer_name', None)
    request.session.pop('user_session_id', None)
    messages.success(request, 'You have been logged out.')
    return redirect('/login/')


from django.shortcuts import get_object_or_404

def buy_now(request, product_id):
    if 'customer_id' not in request.session:
        return _to_login(request, '/login/')

    try:
        customer = Customers.objects.get(customer_id=request.session['customer_id'])
        product = Products.objects.get(product_id=product_id)
        if product.stock_quantity is not None and product.stock_quantity < 1:
            messages.error(request, 'Sorry, this product is out of stock.')
            return redirect('product_detail', product_id=product_id)

        # First delete related cart_events, then delete cart items
        old_carts = Cart.objects.filter(customer=customer)
        cart_ids = list(old_carts.values_list('cart_id', flat=True))

        if cart_ids:
            # cart_events keep their history (cart_id becomes NULL)
            old_carts.delete()

        # Add the selected product to cart
        cart_item = Cart.objects.create(
            customer=customer,
            product=product,
            quantity=1,
            added_date=timezone.now()
        )

        # Record CART stage in funnel
        session_id = request.session.get('user_session_id')
        if session_id:
            FunnelEvents.objects.create(
                customer_id=customer.customer_id,
                session_id=session_id,
                product_id=product_id,
                event_stage='CART',
                event_timestamp=timezone.now()
            )

        return redirect('/checkout/')

    except Exception as e:
        print("========== BUY NOW ERROR ==========")
        print(e)
        print("===================================")
        return redirect('/products/')


# ---------------------------------------------------------------------
# Admin analytics page: reads the SQL views and stored procedures
# (sql/03_views_procedures.sql, sql/05_device_view.sql)
# ---------------------------------------------------------------------
from datetime import date, timedelta
from django.db import connection


def _rows(sql, params=None):
    """Execute SQL and return the first result set as a list of dictionaries."""
    with connection.cursor() as cur:
        cur.execute(sql, params or [])

        if cur.description is None:
            return []

        columns = [col[0] for col in cur.description]
        rows = [
            dict(zip(columns, row))
            for row in cur.fetchall()
        ]

        return rows

def _parse_date(value, default):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return default


def admin_analytics(request):
    if 'admin_id' not in request.session:
        return _to_login(request, '/adminpanel/login/')

    today = timezone.now().date()
    end = _parse_date(request.GET.get('end'), today)
    start = _parse_date(request.GET.get('start'), end - timedelta(days=29))
    if start > end:
        start, end = end, start
    range_args = [start, end + timedelta(days=1)]   # [start, end] inclusive

    # Funnel for the selected range: stored procedure
    funnel = _rows(
    "EXEC dbo.sp_funnel_between %s, %s",
    [start, end]
      )
    top = funnel[0]['customers'] if funnel else 0
    for f in funnel:
        f['pct_of_top'] = round(100 * f['customers'] / top, 1) if top else 0

    # KPIs for the selected range (visitors / buyers use the same cumulative rule)
    k = _rows("""
        SELECT
          (SELECT COUNT(*) FROM payments
            WHERE payment_status = 'Completed' AND payment_date >= %s AND payment_date < %s) AS paid_orders,
          (SELECT COALESCE(SUM(amount), 0) FROM payments
            WHERE payment_status = 'Completed' AND payment_date >= %s AND payment_date < %s) AS revenue,
          (SELECT COUNT(*) FROM vw_cart_abandonment
            WHERE last_carted_at >= %s AND last_carted_at < %s) AS abandoned
    """, range_args * 3)[0]
    by_stage = {f['stage']: f['customers'] for f in funnel}
    k['visitors'] = by_stage.get('VIEW', 0)
    k['buyers'] = by_stage.get('PAYMENT', 0)
    k['conversion'] = round(100 * k['buyers'] / k['visitors'], 1) if k['visitors'] else 0
    k['aov'] = round(k['revenue'] / k['paid_orders']) if k['paid_orders'] else 0

    # Daily trend for the selected range: view
    daily = _rows("""SELECT day, viewed, carted, paid FROM vw_daily_funnel
                     WHERE day BETWEEN %s AND %s ORDER BY day""", [start, end])

    # All-time breakdowns: views + stored procedure
    devices = _rows("SELECT * FROM vw_device_funnel ORDER BY sessions DESC")
    categories = _rows("""
    SELECT TOP 10 *
    FROM dbo.vw_category_funnel
    WHERE viewed > 0
    ORDER BY paid DESC, viewed DESC
    """)

    top_products = _rows(
    "EXEC dbo.sp_top_products %s",
    [10]
    )

    abandoned = _rows("""
    SELECT TOP 15 *
    FROM dbo.vw_cart_abandonment
    ORDER BY last_carted_at DESC
    """)

    chart_data = {
        'funnel': {'labels': [f['stage'] for f in funnel],
                   'values': [f['customers'] for f in funnel]},
        'daily': {'labels': [d['day'].strftime('%d %b') for d in daily],
                  'viewed': [d['viewed'] for d in daily],
                  'carted': [d['carted'] for d in daily],
                  'paid': [d['paid'] for d in daily]},
    }

    return render(request, 'store/admin_analytics.html', {
        'start': start, 'end': end, 'funnel': funnel, 'k': k,
        'devices': devices, 'categories': categories,
        'top_products': top_products, 'abandoned': abandoned,
        'chart_data': chart_data,
    })


# ---------------------------------------------------------------------
# Order status changes (admin) and cancelling (customer)
# ---------------------------------------------------------------------
ORDER_FLOW = {                       # allowed next statuses
    'Pending': ['Cancelled'],
    'Paid': ['Shipped', 'Cancelled'],
    'Shipped': ['Delivered'],
    'Delivered': [],
    'Cancelled': [],
}


def _cancel_order(order):
    """Cancel an order and give its stock back, in one transaction.
    (The stock trigger only reduces stock; cancelling must undo that.)"""
    for item in OrderItems.objects.filter(order=order).select_for_update():
        Products.objects.filter(product_id=item.product_id, stock_quantity__isnull=False) \
                        .update(stock_quantity=F('stock_quantity') + item.quantity)
    Payments.objects.filter(order=order, payment_status='Completed').update(payment_status='Refunded')
    order.order_status = 'Cancelled'
    order.save(update_fields=['order_status'])


def admin_update_order_status(request, order_id):
    if 'admin_id' not in request.session:
        return _to_login(request, '/adminpanel/login/')
    if request.method != 'POST':
        return redirect('/adminpanel/orders/')

    new = request.POST.get('status', '')
    with transaction.atomic():
        order = Orders.objects.select_for_update().filter(order_id=order_id).first()
        if not order:
            messages.error(request, 'Order not found.')
        elif new not in ORDER_FLOW.get(order.order_status, []):
            messages.error(request, f'Order #{order_id} cannot go from {order.order_status} to {new or "nothing"}.')
        elif new == 'Cancelled':
            _cancel_order(order)
            messages.success(request, f'Order #{order_id} cancelled and its stock returned.')
        else:
            order.order_status = new
            if new == 'Delivered':
                order.delivery_date = timezone.now()
            order.save()
            messages.success(request, f'Order #{order_id} marked {new}.')
    return redirect(request.POST.get('back') or '/adminpanel/orders/')


def cancel_order(request, order_id):
    if 'customer_id' not in request.session:
        return _to_login(request, '/login/')
    if request.method == 'POST':
        with transaction.atomic():
            order = Orders.objects.select_for_update().filter(
                order_id=order_id, customer_id=request.session['customer_id']).first()
            if order and order.order_status == 'Pending':
                _cancel_order(order)
                messages.success(request, f'Order #{order_id} cancelled.')
            elif order:
                messages.error(request, 'Only unpaid orders can be cancelled here.')
    return redirect('order_detail', order_id=order_id)

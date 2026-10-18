# Manual test cases: ShopSphere

How to use this list:

- Run each test on a fresh database built from `database/01` to `09`, plus `create_sample_data` (and optionally `generate_funnel_data`). See the README, sections 12–14.
- Start the site with `python manage.py runserver` and open <http://127.0.0.1:8000/>.
- Tick **Pass** when the actual result matches the expected result.
- The **DB check** column gives a query to run in MySQL Workbench to confirm what the database recorded.

Logins: customer `customer@example.com` / `pass123`, seller `seller@example.com` / `pass123`, admin `admin` / `adminpass`.

## 1. Visitor (not logged in)

| ID | Test | Steps | Expected result | DB check | Pass |
|---|---|---|---|---|---|
| V1 | Home page | Open `/` | Hero section, featured products with photos, category tiles | | ☐ |
| V2 | Browse by gender | Click Men / Women / Boys / Girls in the menu | Only that gender's products; the count updates | | ☐ |
| V3 | Search | Type `nike shoes` in the search box and click Apply | Only matching products | | ☐ |
| V4 | Filter and sort | Pick a category and "Price: low to high" | Products filtered and sorted; pages 1, 2, … work | | ☐ |
| V5 | SQL injection in search | Search for `' OR 1=1 --` | "No products" message, no error page | | ☐ |
| V6 | Product page | Open any product | Photo, price, stock, reviews, related products | | ☐ |
| V7 | Unknown product | Open `/product/999999/` | Redirected to the product list with "not found" | | ☐ |
| V8 | Protected page | Open `/cart/` | Redirected to `/login/?next=/cart/` | | ☐ |
| V9 | Add to cart while logged out | Click **Add to cart** | Login page; after logging in, the product is added to your cart | | ☐ |

## 2. Registration and login

| ID | Test | Steps | Expected result | DB check | Pass |
|---|---|---|---|---|---|
| A1 | Register | Fill the form with a new email and an 8+ character password | "Account created", login page | `SELECT email, LEFT(password,20) FROM customers ORDER BY customer_id DESC LIMIT 1;` shows a `pbkdf2_sha256$` hash | ☐ |
| A2 | Passwords differ | Different password and confirmation | "Passwords do not match" | | ☐ |
| A3 | Short password | Password `abc` | "at least 8 characters" | | ☐ |
| A4 | Invalid email | Email `admin` | "Please enter a valid email address" | | ☐ |
| A5 | Existing email | Register with `customer@example.com` | "An account with this email already exists" | | ☐ |
| A6 | Customer login | Log in as the customer | Products page; the menu shows "Hi, Test" | `SELECT * FROM user_sessions ORDER BY session_id DESC LIMIT 1;` shows a new session | ☐ |
| A7 | Wrong password | Correct email, wrong password | "Incorrect password" | | ☐ |
| A8 | Wrong role | Log in on the customer page with `admin` | Error; not logged in | | ☐ |
| A9 | Logout | Menu → Log out | Back to the shop as a visitor | The session row now has an `end_time` | ☐ |
| A10 | Open redirect | Open `/login/?next=https://example.com` and log in | You stay on ShopSphere (`/products/`) | | ☐ |

## 3. Customer funnel

| ID | Test | Steps | Expected result | DB check | Pass |
|---|---|---|---|---|---|
| F1 | VIEW recorded | As the customer, open a product | Page shows | `SELECT * FROM funnel_events WHERE event_stage='VIEW' ORDER BY event_id DESC LIMIT 1;` | ☐ |
| F2 | CART recorded | Click **Add to cart** | Cart page, "Added …" message | New `cart` row; `cart_events` ADD; `funnel_events` CART | ☐ |
| F3 | Change quantity | Click **+** and **−** in the cart | Quantity and total update | `cart_events` INCREASE / DECREASE | ☐ |
| F4 | Stock limit in cart | Click **+** past the product's stock | "Only N in stock." | | ☐ |
| F5 | Remove from cart | Click **Remove** | Item disappears | `cart_events` row kept, `cart_id` now NULL | ☐ |
| F6 | Checkout needs address | Click **Checkout** with an empty address | "Please enter a shipping address" | | ☐ |
| F7 | Checkout | Enter an address and place the order | Payment page for the new order | New `orders` row (Pending), `order_items` rows, stock reduced, `funnel_events` CHECKOUT + ORDER, cart empty | ☐ |
| F8 | Stock trigger | In Workbench set a product's stock to 1; add 2 of it to the cart; check out | "Not enough stock for …"; no order created; cart kept | `SELECT COUNT(*) FROM orders;` unchanged | ☐ |
| F9 | Payment | Choose UPI / Card / Net banking / COD and pay | "Payment successful", order shows **Paid** | `payments` row Completed; `funnel_events` PAYMENT (written by the trigger) | ☐ |
| F10 | Pay twice | Press the browser Back button and pay again | Redirected to My orders; still one payment | `SELECT COUNT(*) FROM payments WHERE order_id = …;` = 1 | ☐ |
| F11 | Pay later and cancel | Check out, choose **Pay later**, open the order and click **Cancel** | Order **Cancelled** | Stock back to its value before the order | ☐ |
| F12 | Another customer's order | Log in as a demo shopper and open `/order/<customer's order id>/` | 404 page | | ☐ |
| F13 | Review | On a product, give 4 stars and a comment | "Thanks! Your review was posted"; the average rating updates | `reviews` row; `funnel_events` REVIEW (trigger) | ☐ |
| F14 | Profile and orders | Open Profile and My orders | Customer details; every order with items and status | | ☐ |
| F15 | Buy now | Click **Buy now** on a product | Cart is replaced by just that product and checkout opens | | ☐ |

## 4. Seller

| ID | Test | Steps | Expected result | DB check | Pass |
|---|---|---|---|---|---|
| S1 | Seller login | Log in at `/seller/login/` | Seller hub with products, units sold and revenue | `SELECT * FROM vw_seller_sales WHERE seller_id = …;` matches the cards | ☐ |
| S2 | Add product | **+ Add product**, fill the form | Product appears in the list and the shop | New `products` row with your `seller_id` | ☐ |
| S3 | Invalid product | Price `-5` or an existing product ID | Error message, nothing saved | | ☐ |
| S4 | Edit product | Edit the price | New price shown in the shop | | ☐ |
| S5 | Delete unsold product | Delete the product from S2 | "Deleted" | Row gone (its cart rows and reviews cascade) | ☐ |
| S6 | Delete sold product | Delete a product that has orders | "taken off sale (stock set to 0)" | Row kept, `stock_quantity = 0` (RESTRICT) | ☐ |
| S7 | Other seller's product | Open `/seller/product/<another seller's id>/edit/` | Redirected to your own seller hub; product unchanged | | ☐ |

## 5. Admin

| ID | Test | Steps | Expected result | DB check | Pass |
|---|---|---|---|---|---|
| D1 | Admin login | Log in at `/adminpanel/login/` | Dashboard with totals, revenue and recent orders | | ☐ |
| D2 | Lists | Open Customers, Sellers, Products, Orders; use search and pages | Correct rows; search and pagination work | | ☐ |
| D3 | Low stock | Products → Low stock | Only products with low stock | | ☐ |
| D4 | Admin add / edit / delete product | Same as S2–S6, choosing a seller | Same results | | ☐ |
| D5 | Order status | On a Paid order choose **Shipped**, then **Delivered** | Status updates in that order | | ☐ |
| D6 | Illegal status jump | On a Paid order try **Delivered** directly | "cannot go from Paid to Delivered" | | ☐ |
| D7 | Admin cancel | Cancel a Paid order | Order Cancelled, stock returned | Payment status becomes Refunded | ☐ |
| D8 | Funnel table | Open Funnel table | Stages VIEW → REVIEW with counts and % from previous; every count ≤ the one above | `SELECT * FROM vw_funnel_summary;` matches | ☐ |
| D9 | Product funnel | Click a product in the funnel table | That product's funnel | `SELECT * FROM vw_product_funnel WHERE product_id = …;` | ☐ |
| D10 | Analytics | Open Analytics, change the date range, click Apply | KPIs, funnel chart, daily trend, devices, categories, top products and abandoned carts update | `CALL sp_funnel_between('…', '…');` matches the funnel | ☐ |
| D11 | Customer cannot reach admin | As a customer, open `/adminpanel/dashboard/` | Redirected to the admin login | | ☐ |

## 6. Interface

| ID | Test | Steps | Expected result | Pass |
|---|---|---|---|---|
| U1 | Dark mode | Click the moon icon | Whole site switches theme; the choice is remembered | ☐ |
| U2 | Mobile layout | Narrow the browser to phone width | Menu collapses into the ☰ button; no sideways scrolling | ☐ |
| U3 | 3D effects | Move the mouse over product cards and the hero | Cards tilt; the payment card flips | ☐ |
| U4 | Broken links | Click through every menu item for each role | No error pages | ☐ |

## 7. Automated checks

| ID | Test | How | Expected |
|---|---|---|---|
| T1 | Django tests | `python manage.py test store -v 2` | `Ran 29 tests … OK` |
| T2 | SQL validation | Run `database/tests/validation_tests.sql` in Workbench | 16 PASS, 0 FAIL |
| T3 | Complex queries | Run `database/queries/complex_queries.sql` | Every result tab returns rows without errors |

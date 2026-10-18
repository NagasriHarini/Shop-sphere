-- =====================================================================
--  Complex SQL queries - ShopSphere / Online Shopping Funnel Analysis
--  Database : shopping_funnel (MySQL 8)
--
--  How to run: open in MySQL Workbench and run one query at a time
--  (put the cursor in a query, press Ctrl+Enter), or run the whole file
--  (Ctrl+Shift+Enter) and read the result tabs in order.
--  All queries are read-only (SELECT / CALL).
--
--  Index
--    A. Multi-table joins ............................ Q1 - Q4
--    B. GROUP BY, HAVING and aggregate functions ..... Q5 - Q8
--    C. Subqueries (scalar, IN, EXISTS, correlated,
--       derived table, NOT EXISTS) ................... Q9 - Q14
--    D. CTEs and window functions .................... Q15 - Q18
--    E. Set operations, CASE and date functions ...... Q19 - Q20
--    F. Views and stored procedures .................. Q21 - Q24
-- =====================================================================

USE shopping_funnel;


-- =====================================================================
--  A. MULTI-TABLE JOINS
-- =====================================================================

-- Q1. Full order report (5-table join)
-- Purpose : every order line with who bought it, what, from which seller,
--           and how it was paid. LEFT JOIN on payments keeps unpaid orders.
-- Concepts: INNER JOIN x4, LEFT JOIN, column aliases
SELECT o.order_id,
       o.order_date,
       CONCAT(c.first_name, ' ', c.last_name) AS customer,
       p.product_title,
       s.seller_name,
       oi.quantity,
       oi.unit_price,
       oi.subtotal,
       o.order_status,
       pm.payment_method,
       pm.payment_status
FROM orders o
JOIN customers   c  ON c.customer_id = o.customer_id
JOIN order_items oi ON oi.order_id   = o.order_id
JOIN products    p  ON p.product_id  = oi.product_id
JOIN sellers     s  ON s.seller_id   = p.seller_id
LEFT JOIN payments pm ON pm.order_id = o.order_id
ORDER BY o.order_date DESC, o.order_id
LIMIT 50;


-- Q2. What is in every customer's cart right now, and its value
-- Purpose : basis for "cart abandonment" follow-ups
-- Concepts: 3-table join, computed column
SELECT c.customer_id,
       CONCAT(c.first_name, ' ', c.last_name) AS customer,
       p.product_title,
       ct.quantity,
       p.price,
       ct.quantity * p.price AS line_value,
       ct.added_date
FROM cart ct
JOIN customers c ON c.customer_id = ct.customer_id
JOIN products  p ON p.product_id  = ct.product_id
ORDER BY line_value DESC;


-- Q3. One customer's session-by-session browsing history
-- Purpose : see which device a customer used and what they looked at
-- Concepts: 3-table join, filter on the joined table
SELECT us.session_id,
       us.device_type,
       us.start_time,
       us.end_time,
       p.product_title,
       pv.view_timestamp
FROM user_sessions us
JOIN product_views pv ON pv.session_id = us.session_id
JOIN products      p  ON p.product_id  = pv.product_id
WHERE us.customer_id = (SELECT MIN(customer_id) FROM product_views)   -- any customer with views
ORDER BY us.start_time, pv.view_timestamp;


-- Q4. Products that were never viewed (anti-join with LEFT JOIN ... IS NULL)
-- Purpose : catalogue items that get no traffic at all
-- Concepts: LEFT JOIN + IS NULL (rows with no match)
SELECT p.product_id, p.product_title, p.category, p.brand, p.price
FROM products p
LEFT JOIN product_views pv ON pv.product_id = p.product_id
WHERE pv.view_id IS NULL
ORDER BY p.category, p.brand
LIMIT 50;


-- =====================================================================
--  B. GROUP BY, HAVING AND AGGREGATE FUNCTIONS
-- =====================================================================

-- Q5. Revenue, units and orders per seller (paid orders only)
-- Concepts: JOIN + GROUP BY, SUM / COUNT(DISTINCT) / AVG, ORDER BY aggregate
SELECT s.seller_id,
       s.seller_name,
       COUNT(DISTINCT o.order_id)         AS paid_orders,
       SUM(oi.quantity)                   AS units_sold,
       SUM(oi.subtotal)                   AS revenue,
       ROUND(AVG(oi.unit_price), 2)       AS avg_selling_price
FROM sellers s
JOIN products    p  ON p.seller_id  = s.seller_id
JOIN order_items oi ON oi.product_id = p.product_id
JOIN orders      o  ON o.order_id    = oi.order_id
WHERE o.order_status IN ('Paid', 'Shipped', 'Delivered')
GROUP BY s.seller_id, s.seller_name
ORDER BY revenue DESC;


-- Q6. Catalogue summary per gender and category
-- Concepts: GROUP BY two columns, COUNT / MIN / MAX / AVG / SUM
SELECT gender,
       category,
       COUNT(*)                 AS products,
       MIN(price)               AS cheapest,
       MAX(price)               AS dearest,
       ROUND(AVG(price), 2)     AS avg_price,
       SUM(stock_quantity)      AS units_in_stock
FROM products
GROUP BY gender, category
ORDER BY gender, products DESC;


-- Q7. Best-rated brands with at least 2 reviews
-- Concepts: GROUP BY + HAVING (filter on an aggregate), AVG / COUNT
SELECT p.brand,
       COUNT(r.review_id)          AS reviews,
       COUNT(DISTINCT p.product_id) AS products_reviewed,
       ROUND(AVG(r.rating), 2)     AS avg_rating
FROM reviews r
JOIN products p ON p.product_id = r.product_id
GROUP BY p.brand
HAVING COUNT(r.review_id) >= 2
ORDER BY avg_rating DESC, reviews DESC;


-- Q8. Customers who spent more than 5,000 in total
-- Concepts: GROUP BY + HAVING SUM(...) > n
SELECT c.customer_id,
       CONCAT(c.first_name, ' ', c.last_name) AS customer,
       c.city,
       COUNT(o.order_id)     AS orders,
       SUM(o.total_amount)   AS total_spent
FROM customers c
JOIN orders o ON o.customer_id = c.customer_id
WHERE o.order_status <> 'Cancelled'
GROUP BY c.customer_id, customer, c.city
HAVING SUM(o.total_amount) > 5000
ORDER BY total_spent DESC;


-- =====================================================================
--  C. SUBQUERIES
-- =====================================================================

-- Q9. Products priced above the average of their own category
-- Concepts: CORRELATED subquery (runs once per outer row)
SELECT p.product_id, p.product_title, p.category, p.price
FROM products p
WHERE p.price > (SELECT AVG(p2.price)
                 FROM products p2
                 WHERE p2.category = p.category)
ORDER BY p.category, p.price DESC
LIMIT 50;


-- Q10. Customers who added something to the cart but never placed an order
-- Concepts: IN subquery + NOT EXISTS subquery
SELECT c.customer_id, CONCAT(c.first_name, ' ', c.last_name) AS customer, c.email
FROM customers c
WHERE c.customer_id IN (SELECT ce.customer_id FROM cart_events ce WHERE ce.event_type = 'ADD')
  AND NOT EXISTS (SELECT 1 FROM orders o WHERE o.customer_id = c.customer_id);


-- Q11. Orders whose total is above the average order value
-- Concepts: scalar subquery in WHERE and in SELECT
SELECT o.order_id,
       o.total_amount,
       (SELECT ROUND(AVG(total_amount), 2) FROM orders) AS avg_order_value
FROM orders o
WHERE o.total_amount > (SELECT AVG(total_amount) FROM orders)
ORDER BY o.total_amount DESC;


-- Q12. Each customer's number of sessions, views and orders in one row
-- Concepts: scalar subqueries in the SELECT list
SELECT c.customer_id,
       CONCAT(c.first_name, ' ', c.last_name) AS customer,
       (SELECT COUNT(*) FROM user_sessions us WHERE us.customer_id = c.customer_id) AS sessions,
       (SELECT COUNT(*) FROM product_views pv WHERE pv.customer_id = c.customer_id) AS views,
       (SELECT COUNT(*) FROM orders o        WHERE o.customer_id  = c.customer_id) AS orders
FROM customers c
ORDER BY views DESC
LIMIT 25;


-- Q13. Brand with the highest revenue in each category
-- Concepts: derived table (subquery in FROM) joined to its own MAX
SELECT t.category, t.brand, t.revenue
FROM (SELECT p.category, p.brand, SUM(oi.subtotal) AS revenue
      FROM order_items oi JOIN products p ON p.product_id = oi.product_id
      GROUP BY p.category, p.brand) t
JOIN (SELECT category, MAX(revenue) AS best
      FROM (SELECT p.category, p.brand, SUM(oi.subtotal) AS revenue
            FROM order_items oi JOIN products p ON p.product_id = oi.product_id
            GROUP BY p.category, p.brand) x
      GROUP BY category) m
  ON m.category = t.category AND m.best = t.revenue
ORDER BY t.revenue DESC;


-- Q14. Paid orders that the customer has not reviewed yet
-- Concepts: EXISTS + NOT EXISTS together
SELECT DISTINCT o.order_id, o.customer_id, oi.product_id
FROM orders o
JOIN order_items oi ON oi.order_id = o.order_id
WHERE EXISTS (SELECT 1 FROM payments pm
              WHERE pm.order_id = o.order_id AND pm.payment_status = 'Completed')
  AND NOT EXISTS (SELECT 1 FROM reviews r
                  WHERE r.customer_id = o.customer_id AND r.product_id = oi.product_id)
ORDER BY o.order_id;


-- =====================================================================
--  D. CTEs AND WINDOW FUNCTIONS (MySQL 8)
-- =====================================================================

-- Q15. THE FUNNEL: customers at each stage, conversion and drop-off
-- Purpose : the core analysis of the project.
--   A customer counts in a stage if they reached it or any later stage
--   (you cannot pay without ordering). FIELD() turns a stage into 1..5.
-- Concepts: CTE, FIELD(), MAX per group, LAG() window, conversion / drop-off %
WITH reach AS (
    SELECT customer_id,
           MAX(FIELD(event_stage, 'VIEW','CART','CHECKOUT','ORDER','PAYMENT')) AS max_rank
    FROM funnel_events
    GROUP BY customer_id
),
stages AS (
    SELECT 1 AS pos, 'VIEW' AS stage UNION ALL SELECT 2, 'CART' UNION ALL
    SELECT 3, 'CHECKOUT' UNION ALL SELECT 4, 'ORDER' UNION ALL SELECT 5, 'PAYMENT'
),
counts AS (
    SELECT s.pos, s.stage, COUNT(r.customer_id) AS customers
    FROM stages s
    LEFT JOIN reach r ON r.max_rank >= s.pos
    GROUP BY s.pos, s.stage
)
SELECT stage,
       customers,
       ROUND(100 * customers / NULLIF(LAG(customers) OVER (ORDER BY pos), 0), 1)       AS conversion_pct,
       ROUND(100 - 100 * customers / NULLIF(LAG(customers) OVER (ORDER BY pos), 0), 1) AS drop_off_pct,
       ROUND(100 * customers / NULLIF(FIRST_VALUE(customers) OVER (ORDER BY pos), 0), 1) AS pct_of_visitors
FROM counts
ORDER BY pos;


-- Q16. Top 3 products by revenue inside every category
-- Concepts: CTE + RANK() OVER (PARTITION BY ...)
WITH product_revenue AS (
    SELECT p.category, p.product_id, p.product_title, SUM(oi.subtotal) AS revenue
    FROM order_items oi JOIN products p ON p.product_id = oi.product_id
    GROUP BY p.category, p.product_id, p.product_title
),
ranked AS (
    SELECT pr.*, RANK() OVER (PARTITION BY category ORDER BY revenue DESC) AS rnk
    FROM product_revenue pr
)
SELECT category, rnk, product_title, revenue
FROM ranked
WHERE rnk <= 3
ORDER BY category, rnk;


-- Q17. Daily revenue with a running total and a 7-day moving average
-- Concepts: SUM() OVER (ORDER BY ...), AVG() OVER (ROWS BETWEEN ...)
WITH daily AS (
    SELECT DATE(payment_date) AS day, SUM(amount) AS revenue
    FROM payments
    WHERE payment_status = 'Completed'
    GROUP BY DATE(payment_date)
)
SELECT day,
       revenue,
       SUM(revenue) OVER (ORDER BY day)                                  AS running_total,
       ROUND(AVG(revenue) OVER (ORDER BY day ROWS BETWEEN 6 PRECEDING AND CURRENT ROW), 2)
                                                                         AS moving_avg_7d
FROM daily
ORDER BY day;


-- Q18. Time from first product view to first payment, per customer
-- Concepts: conditional aggregation (MIN(CASE ...)), TIMESTAMPDIFF
WITH firsts AS (
    SELECT customer_id,
           MIN(CASE WHEN event_stage = 'VIEW'    THEN event_timestamp END) AS first_view,
           MIN(CASE WHEN event_stage = 'PAYMENT' THEN event_timestamp END) AS first_payment
    FROM funnel_events
    GROUP BY customer_id
)
SELECT customer_id,
       first_view,
       first_payment,
       TIMESTAMPDIFF(MINUTE, first_view, first_payment) AS minutes_to_buy
FROM firsts
WHERE first_view IS NOT NULL AND first_payment IS NOT NULL AND first_payment >= first_view
ORDER BY minutes_to_buy;


-- =====================================================================
--  E. SET OPERATIONS, CASE AND DATE FUNCTIONS
-- =====================================================================

-- Q19. One activity feed from three tables
-- Concepts: UNION ALL of differently shaped tables, ORDER BY over the union
SELECT 'View'   AS activity, customer_id, product_id, view_timestamp AS at_time FROM product_views
UNION ALL
SELECT 'Cart',  customer_id, product_id, event_timestamp FROM cart_events WHERE event_type = 'ADD'
UNION ALL
SELECT 'Review', customer_id, product_id, review_date FROM reviews
ORDER BY at_time DESC
LIMIT 30;


-- Q20. Customer segments by spend
-- Concepts: CASE expression, LEFT JOIN + COALESCE, GROUP BY on an expression
SELECT segment, COUNT(*) AS customers, ROUND(AVG(spent), 2) AS avg_spent
FROM (
    SELECT c.customer_id,
           COALESCE(SUM(o.total_amount), 0) AS spent,
           CASE
               WHEN COALESCE(SUM(o.total_amount), 0) = 0     THEN '1. No purchase'
               WHEN SUM(o.total_amount) < 3000               THEN '2. Low (< 3k)'
               WHEN SUM(o.total_amount) < 10000              THEN '3. Medium (3k-10k)'
               ELSE                                               '4. High (10k+)'
           END AS segment
    FROM customers c
    LEFT JOIN orders o ON o.customer_id = c.customer_id AND o.order_status <> 'Cancelled'
    GROUP BY c.customer_id
) t
GROUP BY segment
ORDER BY segment;


-- =====================================================================
--  F. VIEWS AND STORED PROCEDURES (created in 05, 07 and 08)
-- =====================================================================

-- Q21. Overall funnel from the view
SELECT stage, customers, pct_from_previous, pct_from_view FROM vw_funnel_summary;

-- Q22. Device comparison: which device converts carts to orders best?
SELECT device_type, sessions, carted, ordered, cart_to_order_pct
FROM vw_device_funnel
ORDER BY cart_to_order_pct DESC;

-- Q23. Funnel for a date range (stored procedure with input parameters)
CALL sp_funnel_between(CURDATE() - INTERVAL 30 DAY, CURDATE());

-- Q24. Best-selling products (stored procedure) and one customer's journey
CALL sp_top_products(10);
SET @cust := (SELECT MIN(customer_id) FROM funnel_events);
CALL sp_customer_journey(@cust);

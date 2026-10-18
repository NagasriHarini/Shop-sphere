-- =====================================================================
--  05  Funnel reports (views + stored procedures)
--  Database : shopping_funnel (MySQL 8)
--  Run in MySQL Workbench: open this file, then Execute All (Ctrl+Shift+Enter)
--  Requires: 03_funnel_events.sql and 04_triggers.sql already run.
--
--  VIEWS (use them like tables:  SELECT * FROM vw_funnel_summary;)
--    vw_funnel_summary     customers at each stage + conversion %
--    vw_product_funnel     funnel for every product that had activity
--    vw_category_funnel    funnel by gender / category / sub-category
--    vw_brand_funnel       funnel by brand
--    vw_cart_abandonment   carted but never paid for (customer + product)
--    vw_seller_sales       units sold and revenue per seller (paid orders)
--    vw_daily_funnel       stage counts per day (trend)
--
--  STORED PROCEDURES (CALL them)
--    sp_funnel_between(start_date, end_date)   funnel for a date range
--    sp_customer_journey(customer_id)          one customer's path, in time order
--    sp_top_products(n)                        best-selling products by revenue
--
--  Safe to re-run: views use CREATE OR REPLACE, procedures are dropped first.
-- =====================================================================

USE shopping_funnel;

-- ---------------------------------------------------------------------
-- 1. Overall funnel
--    customers           = distinct customers who reached the stage
--    pct_from_previous   = % of the previous stage's customers
--    pct_from_view       = % of everyone who viewed a product
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW vw_funnel_summary AS
WITH stages AS (
    SELECT 1 AS stage_order, 'VIEW'     AS stage UNION ALL
    SELECT 2, 'CART'     UNION ALL
    SELECT 3, 'CHECKOUT' UNION ALL
    SELECT 4, 'ORDER'    UNION ALL
    SELECT 5, 'PAYMENT'  UNION ALL
    SELECT 6, 'REVIEW'
),
counts AS (
    SELECT s.stage_order, s.stage,
           COUNT(DISTINCT fe.customer_id) AS customers,
           COUNT(fe.event_id)             AS events
    FROM stages s
    LEFT JOIN funnel_events fe ON fe.event_stage = s.stage
    GROUP BY s.stage_order, s.stage
)
SELECT stage_order,
       stage,
       customers,
       events,
       ROUND(100 * customers / NULLIF(LAG(customers) OVER (ORDER BY stage_order), 0), 1)
           AS pct_from_previous,
       ROUND(100 * customers / NULLIF(FIRST_VALUE(customers) OVER (ORDER BY stage_order), 0), 1)
           AS pct_from_view
FROM counts;


-- ---------------------------------------------------------------------
-- 2. Funnel per product (only products with at least one event)
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW vw_product_funnel AS
SELECT p.product_id,
       p.product_title,
       p.brand,
       p.category,
       p.sub_category,
       COUNT(DISTINCT CASE WHEN fe.event_stage = 'VIEW'     THEN fe.customer_id END) AS viewed,
       COUNT(DISTINCT CASE WHEN fe.event_stage = 'CART'     THEN fe.customer_id END) AS carted,
       COUNT(DISTINCT CASE WHEN fe.event_stage = 'CHECKOUT' THEN fe.customer_id END) AS checked_out,
       COUNT(DISTINCT CASE WHEN fe.event_stage = 'ORDER'    THEN fe.customer_id END) AS ordered,
       COUNT(DISTINCT CASE WHEN fe.event_stage = 'PAYMENT'  THEN fe.customer_id END) AS paid,
       COUNT(DISTINCT CASE WHEN fe.event_stage = 'REVIEW'   THEN fe.customer_id END) AS reviewed,
       ROUND(100 * COUNT(DISTINCT CASE WHEN fe.event_stage = 'PAYMENT' THEN fe.customer_id END)
                 / NULLIF(COUNT(DISTINCT CASE WHEN fe.event_stage = 'VIEW' THEN fe.customer_id END), 0), 1)
           AS view_to_paid_pct
FROM funnel_events fe
JOIN products p ON p.product_id = fe.product_id
GROUP BY p.product_id, p.product_title, p.brand, p.category, p.sub_category;


-- ---------------------------------------------------------------------
-- 3. Funnel by gender / category / sub-category
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW vw_category_funnel AS
SELECT p.gender,
       p.category,
       p.sub_category,
       COUNT(DISTINCT CASE WHEN fe.event_stage = 'VIEW'    THEN fe.customer_id END) AS viewed,
       COUNT(DISTINCT CASE WHEN fe.event_stage = 'CART'    THEN fe.customer_id END) AS carted,
       COUNT(DISTINCT CASE WHEN fe.event_stage = 'ORDER'   THEN fe.customer_id END) AS ordered,
       COUNT(DISTINCT CASE WHEN fe.event_stage = 'PAYMENT' THEN fe.customer_id END) AS paid,
       ROUND(100 * COUNT(DISTINCT CASE WHEN fe.event_stage = 'PAYMENT' THEN fe.customer_id END)
                 / NULLIF(COUNT(DISTINCT CASE WHEN fe.event_stage = 'CART' THEN fe.customer_id END), 0), 1)
           AS cart_to_paid_pct
FROM funnel_events fe
JOIN products p ON p.product_id = fe.product_id
GROUP BY p.gender, p.category, p.sub_category;


-- ---------------------------------------------------------------------
-- 4. Funnel by brand
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW vw_brand_funnel AS
SELECT p.brand,
       COUNT(DISTINCT CASE WHEN fe.event_stage = 'VIEW'    THEN fe.customer_id END) AS viewed,
       COUNT(DISTINCT CASE WHEN fe.event_stage = 'CART'    THEN fe.customer_id END) AS carted,
       COUNT(DISTINCT CASE WHEN fe.event_stage = 'ORDER'   THEN fe.customer_id END) AS ordered,
       COUNT(DISTINCT CASE WHEN fe.event_stage = 'PAYMENT' THEN fe.customer_id END) AS paid,
       ROUND(100 * COUNT(DISTINCT CASE WHEN fe.event_stage = 'PAYMENT' THEN fe.customer_id END)
                 / NULLIF(COUNT(DISTINCT CASE WHEN fe.event_stage = 'VIEW' THEN fe.customer_id END), 0), 1)
           AS view_to_paid_pct
FROM funnel_events fe
JOIN products p ON p.product_id = fe.product_id
GROUP BY p.brand;


-- ---------------------------------------------------------------------
-- 5. Cart abandonment
--    A (customer, product) pair that reached CART but has no PAYMENT
--    for that product at or after the latest cart time.
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW vw_cart_abandonment AS
SELECT c.customer_id,
       CONCAT(cu.first_name, ' ', cu.last_name) AS customer_name,
       cu.email,
       c.product_id,
       p.product_title,
       p.price,
       c.last_carted_at,
       TIMESTAMPDIFF(HOUR, c.last_carted_at, NOW()) AS hours_since_cart
FROM (
    SELECT customer_id, product_id, MAX(event_timestamp) AS last_carted_at
    FROM funnel_events
    WHERE event_stage = 'CART'
    GROUP BY customer_id, product_id
) c
JOIN customers cu ON cu.customer_id = c.customer_id
JOIN products  p  ON p.product_id   = c.product_id
WHERE NOT EXISTS (
    SELECT 1
    FROM funnel_events pay
    WHERE pay.event_stage = 'PAYMENT'
      AND pay.customer_id = c.customer_id
      AND pay.product_id  = c.product_id
      AND pay.event_timestamp >= c.last_carted_at
);


-- ---------------------------------------------------------------------
-- 6. Seller sales (only orders that have a successful payment)
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW vw_seller_sales AS
SELECT s.seller_id,
       s.seller_name,
       s.rating,
       COUNT(DISTINCT p.product_id)        AS products_listed,
       COUNT(DISTINCT paid.order_id)       AS paid_orders,
       COALESCE(SUM(paid.quantity), 0)     AS units_sold,
       COALESCE(SUM(paid.subtotal), 0)     AS revenue
FROM sellers s
LEFT JOIN products p ON p.seller_id = s.seller_id
LEFT JOIN (
    SELECT oi.order_id, oi.product_id, oi.quantity, oi.subtotal
    FROM order_items oi
    WHERE EXISTS (
        SELECT 1 FROM payments pm
        WHERE pm.order_id = oi.order_id
          AND pm.payment_status IN ('Completed', 'Successful', 'Paid')
    )
) paid ON paid.product_id = p.product_id
GROUP BY s.seller_id, s.seller_name, s.rating;


-- ---------------------------------------------------------------------
-- 7. Daily trend: distinct customers per stage per day
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW vw_daily_funnel AS
SELECT DATE(event_timestamp) AS day,
       COUNT(DISTINCT CASE WHEN event_stage = 'VIEW'     THEN customer_id END) AS viewed,
       COUNT(DISTINCT CASE WHEN event_stage = 'CART'     THEN customer_id END) AS carted,
       COUNT(DISTINCT CASE WHEN event_stage = 'CHECKOUT' THEN customer_id END) AS checked_out,
       COUNT(DISTINCT CASE WHEN event_stage = 'ORDER'    THEN customer_id END) AS ordered,
       COUNT(DISTINCT CASE WHEN event_stage = 'PAYMENT'  THEN customer_id END) AS paid,
       COUNT(DISTINCT CASE WHEN event_stage = 'REVIEW'   THEN customer_id END) AS reviewed
FROM funnel_events
GROUP BY DATE(event_timestamp);


-- =====================================================================
--  Stored procedures
-- =====================================================================
DROP PROCEDURE IF EXISTS sp_funnel_between;
DROP PROCEDURE IF EXISTS sp_customer_journey;
DROP PROCEDURE IF EXISTS sp_top_products;

DELIMITER $$

-- Funnel for a date range (both dates inclusive)
--   CALL sp_funnel_between('2026-08-01', '2026-10-31');
CREATE PROCEDURE sp_funnel_between(IN p_start DATE, IN p_end DATE)
BEGIN
    IF p_start IS NULL OR p_end IS NULL OR p_start > p_end THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Give a valid date range: start <= end';
    END IF;

    WITH stages AS (
        SELECT 1 AS stage_order, 'VIEW' AS stage UNION ALL
        SELECT 2, 'CART' UNION ALL SELECT 3, 'CHECKOUT' UNION ALL
        SELECT 4, 'ORDER' UNION ALL SELECT 5, 'PAYMENT' UNION ALL SELECT 6, 'REVIEW'
    ),
    counts AS (
        SELECT s.stage_order, s.stage, COUNT(DISTINCT fe.customer_id) AS customers
        FROM stages s
        LEFT JOIN funnel_events fe
               ON fe.event_stage = s.stage
              AND fe.event_timestamp >= p_start
              AND fe.event_timestamp <  p_end + INTERVAL 1 DAY
        GROUP BY s.stage_order, s.stage
    )
    SELECT stage,
           customers,
           ROUND(100 * customers / NULLIF(LAG(customers) OVER (ORDER BY stage_order), 0), 1)
               AS pct_from_previous
    FROM counts
    ORDER BY stage_order;
END$$

-- Every funnel event of one customer, in time order
--   CALL sp_customer_journey(10);
CREATE PROCEDURE sp_customer_journey(IN p_customer_id INT)
BEGIN
    IF NOT EXISTS (SELECT 1 FROM customers WHERE customer_id = p_customer_id) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'No customer with that id';
    END IF;

    SELECT fe.event_timestamp,
           fe.event_stage,
           fe.product_id,
           p.product_title,
           fe.order_id,
           fe.session_id
    FROM funnel_events fe
    LEFT JOIN products p ON p.product_id = fe.product_id
    WHERE fe.customer_id = p_customer_id
    ORDER BY fe.event_timestamp, fe.event_id;
END$$

-- Best-selling products by revenue from paid orders
--   CALL sp_top_products(10);
CREATE PROCEDURE sp_top_products(IN p_limit INT)
BEGIN
    SELECT p.product_id,
           p.product_title,
           p.brand,
           SUM(oi.quantity) AS units_sold,
           SUM(oi.subtotal) AS revenue,
           p.stock_quantity AS stock_left
    FROM order_items oi
    JOIN products p ON p.product_id = oi.product_id
    WHERE EXISTS (
        SELECT 1 FROM payments pm
        WHERE pm.order_id = oi.order_id
          AND pm.payment_status IN ('Completed', 'Successful', 'Paid')
    )
    GROUP BY p.product_id, p.product_title, p.brand, p.stock_quantity
    ORDER BY revenue DESC
    LIMIT p_limit;
END$$

DELIMITER ;


-- =====================================================================
--  Try them (each one opens a result tab in Workbench)
-- =====================================================================
SELECT * FROM vw_funnel_summary;
SELECT * FROM vw_cart_abandonment;
SELECT * FROM vw_seller_sales ORDER BY revenue DESC LIMIT 5;
CALL sp_top_products(5);

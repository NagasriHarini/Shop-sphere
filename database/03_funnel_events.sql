-- =====================================================================
--  03  funnel_events table (the funnel event log)
--  Database : shopping_funnel (MySQL 8)
--  Run in MySQL Workbench: open this file, then Execute All (Ctrl+Shift+Enter)
--
--  What this script does
--    1. Creates the funnel_events table (it is in models.py but was never
--       created in MySQL, so every funnel write was silently failing).
--    2. Backfills it from data that already exists in other tables
--       (product_views, cart_events, orders/order_items, payments, reviews),
--       so the funnel isn't empty on day one.
--    3. Prints a few check queries at the end.
--
--  Safe to re-run: the table is only created if missing, and the backfill
--  only runs while the table is still empty.
-- =====================================================================

USE shopping_funnel;

-- ---------------------------------------------------------------------
-- 1. Table
-- ---------------------------------------------------------------------
-- One row = one customer reaching one stage of the funnel.
-- Stages, in order:
--   VIEW -> CART -> CHECKOUT -> ORDER -> PAYMENT -> REVIEW
--
-- session_id is NULLable: rows backfilled from old orders/payments/reviews
-- have no known session, and the 04 triggers (PAYMENT, REVIEW) may fire
-- for a customer with no open session.
-- product_id is NULLable: some events can be order-level.
-- order_id is filled only from the ORDER stage onwards.
CREATE TABLE IF NOT EXISTS funnel_events (
    event_id        INT          NOT NULL AUTO_INCREMENT,
    customer_id     INT          NOT NULL,
    session_id      INT          NULL,
    product_id      INT          NULL,
    event_stage     VARCHAR(30)  NOT NULL,
    event_timestamp DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    order_id        INT          NULL,

    PRIMARY KEY (event_id),

    CONSTRAINT chk_funnel_stage CHECK (
        event_stage IN ('VIEW','CART','CHECKOUT','ORDER','PAYMENT','REVIEW')
    ),

    CONSTRAINT fk_funnel_customer FOREIGN KEY (customer_id)
        REFERENCES customers (customer_id)    ON DELETE CASCADE,
    CONSTRAINT fk_funnel_session  FOREIGN KEY (session_id)
        REFERENCES user_sessions (session_id) ON DELETE SET NULL,
    CONSTRAINT fk_funnel_product  FOREIGN KEY (product_id)
        REFERENCES products (product_id)      ON DELETE SET NULL,
    CONSTRAINT fk_funnel_order    FOREIGN KEY (order_id)
        REFERENCES orders (order_id)          ON DELETE SET NULL,

    -- Indexes for the funnel queries
    INDEX idx_funnel_stage_customer (event_stage, customer_id),   -- overall funnel
    INDEX idx_funnel_product_stage  (product_id, event_stage),    -- per-product funnel
    INDEX idx_funnel_customer_time  (customer_id, event_timestamp), -- customer journey
    INDEX idx_funnel_time           (event_timestamp)             -- daily / weekly trends
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ---------------------------------------------------------------------
-- 2. Backfill from existing data (only while the table is empty)
-- ---------------------------------------------------------------------
SET @fe_empty := (SELECT COUNT(*) = 0 FROM funnel_events);

START TRANSACTION;

-- VIEW  <- product_views
INSERT INTO funnel_events (customer_id, session_id, product_id, event_stage, event_timestamp)
SELECT pv.customer_id, pv.session_id, pv.product_id, 'VIEW',
       COALESCE(pv.view_timestamp, us.start_time, NOW())
FROM product_views pv
LEFT JOIN user_sessions us ON us.session_id = pv.session_id
WHERE @fe_empty;

-- CART  <- cart_events (ADD only)
INSERT INTO funnel_events (customer_id, product_id, event_stage, event_timestamp)
SELECT ce.customer_id, ce.product_id, 'CART', COALESCE(ce.event_timestamp, NOW())
FROM cart_events ce
WHERE ce.event_type = 'ADD' AND @fe_empty;

-- CHECKOUT and ORDER  <- orders + order_items (one row per product in the order)
INSERT INTO funnel_events (customer_id, product_id, event_stage, event_timestamp, order_id)
SELECT o.customer_id, oi.product_id, 'CHECKOUT', COALESCE(o.order_date, NOW()), NULL
FROM orders o
JOIN order_items oi ON oi.order_id = o.order_id
WHERE @fe_empty;

INSERT INTO funnel_events (customer_id, product_id, event_stage, event_timestamp, order_id)
SELECT o.customer_id, oi.product_id, 'ORDER', COALESCE(o.order_date, NOW()), o.order_id
FROM orders o
JOIN order_items oi ON oi.order_id = o.order_id
WHERE @fe_empty;

-- PAYMENT  <- successful payments (one row per product in the paid order)
INSERT INTO funnel_events (customer_id, product_id, event_stage, event_timestamp, order_id)
SELECT o.customer_id, oi.product_id, 'PAYMENT', COALESCE(p.payment_date, NOW()), o.order_id
FROM payments p
JOIN orders o       ON o.order_id  = p.order_id
JOIN order_items oi ON oi.order_id = o.order_id
WHERE p.payment_status IN ('Completed', 'Successful', 'Paid') AND @fe_empty;

-- REVIEW  <- reviews
INSERT INTO funnel_events (customer_id, product_id, event_stage, event_timestamp)
SELECT r.customer_id, r.product_id, 'REVIEW', COALESCE(r.review_date, NOW())
FROM reviews r
WHERE @fe_empty;

COMMIT;


-- ---------------------------------------------------------------------
-- 3. Checks (look at the result tabs in Workbench)
-- ---------------------------------------------------------------------

-- 3a. Rows per stage
SELECT event_stage, COUNT(*) AS events, COUNT(DISTINCT customer_id) AS customers
FROM funnel_events
GROUP BY event_stage
ORDER BY FIELD(event_stage,'VIEW','CART','CHECKOUT','ORDER','PAYMENT','REVIEW');

-- 3b. The overall funnel: distinct customers per stage and % carried
--     over from the previous stage (the same numbers the admin Funnel page shows)
WITH stage_counts AS (
    SELECT s.stage, s.pos, COUNT(DISTINCT fe.customer_id) AS customers
    FROM (SELECT 'VIEW' AS stage, 1 AS pos UNION ALL SELECT 'CART', 2
          UNION ALL SELECT 'CHECKOUT', 3 UNION ALL SELECT 'ORDER', 4
          UNION ALL SELECT 'PAYMENT', 5 UNION ALL SELECT 'REVIEW', 6) s
    LEFT JOIN funnel_events fe ON fe.event_stage = s.stage
    GROUP BY s.stage, s.pos
)
SELECT stage,
       customers,
       ROUND(100 * customers / NULLIF(LAG(customers) OVER (ORDER BY pos), 0), 1)
           AS pct_from_previous_stage
FROM stage_counts
ORDER BY pos;

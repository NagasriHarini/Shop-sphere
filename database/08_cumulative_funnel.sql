-- =====================================================================
--  08  Cumulative ("implied stage") funnel
--  Database : shopping_funnel (MySQL 8)
--  Run in MySQL Workbench: open this file, then Execute All
--  Requires: 03-07 already run.  Safe to re-run.
--
--  RULE: a customer who reached a later stage is also counted in every
--  earlier stage, because you cannot pay without ordering, order without
--  checking out, and so on:
--        VIEW >= CART >= CHECKOUT >= ORDER >= PAYMENT
--  So a customer whose only recorded event is PAYMENT (e.g. an old order
--  placed before view/cart tracking existed) still counts as having viewed
--  and carted. REVIEW is counted on its own, because a review does not
--  prove a purchase.
--
--  How: FIELD(event_stage, 'VIEW','CART','CHECKOUT','ORDER','PAYMENT') turns
--  a stage into a rank 1..5 (REVIEW -> 0). For each customer (or customer +
--  product, customer + day, session) we take the MAX rank reached, and a
--  stage with rank k counts everyone whose max rank >= k.
--
--  Column names are unchanged, so the website keeps working.
-- =====================================================================

USE shopping_funnel;

-- ---------------------------------------------------------------------
-- 1. Overall funnel
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW vw_funnel_summary AS
WITH reach AS (
    SELECT customer_id,
           MAX(FIELD(event_stage, 'VIEW','CART','CHECKOUT','ORDER','PAYMENT')) AS max_rank,
           MAX(event_stage = 'REVIEW') AS reviewed
    FROM funnel_events
    GROUP BY customer_id
),
stages AS (
    SELECT 1 AS stage_order, 'VIEW' AS stage UNION ALL
    SELECT 2, 'CART' UNION ALL SELECT 3, 'CHECKOUT' UNION ALL
    SELECT 4, 'ORDER' UNION ALL SELECT 5, 'PAYMENT' UNION ALL SELECT 6, 'REVIEW'
),
counts AS (
    SELECT s.stage_order, s.stage,
           CASE WHEN s.stage_order <= 5
                THEN (SELECT COUNT(*) FROM reach r WHERE r.max_rank >= s.stage_order)
                ELSE (SELECT COUNT(*) FROM reach r WHERE r.reviewed = 1) END AS customers,
           (SELECT COUNT(*) FROM funnel_events fe WHERE fe.event_stage = s.stage) AS events
    FROM stages s
)
SELECT stage_order, stage, customers, events,
       ROUND(100 * customers / NULLIF(LAG(customers) OVER (ORDER BY stage_order), 0), 1) AS pct_from_previous,
       ROUND(100 * customers / NULLIF(FIRST_VALUE(customers) OVER (ORDER BY stage_order), 0), 1) AS pct_from_view
FROM counts;


-- ---------------------------------------------------------------------
-- 2. Per product / category / brand: reach is per customer + product
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW vw_customer_product_reach AS
SELECT customer_id, product_id,
       MAX(FIELD(event_stage, 'VIEW','CART','CHECKOUT','ORDER','PAYMENT')) AS max_rank,
       MAX(event_stage = 'REVIEW') AS reviewed
FROM funnel_events
WHERE product_id IS NOT NULL
GROUP BY customer_id, product_id;

CREATE OR REPLACE VIEW vw_product_funnel AS
SELECT p.product_id, p.product_title, p.brand, p.category, p.sub_category,
       SUM(r.max_rank >= 1) AS viewed,
       SUM(r.max_rank >= 2) AS carted,
       SUM(r.max_rank >= 3) AS checked_out,
       SUM(r.max_rank >= 4) AS ordered,
       SUM(r.max_rank >= 5) AS paid,
       SUM(r.reviewed)      AS reviewed,
       ROUND(100 * SUM(r.max_rank >= 5) / NULLIF(SUM(r.max_rank >= 1), 0), 1) AS view_to_paid_pct
FROM vw_customer_product_reach r
JOIN products p ON p.product_id = r.product_id
GROUP BY p.product_id, p.product_title, p.brand, p.category, p.sub_category;

-- category / brand: a customer counts once per group (best stage on any product in it)
CREATE OR REPLACE VIEW vw_category_funnel AS
WITH g AS (
    SELECT r.customer_id, p.gender, p.category, p.sub_category, MAX(r.max_rank) AS max_rank
    FROM vw_customer_product_reach r JOIN products p ON p.product_id = r.product_id
    GROUP BY r.customer_id, p.gender, p.category, p.sub_category
)
SELECT gender, category, sub_category,
       SUM(max_rank >= 1) AS viewed,
       SUM(max_rank >= 2) AS carted,
       SUM(max_rank >= 4) AS ordered,
       SUM(max_rank >= 5) AS paid,
       ROUND(100 * SUM(max_rank >= 5) / NULLIF(SUM(max_rank >= 2), 0), 1) AS cart_to_paid_pct
FROM g
GROUP BY gender, category, sub_category;

CREATE OR REPLACE VIEW vw_brand_funnel AS
WITH g AS (
    SELECT r.customer_id, p.brand, MAX(r.max_rank) AS max_rank
    FROM vw_customer_product_reach r JOIN products p ON p.product_id = r.product_id
    GROUP BY r.customer_id, p.brand
)
SELECT brand,
       SUM(max_rank >= 1) AS viewed,
       SUM(max_rank >= 2) AS carted,
       SUM(max_rank >= 4) AS ordered,
       SUM(max_rank >= 5) AS paid,
       ROUND(100 * SUM(max_rank >= 5) / NULLIF(SUM(max_rank >= 1), 0), 1) AS view_to_paid_pct
FROM g
GROUP BY brand;


-- ---------------------------------------------------------------------
-- 3. Daily trend: reach per customer per day
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW vw_daily_funnel AS
WITH d AS (
    SELECT DATE(event_timestamp) AS day, customer_id,
           MAX(FIELD(event_stage, 'VIEW','CART','CHECKOUT','ORDER','PAYMENT')) AS max_rank,
           MAX(event_stage = 'REVIEW') AS reviewed
    FROM funnel_events
    GROUP BY DATE(event_timestamp), customer_id
)
SELECT day,
       SUM(max_rank >= 1) AS viewed,
       SUM(max_rank >= 2) AS carted,
       SUM(max_rank >= 3) AS checked_out,
       SUM(max_rank >= 4) AS ordered,
       SUM(max_rank >= 5) AS paid,
       SUM(reviewed)      AS reviewed
FROM d
GROUP BY day;


-- ---------------------------------------------------------------------
-- 4. Device funnel: reach per session
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW vw_device_funnel AS
WITH s AS (
    SELECT us.session_id, COALESCE(us.device_type, 'Unknown') AS device_type,
           COALESCE(MAX(FIELD(fe.event_stage, 'VIEW','CART','CHECKOUT','ORDER','PAYMENT')), 0) AS max_rank
    FROM user_sessions us
    LEFT JOIN funnel_events fe ON fe.session_id = us.session_id
    GROUP BY us.session_id, COALESCE(us.device_type, 'Unknown')
)
SELECT device_type,
       COUNT(*)            AS sessions,
       SUM(max_rank >= 1)  AS viewed,
       SUM(max_rank >= 2)  AS carted,
       SUM(max_rank >= 4)  AS ordered,
       SUM(max_rank >= 5)  AS paid,
       ROUND(100 * SUM(max_rank >= 4) / NULLIF(SUM(max_rank >= 2), 0), 1) AS cart_to_order_pct,
       ROUND(100 * SUM(max_rank >= 4) / NULLIF(COUNT(*), 0), 1)            AS session_conversion_pct
FROM s
GROUP BY device_type;


-- ---------------------------------------------------------------------
-- 5. Date-range funnel procedure (same rule, only events in the range)
-- ---------------------------------------------------------------------
DROP PROCEDURE IF EXISTS sp_funnel_between;
DELIMITER $$
CREATE PROCEDURE sp_funnel_between(IN p_start DATE, IN p_end DATE)
BEGIN
    IF p_start IS NULL OR p_end IS NULL OR p_start > p_end THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Give a valid date range: start <= end';
    END IF;

    WITH reach AS (
        SELECT customer_id,
               MAX(FIELD(event_stage, 'VIEW','CART','CHECKOUT','ORDER','PAYMENT')) AS max_rank,
               MAX(event_stage = 'REVIEW') AS reviewed
        FROM funnel_events
        WHERE event_timestamp >= p_start AND event_timestamp < p_end + INTERVAL 1 DAY
        GROUP BY customer_id
    ),
    stages AS (
        SELECT 1 AS stage_order, 'VIEW' AS stage UNION ALL
        SELECT 2, 'CART' UNION ALL SELECT 3, 'CHECKOUT' UNION ALL
        SELECT 4, 'ORDER' UNION ALL SELECT 5, 'PAYMENT' UNION ALL SELECT 6, 'REVIEW'
    ),
    counts AS (
        SELECT s.stage_order, s.stage,
               CASE WHEN s.stage_order <= 5
                    THEN (SELECT COUNT(*) FROM reach r WHERE r.max_rank >= s.stage_order)
                    ELSE (SELECT COUNT(*) FROM reach r WHERE r.reviewed = 1) END AS customers
        FROM stages s
    )
    SELECT stage, customers,
           ROUND(100 * customers / NULLIF(LAG(customers) OVER (ORDER BY stage_order), 0), 1) AS pct_from_previous
    FROM counts
    ORDER BY stage_order;
END$$
DELIMITER ;


-- Check
SELECT stage, customers, pct_from_previous, pct_from_view FROM vw_funnel_summary;

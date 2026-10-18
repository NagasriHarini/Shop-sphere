-- =====================================================================
--  06  Data clean-up + integrity constraints (CHECK / UNIQUE)
--  Database : shopping_funnel (MySQL 8)
--  Run in MySQL Workbench: open this file, then Execute All (Ctrl+Shift+Enter)
--  Requires: 03, 04 and 05 already run.
--
--  Part A fixes existing rows that would break the new rules.
--  Part B adds the rules (CHECK / UNIQUE constraints), so bad data
--  can never be inserted again, whichever program writes it.
--
--  Safe to re-run: every fix is idempotent and each constraint is only
--  added if it doesn't exist yet.
--
--  NOTE: plain-text passwords are NOT fixed here. MySQL can't produce
--  Django's password hashes, so that is done by the Django command
--      python manage.py hash_plain_passwords
-- =====================================================================

USE shopping_funnel;

-- Workbench's "Safe Updates" mode blocks UPDATE/DELETE without a key in WHERE
-- (Error 1175). Turn it off for this script only; it's turned back on at the end.
SET @old_safe_updates := @@SQL_SAFE_UPDATES;
SET SQL_SAFE_UPDATES = 0;

-- =====================================================================
--  PART A. Clean up existing data
-- =====================================================================
START TRANSACTION;

-- A1. Order total must equal the sum of its items (order 1 said 1598, items = 9436)
UPDATE orders o
JOIN (SELECT order_id, SUM(subtotal) AS items_total
      FROM order_items GROUP BY order_id) t ON t.order_id = o.order_id
SET o.total_amount = t.items_total
WHERE o.total_amount <> t.items_total;

-- A2. One spelling for a successful payment: 'Successful' -> 'Completed'
UPDATE payments SET payment_status = 'Completed' WHERE payment_status = 'Successful';

-- A3. Orders that have a completed payment are 'Paid', not 'Pending'
UPDATE orders o
SET o.order_status = 'Paid'
WHERE o.order_status = 'Pending'
  AND EXISTS (SELECT 1 FROM payments p
              WHERE p.order_id = o.order_id AND p.payment_status = 'Completed');

-- A4. Duplicate cart rows (same customer + same product, e.g. a double click):
--     keep the oldest row with the largest quantity seen, delete the extras.
UPDATE cart keep
JOIN (SELECT customer_id, product_id, MIN(cart_id) AS keep_id, MAX(quantity) AS total_qty
      FROM cart GROUP BY customer_id, product_id HAVING COUNT(*) > 1) d
  ON keep.cart_id = d.keep_id
SET keep.quantity = d.total_qty;

CREATE TEMPORARY TABLE tmp_dup_cart AS
SELECT c.cart_id
FROM cart c
JOIN (SELECT customer_id, product_id, MIN(cart_id) AS keep_id
      FROM cart GROUP BY customer_id, product_id HAVING COUNT(*) > 1) d
  ON d.customer_id = c.customer_id AND d.product_id = c.product_id
WHERE c.cart_id <> d.keep_id;

DELETE FROM cart_events WHERE cart_id IN (SELECT cart_id FROM tmp_dup_cart);
DELETE FROM cart        WHERE cart_id IN (SELECT cart_id FROM tmp_dup_cart);
DROP TEMPORARY TABLE tmp_dup_cart;

-- A5. Missing timestamps: fill from the best evidence available
--     session start = its first product view, else its first funnel event
UPDATE user_sessions us
SET us.start_time = COALESCE(
        (SELECT MIN(pv.view_timestamp) FROM product_views pv WHERE pv.session_id = us.session_id),
        (SELECT MIN(fe.event_timestamp) FROM funnel_events fe WHERE fe.session_id = us.session_id),
        NOW())
WHERE us.start_time IS NULL;

UPDATE product_views pv
JOIN user_sessions us ON us.session_id = pv.session_id
SET pv.view_timestamp = us.start_time
WHERE pv.view_timestamp IS NULL;

UPDATE cart c
SET c.added_date = COALESCE(
        (SELECT MIN(ce.event_timestamp) FROM cart_events ce WHERE ce.cart_id = c.cart_id),
        NOW())
WHERE c.added_date IS NULL;

-- A6. Empty strings -> NULL for optional customer gender
UPDATE customers SET gender = NULL WHERE gender = '';

COMMIT;


-- =====================================================================
--  PART B. Constraints
--  Two small helper procedures add a constraint only if it's missing,
--  so this file can be run again without "duplicate constraint" errors.
-- =====================================================================
DROP PROCEDURE IF EXISTS tmp_add_check;
DROP PROCEDURE IF EXISTS tmp_add_unique;

DELIMITER $$
CREATE PROCEDURE tmp_add_check(IN p_table VARCHAR(64), IN p_name VARCHAR(64), IN p_expr TEXT)
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.TABLE_CONSTRAINTS
                   WHERE CONSTRAINT_SCHEMA = DATABASE()
                     AND TABLE_NAME = p_table AND CONSTRAINT_NAME = p_name) THEN
        SET @ddl = CONCAT('ALTER TABLE `', p_table, '` ADD CONSTRAINT `', p_name, '` CHECK (', p_expr, ')');
        PREPARE stmt FROM @ddl;
        EXECUTE stmt;
        DEALLOCATE PREPARE stmt;
    END IF;
END$$

CREATE PROCEDURE tmp_add_unique(IN p_table VARCHAR(64), IN p_name VARCHAR(64), IN p_cols TEXT)
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.STATISTICS
                   WHERE TABLE_SCHEMA = DATABASE()
                     AND TABLE_NAME = p_table AND INDEX_NAME = p_name) THEN
        SET @ddl = CONCAT('ALTER TABLE `', p_table, '` ADD CONSTRAINT `', p_name, '` UNIQUE (', p_cols, ')');
        PREPARE stmt FROM @ddl;
        EXECUTE stmt;
        DEALLOCATE PREPARE stmt;
    END IF;
END$$
DELIMITER ;

-- products
CALL tmp_add_check('products', 'chk_products_price', 'price IS NULL OR price >= 0');
CALL tmp_add_check('products', 'chk_products_stock', 'stock_quantity IS NULL OR stock_quantity >= 0');

-- cart: positive quantity, one row per customer + product
CALL tmp_add_check ('cart', 'chk_cart_quantity', 'quantity > 0');
CALL tmp_add_unique('cart', 'uq_cart_customer_product', 'customer_id, product_id');

-- cart_events: only the event types the app writes
CALL tmp_add_check('cart_events', 'chk_cart_event_type',
                   'event_type IN (''ADD'', ''INCREASE'', ''DECREASE'', ''REMOVE'')');

-- orders
CALL tmp_add_check('orders', 'chk_orders_total', 'total_amount >= 0');
CALL tmp_add_check('orders', 'chk_orders_status',
                   'order_status IN (''Pending'', ''Paid'', ''Shipped'', ''Delivered'', ''Cancelled'')');

-- order_items: positive quantity, non-negative price, subtotal = qty x price
CALL tmp_add_check('order_items', 'chk_items_quantity', 'quantity > 0');
CALL tmp_add_check('order_items', 'chk_items_price',    'unit_price >= 0');
CALL tmp_add_check('order_items', 'chk_items_subtotal', 'subtotal = quantity * unit_price');

-- payments
CALL tmp_add_check ('payments', 'chk_payments_amount', 'amount >= 0');
CALL tmp_add_check ('payments', 'chk_payments_status',
                    'payment_status IN (''Pending'', ''Completed'', ''Failed'', ''Refunded'')');
CALL tmp_add_unique('payments', 'uq_payments_transaction', 'transaction_id');

-- sellers / customers
CALL tmp_add_check('sellers',   'chk_sellers_rating', 'rating IS NULL OR rating BETWEEN 0 AND 5');
CALL tmp_add_check('sellers',   'chk_sellers_email',  'email LIKE ''%_@_%._%''');
CALL tmp_add_check('customers', 'chk_customers_email', 'email LIKE ''%_@_%._%''');
CALL tmp_add_check('customers', 'chk_customers_gender',
                   'gender IS NULL OR gender IN (''Male'', ''Female'', ''Other'')');

DROP PROCEDURE tmp_add_check;
DROP PROCEDURE tmp_add_unique;


-- =====================================================================
--  PART C. Keep cart history when a cart row is removed
--  Before: cart_events.cart_id -> cart was RESTRICT, so the "Remove" button
--  failed (its own REMOVE event blocked the delete), and checkout had to
--  delete cart history to empty the cart.
--  After : cart_id becomes NULL-able with ON DELETE SET NULL. The cart row
--  can be deleted and its events stay for the funnel / abandonment reports.
-- =====================================================================
DROP PROCEDURE IF EXISTS tmp_fix_cart_events_fk;
DELIMITER $$
CREATE PROCEDURE tmp_fix_cart_events_fk()
BEGIN
    DECLARE v_fk VARCHAR(64);
    DECLARE v_rule VARCHAR(64);

    SELECT rc.CONSTRAINT_NAME, rc.DELETE_RULE INTO v_fk, v_rule
    FROM information_schema.REFERENTIAL_CONSTRAINTS rc
    WHERE rc.CONSTRAINT_SCHEMA = DATABASE()
      AND rc.TABLE_NAME = 'cart_events'
      AND rc.REFERENCED_TABLE_NAME = 'cart'
    LIMIT 1;

    IF v_fk IS NOT NULL AND v_rule <> 'SET NULL' THEN
        SET @ddl = CONCAT('ALTER TABLE cart_events DROP FOREIGN KEY `', v_fk, '`');
        PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;
        SET v_fk = NULL;
    END IF;

    IF EXISTS (SELECT 1 FROM information_schema.COLUMNS
               WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'cart_events'
                 AND COLUMN_NAME = 'cart_id' AND IS_NULLABLE = 'NO') THEN
        ALTER TABLE cart_events MODIFY cart_id INT NULL;
    END IF;

    IF v_fk IS NULL THEN
        ALTER TABLE cart_events
            ADD CONSTRAINT fk_cart_events_cart FOREIGN KEY (cart_id)
                REFERENCES cart (cart_id) ON DELETE SET NULL;
    END IF;
END$$
DELIMITER ;

CALL tmp_fix_cart_events_fk();
DROP PROCEDURE tmp_fix_cart_events_fk;


-- =====================================================================
--  Check: every CHECK / UNIQUE constraint now on the tables
-- =====================================================================
SELECT TABLE_NAME, CONSTRAINT_NAME, CONSTRAINT_TYPE
FROM information_schema.TABLE_CONSTRAINTS
WHERE CONSTRAINT_SCHEMA = 'shopping_funnel'
  AND CONSTRAINT_TYPE IN ('CHECK', 'UNIQUE')
  AND TABLE_NAME NOT LIKE 'auth\_%' AND TABLE_NAME NOT LIKE 'django\_%'
ORDER BY TABLE_NAME, CONSTRAINT_TYPE, CONSTRAINT_NAME;

-- Check: cart_events -> cart now says SET NULL
SELECT CONSTRAINT_NAME, TABLE_NAME, REFERENCED_TABLE_NAME, DELETE_RULE
FROM information_schema.REFERENTIAL_CONSTRAINTS
WHERE CONSTRAINT_SCHEMA = 'shopping_funnel' AND TABLE_NAME = 'cart_events';

SET SQL_SAFE_UPDATES = @old_safe_updates;

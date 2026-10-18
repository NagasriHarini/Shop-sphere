-- =====================================================================
--  04  Triggers
--  Database : shopping_funnel (MySQL 8)
--  Run in MySQL Workbench: open this file, then Execute All (Ctrl+Shift+Enter)
--  Requires: 03_funnel_events.sql already run.
--
--  The Django code already logs VIEW, CART, CHECKOUT and ORDER.
--  These triggers let the DATABASE handle the rest by itself:
--
--    trg_payments_after_insert       payment saved   -> PAYMENT funnel events
--    trg_reviews_after_insert        review saved    -> REVIEW funnel event
--    trg_order_items_before_insert   order line      -> block it if stock is too low
--    trg_order_items_after_insert    order line      -> reduce product stock
--
--  Safe to re-run: each trigger is dropped and recreated.
-- =====================================================================

USE shopping_funnel;

DROP TRIGGER IF EXISTS trg_payments_after_insert;
DROP TRIGGER IF EXISTS trg_reviews_after_insert;
DROP TRIGGER IF EXISTS trg_order_items_before_insert;
DROP TRIGGER IF EXISTS trg_order_items_after_insert;

DELIMITER $$

-- ---------------------------------------------------------------------
-- 1. PAYMENT stage
--    When a successful payment is inserted, log one PAYMENT event per
--    product in that order (so the per-product funnel works too).
--    The session is the customer's most recent login session, if any.
-- ---------------------------------------------------------------------
CREATE TRIGGER trg_payments_after_insert
AFTER INSERT ON payments
FOR EACH ROW
BEGIN
    IF NEW.payment_status IN ('Completed', 'Successful', 'Paid') THEN
        INSERT INTO funnel_events
            (customer_id, session_id, product_id, event_stage, event_timestamp, order_id)
        SELECT o.customer_id,
               (SELECT us.session_id
                  FROM user_sessions us
                 WHERE us.customer_id = o.customer_id
                 ORDER BY us.session_id DESC
                 LIMIT 1),
               oi.product_id,
               'PAYMENT',
               COALESCE(NEW.payment_date, NOW()),
               o.order_id
        FROM orders o
        JOIN order_items oi ON oi.order_id = o.order_id
        WHERE o.order_id = NEW.order_id;
    END IF;
END$$

-- ---------------------------------------------------------------------
-- 2. REVIEW stage
-- ---------------------------------------------------------------------
CREATE TRIGGER trg_reviews_after_insert
AFTER INSERT ON reviews
FOR EACH ROW
BEGIN
    INSERT INTO funnel_events
        (customer_id, session_id, product_id, event_stage, event_timestamp)
    VALUES (
        NEW.customer_id,
        (SELECT us.session_id
           FROM user_sessions us
          WHERE us.customer_id = NEW.customer_id
          ORDER BY us.session_id DESC
          LIMIT 1),
        NEW.product_id,
        'REVIEW',
        COALESCE(NEW.review_date, NOW())
    );
END$$

-- ---------------------------------------------------------------------
-- 3. Stock check: refuse an order line if there isn't enough stock.
--    SIGNAL raises an error, which cancels the INSERT. Django runs
--    checkout in one transaction, so the whole order is rolled back.
-- ---------------------------------------------------------------------
CREATE TRIGGER trg_order_items_before_insert
BEFORE INSERT ON order_items
FOR EACH ROW
BEGIN
    DECLARE v_stock INT;
    DECLARE v_title VARCHAR(255);
    DECLARE v_msg   VARCHAR(255);

    IF NEW.quantity <= 0 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Quantity must be greater than 0';
    END IF;

    -- FOR UPDATE locks the product row so two buyers can't both take the last item
    SELECT stock_quantity, product_title
      INTO v_stock, v_title
      FROM products
     WHERE product_id = NEW.product_id
       FOR UPDATE;

    IF v_stock IS NOT NULL AND v_stock < NEW.quantity THEN
        SET v_msg = CONCAT('Not enough stock for "', LEFT(COALESCE(v_title, NEW.product_id), 120),
                           '": only ', v_stock, ' left');
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = v_msg;
    END IF;
END$$

-- ---------------------------------------------------------------------
-- 4. Reduce stock after the order line is saved
-- ---------------------------------------------------------------------
CREATE TRIGGER trg_order_items_after_insert
AFTER INSERT ON order_items
FOR EACH ROW
BEGIN
    UPDATE products
       SET stock_quantity = stock_quantity - NEW.quantity
     WHERE product_id = NEW.product_id
       AND stock_quantity IS NOT NULL;
END$$

DELIMITER ;


-- ---------------------------------------------------------------------
-- Check: list the triggers just created
-- ---------------------------------------------------------------------
SELECT TRIGGER_NAME, EVENT_MANIPULATION AS on_event, EVENT_OBJECT_TABLE AS on_table,
       ACTION_TIMING AS timing
FROM information_schema.TRIGGERS
WHERE TRIGGER_SCHEMA = 'shopping_funnel'
ORDER BY EVENT_OBJECT_TABLE, ACTION_TIMING DESC;

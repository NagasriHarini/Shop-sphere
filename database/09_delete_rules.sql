-- =====================================================================
--  09  ON DELETE rules for an EXISTING database
--  Database : shopping_funnel (MySQL 8)
--  Run in MySQL Workbench: open this file, then Execute All
--  Requires: 01-08 already run.  Safe to re-run.
--
--  01_schema.sql and 03_funnel_events.sql already create these rules on a
--  new database. A database built before they were added still has plain
--  (RESTRICT) foreign keys; this script switches each one to the rule below.
--
--    CASCADE  child rows that only exist because of their parent
--    SET NULL optional links whose history we keep
--    RESTRICT (unchanged) business history: orders -> customer,
--             order_items / product_views / cart_events -> product,
--             products -> seller
-- =====================================================================

USE shopping_funnel;

DROP PROCEDURE IF EXISTS tmp_set_delete_rule;
DELIMITER $$
-- Finds the FK on p_table(p_column) -> p_ref(p_ref_col). If its delete rule
-- is not p_rule, drops it and adds it again as p_name with p_rule.
CREATE PROCEDURE tmp_set_delete_rule(IN p_table VARCHAR(64), IN p_column VARCHAR(64),
                                     IN p_ref VARCHAR(64), IN p_ref_col VARCHAR(64),
                                     IN p_name VARCHAR(64), IN p_rule VARCHAR(20))
BEGIN
    DECLARE v_fk VARCHAR(64) DEFAULT NULL;
    DECLARE v_rule VARCHAR(64) DEFAULT NULL;

    SELECT k.CONSTRAINT_NAME, rc.DELETE_RULE INTO v_fk, v_rule
    FROM information_schema.KEY_COLUMN_USAGE k
    JOIN information_schema.REFERENTIAL_CONSTRAINTS rc
      ON rc.CONSTRAINT_SCHEMA = k.CONSTRAINT_SCHEMA AND rc.CONSTRAINT_NAME = k.CONSTRAINT_NAME
     AND rc.TABLE_NAME = k.TABLE_NAME
    WHERE k.TABLE_SCHEMA = DATABASE() AND k.TABLE_NAME = p_table
      AND k.COLUMN_NAME = p_column AND k.REFERENCED_TABLE_NAME = p_ref
    LIMIT 1;

    IF v_fk IS NOT NULL AND v_rule <> p_rule THEN
        SET @ddl = CONCAT('ALTER TABLE `', p_table, '` DROP FOREIGN KEY `', v_fk, '`');
        PREPARE s FROM @ddl; EXECUTE s; DEALLOCATE PREPARE s;
        SET v_fk = NULL;
    END IF;

    IF v_fk IS NULL THEN
        SET @ddl = CONCAT('ALTER TABLE `', p_table, '` ADD CONSTRAINT `', p_name,
                          '` FOREIGN KEY (`', p_column, '`) REFERENCES `', p_ref,
                          '` (`', p_ref_col, '`) ON DELETE ', p_rule);
        PREPARE s FROM @ddl; EXECUTE s; DEALLOCATE PREPARE s;
    END IF;
END$$
DELIMITER ;

-- a customer's own activity goes with the customer
CALL tmp_set_delete_rule('user_sessions', 'customer_id', 'customers', 'customer_id', 'user_sessions_ibfk_1', 'CASCADE');
CALL tmp_set_delete_rule('cart',          'customer_id', 'customers', 'customer_id', 'fk_cart_customer',     'CASCADE');
CALL tmp_set_delete_rule('cart_events',   'customer_id', 'customers', 'customer_id', 'cart_events_ibfk_1',   'CASCADE');
CALL tmp_set_delete_rule('product_views', 'customer_id', 'customers', 'customer_id', 'product_views_ibfk_1', 'CASCADE');
CALL tmp_set_delete_rule('reviews',       'customer_id', 'customers', 'customer_id', 'fk_review_customer',   'CASCADE');
CALL tmp_set_delete_rule('funnel_events', 'customer_id', 'customers', 'customer_id', 'fk_funnel_customer',   'CASCADE');

-- an order's lines and payments go with the order
CALL tmp_set_delete_rule('order_items',   'order_id',    'orders',    'order_id',    'fk_orderitem_order',   'CASCADE');
CALL tmp_set_delete_rule('payments',      'order_id',    'orders',    'order_id',    'fk_payment_order',     'CASCADE');

-- a session's product views go with the session
CALL tmp_set_delete_rule('product_views', 'session_id',  'user_sessions', 'session_id', 'product_views_ibfk_3', 'CASCADE');

-- a product's cart rows and reviews go with the product
CALL tmp_set_delete_rule('cart',          'product_id',  'products',  'product_id',  'fk_cart_product',      'CASCADE');
CALL tmp_set_delete_rule('reviews',       'product_id',  'products',  'product_id',  'fk_review_product',    'CASCADE');

DROP PROCEDURE tmp_set_delete_rule;

-- Check: every foreign key and its delete rule
SELECT TABLE_NAME, CONSTRAINT_NAME, REFERENCED_TABLE_NAME, DELETE_RULE
FROM information_schema.REFERENTIAL_CONSTRAINTS
WHERE CONSTRAINT_SCHEMA = 'shopping_funnel'
  AND TABLE_NAME NOT LIKE 'auth\_%' AND TABLE_NAME NOT LIKE 'django\_%'
ORDER BY TABLE_NAME, CONSTRAINT_NAME;

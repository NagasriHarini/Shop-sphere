-- =====================================================================
--  Database validation tests - constraints, triggers and delete rules
--  Database : shopping_funnel (MySQL 8)
--
--  Run in MySQL Workbench: open this file, then Execute All.
--  Requires: database/01 ... 09 already run, and at least one customer
--  and one product in stock (the seed data + create_sample_data is enough).
--
--  Every test runs inside ONE transaction that is ROLLED BACK at the end,
--  so the database is left exactly as it was. The last result tab is a
--  table of 16 tests with PASS / FAIL.
--
--  How a test works:
--    expect_error(name, sql)  - runs sql; PASS if MySQL REJECTS it
--    expect_true(name, expr)  - PASS if the SQL expression is true (1)
-- =====================================================================

USE shopping_funnel;

DROP PROCEDURE IF EXISTS t_expect_error;
DROP PROCEDURE IF EXISTS t_expect_true;
DROP TEMPORARY TABLE IF EXISTS test_results;
CREATE TEMPORARY TABLE test_results (
    test_no  INT AUTO_INCREMENT PRIMARY KEY,
    test     VARCHAR(120),
    result   VARCHAR(4),
    detail   VARCHAR(255)
) ENGINE = MEMORY;   -- MEMORY is not transactional, so the results survive the ROLLBACK

DELIMITER $$
CREATE PROCEDURE t_expect_error(IN p_name VARCHAR(120), IN p_sql TEXT)
BEGIN
    DECLARE v_failed INT DEFAULT 0;
    DECLARE v_msg VARCHAR(255) DEFAULT '';
    BEGIN
        DECLARE CONTINUE HANDLER FOR SQLEXCEPTION
        BEGIN
            GET DIAGNOSTICS CONDITION 1 v_msg = MESSAGE_TEXT;
            SET v_failed = 1;
        END;
        SET @t_sql = p_sql;
        PREPARE t_stmt FROM @t_sql;
        EXECUTE t_stmt;
        DEALLOCATE PREPARE t_stmt;
    END;
    INSERT INTO test_results (test, result, detail)
    VALUES (p_name, IF(v_failed = 1, 'PASS', 'FAIL'),
            IF(v_failed = 1, CONCAT('rejected: ', LEFT(v_msg, 200)), 'statement was accepted'));
END$$

CREATE PROCEDURE t_expect_true(IN p_name VARCHAR(120), IN p_expr TEXT)
BEGIN
    SET @t_sql = CONCAT('SELECT (', p_expr, ') INTO @t_ok');
    PREPARE t_stmt FROM @t_sql;
    EXECUTE t_stmt;
    DEALLOCATE PREPARE t_stmt;
    INSERT INTO test_results (test, result, detail)
    VALUES (p_name, IF(@t_ok = 1, 'PASS', 'FAIL'), p_expr);
END$$
DELIMITER ;

START TRANSACTION;

-- Test data: an existing customer and a product with stock
SET @cust := (SELECT MIN(customer_id) FROM customers);
SET @prod := (SELECT MIN(product_id) FROM products WHERE stock_quantity >= 5 AND price IS NOT NULL);
SET @price := (SELECT price FROM products WHERE product_id = @prod);
SET @stock_before := (SELECT stock_quantity FROM products WHERE product_id = @prod);

-- ---------------------------------------------------------------------
-- 1. CHECK, UNIQUE, NOT NULL and FOREIGN KEY constraints reject bad data
-- ---------------------------------------------------------------------
CALL t_expect_error('T01 CHECK: review rating must be 1-5',
     CONCAT('INSERT INTO reviews (customer_id, product_id, rating) VALUES (', @cust, ',', @prod, ', 6)'));
CALL t_expect_error('T02 CHECK: cart quantity must be > 0',
     CONCAT('INSERT INTO cart (customer_id, product_id, quantity) VALUES (', @cust, ',', @prod, ', 0)'));
CALL t_expect_error('T03 CHECK: product price cannot be negative',
     CONCAT('UPDATE products SET price = -1 WHERE product_id = ', @prod));
CALL t_expect_error('T04 CHECK: order status must be a known value',
     CONCAT('INSERT INTO orders (customer_id, total_amount, order_status) VALUES (', @cust, ', 10, ''Lost'')'));
CALL t_expect_error('T05 CHECK: funnel stage must be a known value',
     CONCAT('INSERT INTO funnel_events (customer_id, event_stage) VALUES (', @cust, ', ''CLICK'')'));
CALL t_expect_error('T06 UNIQUE: two customers cannot share an email',
     CONCAT('INSERT INTO customers (first_name, last_name, email, password) ',
            'SELECT ''Dup'', ''User'', email, ''x'' FROM customers WHERE customer_id = ', @cust));
CALL t_expect_error('T07 NOT NULL: customer email is required',
     'INSERT INTO customers (first_name, last_name, email, password) VALUES (''No'', ''Email'', NULL, ''x'')');
CALL t_expect_error('T08 FOREIGN KEY: order for a customer that does not exist',
     'INSERT INTO orders (customer_id, total_amount) VALUES (99999999, 10)');

-- ---------------------------------------------------------------------
-- 2. Triggers
-- ---------------------------------------------------------------------
INSERT INTO orders (customer_id, total_amount, order_status) VALUES (@cust, @price, 'Pending');
SET @ord := LAST_INSERT_ID();

CALL t_expect_error('T09 CHECK: order item subtotal must equal quantity x price',
     CONCAT('INSERT INTO order_items (order_id, product_id, quantity, unit_price, subtotal) VALUES (',
            @ord, ',', @prod, ', 2, ', @price, ', 1)'));
CALL t_expect_error('T10 TRIGGER: order line larger than the stock is refused (SIGNAL 45000)',
     CONCAT('INSERT INTO order_items (order_id, product_id, quantity, unit_price, subtotal) VALUES (',
            @ord, ',', @prod, ',', @stock_before + 1, ',', @price, ',', (@stock_before + 1) * @price, ')'));

INSERT INTO order_items (order_id, product_id, quantity, unit_price, subtotal)
VALUES (@ord, @prod, 2, @price, 2 * @price);
CALL t_expect_true('T11 TRIGGER: placing an order line reduces stock by its quantity',
     CONCAT('(SELECT stock_quantity FROM products WHERE product_id = ', @prod, ') = ', @stock_before - 2));

INSERT INTO payments (order_id, payment_method, amount, payment_status, transaction_id)
VALUES (@ord, 'UPI', 2 * @price, 'Completed', CONCAT('TEST-', @ord, '-', UNIX_TIMESTAMP()));
CALL t_expect_true('T12 TRIGGER: a completed payment writes a PAYMENT funnel event',
     CONCAT('(SELECT COUNT(*) FROM funnel_events WHERE event_stage = ''PAYMENT'' AND order_id = ', @ord, ') = 1'));

SET @rev_before := (SELECT COUNT(*) FROM funnel_events WHERE event_stage = 'REVIEW' AND customer_id = @cust);
INSERT INTO reviews (customer_id, product_id, rating, review_text) VALUES (@cust, @prod, 5, 'test');
CALL t_expect_true('T13 TRIGGER: a review writes a REVIEW funnel event',
     CONCAT('(SELECT COUNT(*) FROM funnel_events WHERE event_stage = ''REVIEW'' AND customer_id = ', @cust,
            ') = ', @rev_before + 1));

-- ---------------------------------------------------------------------
-- 3. ON DELETE rules
-- ---------------------------------------------------------------------
CALL t_expect_error('T14 RESTRICT: a product with order history cannot be deleted',
     CONCAT('DELETE FROM products WHERE product_id = ', @prod));

DELETE FROM orders WHERE order_id = @ord;
CALL t_expect_true('T15 CASCADE: deleting an order deletes its items and payments',
     CONCAT('(SELECT COUNT(*) FROM order_items WHERE order_id = ', @ord, ') + ',
            '(SELECT COUNT(*) FROM payments WHERE order_id = ', @ord, ') = 0'));

INSERT INTO cart (customer_id, product_id, quantity) VALUES (@cust, @prod, 1)
    ON DUPLICATE KEY UPDATE quantity = quantity;
SET @cart := (SELECT cart_id FROM cart WHERE customer_id = @cust AND product_id = @prod);
INSERT INTO cart_events (customer_id, product_id, cart_id, event_type) VALUES (@cust, @prod, @cart, 'ADD');
SET @cev := LAST_INSERT_ID();
DELETE FROM cart WHERE cart_id = @cart;
CALL t_expect_true('T16 SET NULL: removing a cart row keeps its history (cart_id becomes NULL)',
     CONCAT('(SELECT cart_id IS NULL FROM cart_events WHERE event_id = ', @cev, ')'));

-- ---------------------------------------------------------------------
-- Undo everything the tests did, then show the results
-- ---------------------------------------------------------------------
ROLLBACK;

SELECT test_no, test, result, detail FROM test_results ORDER BY test_no;
SELECT SUM(result = 'PASS') AS passed, SUM(result = 'FAIL') AS failed, COUNT(*) AS total FROM test_results;

DROP PROCEDURE t_expect_error;
DROP PROCEDURE t_expect_true;
DROP TEMPORARY TABLE test_results;

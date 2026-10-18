-- =====================================================================
--  Create a MySQL login for the Django website (run once, in Workbench)
--  The website uses this user instead of root. Its password must match
--  config/local_settings.py  (DB_USER / DB_PASSWORD).
-- =====================================================================

CREATE USER IF NOT EXISTS 'shop_app'@'localhost' IDENTIFIED BY 'ShopApp@2026';
CREATE USER IF NOT EXISTS 'shop_app'@'127.0.0.1' IDENTIFIED BY 'ShopApp@2026';

-- If the user already existed with another password, reset it
ALTER USER 'shop_app'@'localhost' IDENTIFIED BY 'ShopApp@2026';
ALTER USER 'shop_app'@'127.0.0.1' IDENTIFIED BY 'ShopApp@2026';

-- Full access to this one database only
GRANT ALL PRIVILEGES ON shopping_funnel.* TO 'shop_app'@'localhost';
GRANT ALL PRIVILEGES ON shopping_funnel.* TO 'shop_app'@'127.0.0.1';
FLUSH PRIVILEGES;

-- Check
SELECT user, host FROM mysql.user WHERE user = 'shop_app';

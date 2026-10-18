-- =====================================================================
--  07  Funnel by device type
--  Database : shopping_funnel (MySQL 8)
--  Run in MySQL Workbench: open this file, then Execute All
--
--  vw_device_funnel: for each device (Mobile / Desktop / Tablet), how many
--  sessions reached each stage and the session conversion rate.
--  Used by the new admin Analytics page.  Safe to re-run.
-- =====================================================================

USE shopping_funnel;

CREATE OR REPLACE VIEW vw_device_funnel AS
SELECT COALESCE(us.device_type, 'Unknown')                                   AS device_type,
       COUNT(DISTINCT us.session_id)                                         AS sessions,
       COUNT(DISTINCT CASE WHEN fe.event_stage = 'VIEW'    THEN us.session_id END) AS viewed,
       COUNT(DISTINCT CASE WHEN fe.event_stage = 'CART'    THEN us.session_id END) AS carted,
       COUNT(DISTINCT CASE WHEN fe.event_stage = 'ORDER'   THEN us.session_id END) AS ordered,
       COUNT(DISTINCT CASE WHEN fe.event_stage = 'PAYMENT' THEN us.session_id END) AS paid,
       ROUND(100 * COUNT(DISTINCT CASE WHEN fe.event_stage = 'ORDER' THEN us.session_id END)
                 / NULLIF(COUNT(DISTINCT CASE WHEN fe.event_stage = 'CART' THEN us.session_id END), 0), 1)
           AS cart_to_order_pct,
       ROUND(100 * COUNT(DISTINCT CASE WHEN fe.event_stage = 'ORDER' THEN us.session_id END)
                 / NULLIF(COUNT(DISTINCT us.session_id), 0), 1)
           AS session_conversion_pct
FROM user_sessions us
LEFT JOIN funnel_events fe ON fe.session_id = us.session_id
GROUP BY COALESCE(us.device_type, 'Unknown');

SELECT * FROM vw_device_funnel;

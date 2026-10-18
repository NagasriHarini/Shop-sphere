# database/ - core DBMS assets

Run the scripts **in numeric order** in MySQL Workbench (File → Open SQL Script, then Execute All).

| Script | What it does | Safe to re-run |
|---|---|---|
| `00_create_app_user.sql` | Optional: creates the `shop_app` MySQL login for the website | yes |
| `01_schema.sql` | Creates `shopping_funnel` and the 12 core tables: PRIMARY KEY, FOREIGN KEY with ON DELETE CASCADE / SET NULL / RESTRICT, UNIQUE, CHECK, defaults | **no - drops the tables** |
| `02_seed_catalog.sql` | Loads 16 sellers and 2,905 products | no (run once after 01) |
| `03_funnel_events.sql` | `funnel_events` table, its CHECK and FKs, 4 indexes; backfills events from existing orders | yes |
| `04_triggers.sql` | 4 triggers: stock check (`SIGNAL 45000`), stock reduction, PAYMENT and REVIEW events | yes |
| `05_views_procedures.sql` | Funnel views + `sp_funnel_between`, `sp_customer_journey`, `sp_top_products` | yes |
| `06_constraints_cleanup.sql` | Fixes old data, then adds 15 CHECK and 2 UNIQUE constraints | yes |
| `07_device_view.sql` | `vw_device_funnel` | yes |
| `08_cumulative_funnel.sql` | Cumulative funnel versions of the views and of `sp_funnel_between` | yes |
| `09_delete_rules.sql` | Switches the foreign keys of an older database to the ON DELETE rules in 01 | yes |
| `queries/complex_queries.sql` | 24 documented queries: joins, subqueries, GROUP BY / HAVING, aggregates, CTEs, window functions, views, procedures | read-only |
| `tests/validation_tests.sql` | 16 PASS / FAIL tests of constraints, triggers and delete rules; rolls back all changes | yes |

Full build from a terminal:

```bash
for f in 01_schema 02_seed_catalog 03_funnel_events 04_triggers 05_views_procedures \
         06_constraints_cleanup 07_device_view 08_cumulative_funnel 09_delete_rules; do
  mysql -u root -p < database/$f.sql
done
```

The automated tests (`python manage.py test store`) build a separate `test_shopping_funnel` database from these same scripts.

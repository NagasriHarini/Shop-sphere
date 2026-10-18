"""Test runner that builds the test database from the project's SQL scripts.

The store models are unmanaged (managed = False): the tables, triggers, views
and procedures come from database/*.sql, not from Django migrations. So after
Django creates the empty test database (test_shopping_funnel) and its own
auth/session tables, this runner executes database/01 ... 09 on it.

    python manage.py test store
"""
from django.db import connections
from django.test.runner import DiscoverRunner

from store.sql_scripts import build_database


class SqlScriptsTestRunner(DiscoverRunner):
    def setup_databases(self, **kwargs):
        old_config = super().setup_databases(**kwargs)
        conn = connections['default']
        db_name = conn.settings_dict['NAME']          # e.g. test_shopping_funnel
        if self.verbosity:
            print(f'Building {db_name} from database/*.sql ...')
        with conn.cursor() as cur:
            build_database(cur, db_name)
        return old_config

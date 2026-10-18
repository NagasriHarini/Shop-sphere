"""Run the database/*.sql scripts from Python (used by the automated tests).

MySQL Workbench understands `DELIMITER $$`, but a database driver does not, so
this module splits a script into single statements itself: it follows
DELIMITER changes, skips comments and never splits inside a quoted string.
"""
from pathlib import Path

DATABASE_DIR = Path(__file__).resolve().parent.parent / 'database'

# Scripts that build a complete database, in order (00 creates a login and is skipped)
BUILD_SCRIPTS = [
    '01_schema.sql', '02_seed_catalog.sql', '03_funnel_events.sql', '04_triggers.sql',
    '05_views_procedures.sql', '06_constraints_cleanup.sql', '07_device_view.sql',
    '08_cumulative_funnel.sql', '09_delete_rules.sql',
]


def split_statements(text):
    """Yield the statements of an SQL script, one at a time."""
    delimiter = ';'
    buf = []
    i, n = 0, len(text)
    at_line_start = True
    while i < n:
        # DELIMITER command (must start a line)
        if at_line_start:
            j = i
            while j < n and text[j] in ' \t':
                j += 1
            if text[j:j + 10].upper() == 'DELIMITER ':
                end = text.find('\n', j)
                end = n if end == -1 else end
                delimiter = text[j + 10:end].strip()
                i = end + 1
                continue
        c = text[i]
        # comments
        if text.startswith('-- ', i) or text.startswith('--\n', i) or c == '#':
            end = text.find('\n', i)
            i = n if end == -1 else end
            continue
        if text.startswith('/*', i):
            end = text.find('*/', i + 2)
            i = n if end == -1 else end + 2
            continue
        # quoted strings / identifiers: copy as-is
        if c in ("'", '"', '`'):
            j = i + 1
            while j < n:
                if text[j] == '\\' and c != '`':
                    j += 2
                    continue
                if text[j] == c:
                    if j + 1 < n and text[j + 1] == c:   # doubled quote
                        j += 2
                        continue
                    break
                j += 1
            buf.append(text[i:j + 1])
            i = j + 1
            at_line_start = False
            continue
        # end of statement
        if text.startswith(delimiter, i):
            stmt = ''.join(buf).strip()
            if stmt:
                yield stmt
            buf = []
            i += len(delimiter)
            at_line_start = False
            continue
        buf.append(c)
        at_line_start = c == '\n'
        i += 1
    stmt = ''.join(buf).strip()
    if stmt:
        yield stmt


def run_script(cursor, path, db_name='shopping_funnel'):
    """Execute one script on an open cursor. db_name replaces 'shopping_funnel'
    so the same scripts can build the test database."""
    text = Path(path).read_text(encoding='utf-8')
    if db_name != 'shopping_funnel':
        text = text.replace('shopping_funnel', db_name)
    for stmt in split_statements(text):
        cursor.execute(stmt)
        while cursor.nextset():      # drain SELECT / CALL results
            pass


def build_database(cursor, db_name='shopping_funnel'):
    for name in BUILD_SCRIPTS:
        run_script(cursor, DATABASE_DIR / name, db_name)

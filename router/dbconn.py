"""Open the router's decision store from one --db string, so every script reads what shadow wrote, wherever it wrote it.
    reports/shadow.db | sqlite:reports/shadow.db   a local SQLite file (the trial store)
    mysql://user:pass@host/dbname                  the real router_decisions table (needs: pip install pymysql)
Read-only helpers: nothing here writes."""
import os, urllib.parse as U

def is_mysql(spec): return str(spec).startswith('mysql://')

def exists(spec):
    return True if is_mysql(spec) else os.path.exists(_path(spec))

def _path(spec): return spec[7:] if str(spec).startswith('sqlite:') else spec

def connect(spec):
    """Returns (conn, placeholder): '%s' for MySQL, '?' for SQLite."""
    if is_mysql(spec):
        import pymysql
        u = U.urlparse(spec)
        return pymysql.connect(host=u.hostname, port=u.port or 3306, user=U.unquote(u.username or ''),
                               password=U.unquote(u.password or ''), database=u.path.lstrip('/')), '%s'
    import sqlite3
    return sqlite3.connect(_path(spec)), '?'

def fetch(conn, ph, sql, params=()):
    """Run a SELECT written with %s placeholders on either driver."""
    cur = conn.cursor(); cur.execute(sql.replace('%s', ph), params); return cur.fetchall()
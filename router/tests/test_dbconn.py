import os, sqlite3, sys, types
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import dbconn

def _db(tmp_path):
    p = str(tmp_path / 's.db'); c = sqlite3.connect(p)
    c.execute("create table router_decisions (id integer, sku text, subject_uuid text, outcome text, primary_slug text, rule text, slugs text, status text)")
    c.execute("insert into router_decisions values (1,'A','u1','assigned','sofas','rule_x',null,'shadow')"); c.commit(); c.close(); return p

def test_sqlite_plain_path_and_prefix(tmp_path):
    p = _db(tmp_path)
    for spec in (p, 'sqlite:' + p):
        conn, ph = dbconn.connect(spec)
        assert ph == '?' and dbconn.exists(spec)
        assert dbconn.fetch(conn, ph, "select sku, primary_slug from router_decisions where status=%s", ('shadow',)) == [('A', 'sofas')]

def test_missing_sqlite_file_does_not_exist(tmp_path):
    assert not dbconn.exists(str(tmp_path / 'nope.db'))

def test_mysql_url_is_decoded_and_uses_percent_s(monkeypatch):
    seen = {}
    fake = types.SimpleNamespace(connect=lambda **k: seen.update(k) or 'CONN')
    monkeypatch.setitem(sys.modules, 'pymysql', fake)
    conn, ph = dbconn.connect('mysql://root:p%40ss@localhost:3307/onebuilddemo')
    assert (conn, ph) == ('CONN', '%s') and dbconn.is_mysql('mysql://x/y') and dbconn.exists('mysql://x/y')
    assert seen == dict(host='localhost', port=3307, user='root', password='p@ss', database='onebuilddemo')
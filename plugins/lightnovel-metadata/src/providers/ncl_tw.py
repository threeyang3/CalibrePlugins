"""Optional local NCL Taiwan new-book catalogue, imported from public CSV.

This is a *separate* offline source. Taiwan's open data consists of periodic
CSV snapshots of PRE-PUBLICATION notices, not a real-time per-book API. Avoid silently downloading large
monthly catalogues during a Calibre metadata lookup.
"""
from pathlib import Path
from contextlib import closing
import sqlite3
from ..models import Record, clean, isbn, norm

URL = 'https://data.gov.tw/dataset/6730'
SCHEMA_VERSION = 'lightnovel-ncl-1'


def query(index_path, code='', title='', limit=5):
    path = Path(str(index_path or '')).expanduser().resolve()
    if not path.is_file():
        raise ValueError('未找到 NCL 本地索引，请先导入官方 CSV。')
    if path.stat().st_size > 2 * 1024 ** 3:
        raise ValueError('NCL 索引超出 2 GiB 安全上限。')
    if not code and not clean(title):
        return []
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=1)) as db:
        db.execute('PRAGMA query_only=ON')
        version = db.execute('SELECT value FROM metadata WHERE name=?', ('version',)).fetchone()
        if version != (SCHEMA_VERSION,):
            raise ValueError('NCL 索引格式与插件不兼容，请重新导入。')
        if code:
            normalized = isbn(code)
            if not normalized:
                return []
            rows = db.execute('SELECT isbn, title, creator, publisher, date_text FROM books WHERE isbn=? LIMIT 2',
                              (normalized,)).fetchall()
        else:
            # Prefix-only search can use the indexed normalized-title column.
            value = norm(title)
            if len(value) < 3:
                return []
            rows = db.execute('SELECT isbn, title, creator, publisher, date_text FROM books '
                              'WHERE title_norm >= ? AND title_norm < ? ORDER BY title_norm LIMIT ?',
                              (value, value + chr(0x10ffff), max(1, min(int(limit), 10)))).fetchall()
    result = []
    for code, title, creator, publisher, date in rows:
        if isbn(code) != code:
            continue
        result.append(Record('ncl_tw', code, title, [creator] if creator else [], code,
                             publisher=publisher or '', pubdate='', date_text=date or '',
                             language='', tags=['台版'], url=URL))
    return result

#!/usr/bin/env python3
"""Build an offline, read-only ISBN index from NCL Taiwan official CSV files.

Example: python tools/import_ncl.py --output ~/Books/ncl.sqlite 202610.csv
Download the official monthly exports yourself from https://data.gov.tw/dataset/6730
This tool does not access any website, Calibre database or personal information.
"""
import argparse
from contextlib import closing
import csv
import os
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from models import isbn, norm, clean

VERSION = 'lightnovel-ncl-1'
HEADERS = {
    'isbn': ('ISBN', 'isbn', '國際標準書號', '国际标准书号', '書號', '书号'),
    'title': ('申請書名', '申请书名', '書名', '书名', '題名', '题名', '書名(正題名)', '書名(主題名)'),
    'creator': ('作者', '著者', '創作者', '責任者'),
    'publisher': ('出版單位', '出版機構', '出版社', '出版者', '出版单位'),
    'date_text': ('預訂出版日', '预订出版日', '預計出版年月', '預計出版日期', '出版年月', '出版日期', '出版年'),
}


def column_names(header):
    normalized = {clean(name).replace(' ', '').replace('　', '').lstrip('\\ufeff'): name for name in header}
    mapped = {}
    for field, variants in HEADERS.items():
        for variant in variants:
            original = normalized.get(variant.replace(' ', ''))
            if original is not None:
                mapped[field] = original
                break
    if 'isbn' not in mapped or 'title' not in mapped:
        raise ValueError('NCL CSV 缺少 ISBN 或书名列，请检查是否下载正确的数据集。')
    return mapped


def read_csv(path):
    """Stream data twice, validating encoding before emitting a single row.

    A malformed late byte in a large monthly export must NOT leave partial
    rows from one decoding attempt mixed with a fallback decoding attempt.
    """
    last = None
    for encoding in ('utf-8-sig', 'cp950', 'big5'):
        try:
            with path.open('r', encoding=encoding, newline='') as source:
                while source.read(1024 * 1024):
                    pass
        except UnicodeError as err:
            last = err
            continue
        with path.open('r', encoding=encoding, newline='') as source:
            reader = csv.DictReader(source)
            columns = column_names(reader.fieldnames or [])
            for item in reader:
                value = {key: clean(item.get(column)) for key, column in columns.items()}
                code = isbn(value.get('isbn'))
                title = value.get('title', '')
                if code and title:
                    yield (code, title, norm(title), value.get('creator', ''),
                           value.get('publisher', ''), value.get('date_text', ''))
        return
    raise ValueError('CSV 编码无法识别：%s' % path) from last


def build(paths, output, replace=False):
    output = Path(output).expanduser().resolve()
    if output.exists() and not replace:
        raise ValueError('索引已存在；要替换请添加 --replace，或更换输出路径。')
    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = output.with_name(output.name + '.building')
    if tmp.exists():
        raise ValueError('已存在未完成的索引构建文件，请检查并手动清理。')
    count = 0
    try:
        with closing(sqlite3.connect(str(tmp))) as db:
            db.execute('CREATE TABLE metadata (name TEXT PRIMARY KEY, value TEXT NOT NULL)')
            db.execute('CREATE TABLE books (isbn TEXT PRIMARY KEY, title TEXT NOT NULL, '
                       'title_norm TEXT NOT NULL, creator TEXT, publisher TEXT, date_text TEXT)')
            db.execute('INSERT INTO metadata VALUES (?,?)', ('version', VERSION))
            for raw in paths:
                path = Path(raw).expanduser()
                if not path.is_file() or path.suffix.lower() != '.csv':
                    raise ValueError('仅支持本地 NCL CSV：%s' % path)
                for row in read_csv(path):
                    db.execute('INSERT OR REPLACE INTO books VALUES (?,?,?,?,?,?)', row)
                    count += 1
            db.execute('CREATE INDEX idx_books_title_norm ON books(title_norm)')
            db.commit()
        os.replace(str(tmp), str(output))
        return count
    except BaseException:
        if tmp.exists():
            tmp.unlink()
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('csv', nargs='+', type=Path, help='NCL official monthly CSV')
    parser.add_argument('--output', required=True, type=Path, help='SQLite index path')
    parser.add_argument('--replace', action='store_true')
    args = parser.parse_args()
    print('已导入 %s 条有效书目（含重复 ISBN），索引：%s' %
          (build(args.csv, args.output, args.replace), args.output))

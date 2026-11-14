"""Exercise WebNovel column writes and Book Details in a disposable Calibre library.

Install both ZIPs into an isolated CALIBRE_CONFIG_DIRECTORY, then run:
    calibre-debug -e tests/calibre_library_smoke.py

Uses the installed plugin and Calibre's real database and renderer with local fixtures.
"""

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from io import BytesIO
import json
import os
from pathlib import Path
from queue import Queue
from tempfile import TemporaryDirectory
from threading import Event
from types import SimpleNamespace


def platform_link(metadata, mi_to_html, html):
    details, _ = mi_to_html(metadata, [("#webnovel_platform", True)], for_qt=True)
    row = html.fromstring(details).xpath('//tr[@id="_webnovel_platform"]')
    assert len(row) == 1 and "连载平台" in row[0].text_content(), details
    links = row[0].xpath('.//a[text()="起点中文网"]/@href')
    assert len(links) == 1, details
    scheme, separator, payload = links[0].partition(":")
    assert scheme == "action" and separator, links
    action = json.loads(bytes.fromhex(payload))
    assert action["type"] == "cc_url", action
    return action["url"]


def check_fetch_matching(fetch_books, book, alternate_ref):
    alternate = replace(book, ref=alternate_ref)
    wrong_author = replace(book, authors=["同名作品的另一位作者"])
    queried = []

    def fixture_identify(log, abort, title, authors, identifiers):
        queried.append(identifiers)
        if identifiers:
            return [book, alternate]
        if len(queried) == 2:
            return [book, alternate]
        return [book, wrong_author]

    fixture_source = SimpleNamespace(identify_books=fixture_identify)
    targets = [
        (1, book.title, ["未知"], {"qidian": book.ref.book_id}),
        (2, book.title, book.authors, {}),
        (3, book.title, ["未知"], {}),
        (4, book.title, book.authors, {}),
    ]
    matches, skipped = fetch_books(fixture_source, targets, abort=Event(), log=None, notifications=Queue())
    assert matches == [(1, book.title, book), (4, book.title, book)], matches
    assert len(skipped) == 2 and "多个作品" in skipped[0][1] and "填写作者" in skipped[1][1], skipped
    assert queried == [{"qidian": book.ref.book_id}, {}, {}], queried


def main():
    if not os.environ.get("CALIBRE_CONFIG_DIRECTORY"):
        raise SystemExit("Set CALIBRE_CONFIG_DIRECTORY to an isolated test configuration first.")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from calibre.constants import __version__
    from calibre.customize.ui import metadata_plugins
    from calibre.db.backend import DB
    from calibre.db.cache import Cache
    from calibre.ebooks.metadata.book.base import Metadata
    from calibre.ebooks.metadata.book.render import mi_to_html
    from calibre_plugins.webnovel_library.action import apply_book, fetch_books, strip_legacy_details
    from calibre_plugins.webnovel_library.storage import compatible_columns, ensure_columns
    from calibre_plugins.webnovel_metadata.models import BookMetadata, BookRef
    from calibre_plugins.webnovel_metadata.providers import parse_detail
    from lxml import html
    from PIL import Image

    source = next(p for p in metadata_plugins(["identify"]) if p.name == "WebNovel Metadata")
    fixtures = Path(__file__).resolve().parent / "fixtures"
    ref = BookRef("qidian", "1012345678")
    book = parse_detail((fixtures / "qidian_mobile.html").read_text(encoding="utf-8"), ref)
    desktop = parse_detail((fixtures / "qidian_desktop.html").read_text(encoding="utf-8"), ref)
    book = replace(book, latest_chapter=desktop.latest_chapter)
    check_fetch_matching(fetch_books, book, BookRef("qimao", "123456"))
    preserve_date = datetime(2014, 7, 1, 12, tzinfo=timezone.utc)
    original_cover = BytesIO()
    Image.new("RGB", (30, 40), "navy").save(original_cover, "JPEG")

    with TemporaryDirectory(prefix="calibre-webnovel-library-") as path:
        db = Cache(DB(path))
        db.init()
        try:
            db.create_custom_column("source", "来源", "text", False)
            db.create_custom_column("progress", "进度", "enumeration", False,
                                    display={"enum_values": ["未读", "在读", "已读"]})
            missing, invalid = compatible_columns(db)
            assert len(missing) == 6 and not invalid, (missing, invalid)
            ensure_columns(db)
        finally:
            db.close()

        # Calibre rebuilds the cache on reopening after custom columns are added.
        db = Cache(DB(path))
        db.init()
        try:
            assert not any(compatible_columns(db)), compatible_columns(db)
            before_columns = db.field_metadata.custom_field_metadata()
            ensure_columns(db)
            assert db.field_metadata.custom_field_metadata() == before_columns

            metadata = Metadata(book.title, book.authors)
            metadata.pubdate = preserve_date
            metadata.rating = 8
            metadata.tags = ["网文"]
            metadata.set_identifier("file_catalog", "fixture001")
            metadata.comments = (
                '<div> <p>旧简介。</p> <p><strong>个人笔记：</strong>这是我自己的文字。</p> '
                '<p>来源：<a href="{}"><span style="color: #6cb4ee">起点中文网</span></a> · 作品 ID：{}</p> '
                '<p>连载状态：连载中<br>字数：50万字<br>首发日期：2020-04-01<br>'
                '最近更新：2026-11-09 10:20:30<br>最新章节：旧章节</p></div>'
            ).format(ref.url, ref.book_id)
            assert strip_legacy_details(metadata.comments, ref, lambda key: key != '#webnovel_word_count') == metadata.comments
            book_id = db.create_book_entry(metadata, cover=original_cover.getvalue())
            db.set_field("#source", {book_id: "用户提供的电子书文件"})
            db.set_field("#progress", {book_id: "已读"})
            cover_before = db.cover(book_id)
            assert cover_before

            apply_book(db, book_id, source, book)
            after = db.get_metadata(book_id)
            assert after.pubdate == preserve_date, after.pubdate
            assert after.rating == 8
            assert set(after.tags) == {"网文", "科幻", "星际文明"}, after.tags
            assert after.get_identifiers() == {"file_catalog": "fixture001", "qidian": ref.book_id}
            assert after.get("#source") == "用户提供的电子书文件"
            assert after.get("#progress") == "已读"
            assert db.cover(book_id) == cover_before

            assert after.get("#webnovel_first_published").date().isoformat() == "2020-04-01"
            word_count = after.get("#webnovel_word_count")
            assert type(word_count) is int and word_count == 512000, word_count
            assert after.get("#webnovel_status") == "已完结"
            assert after.get("#webnovel_latest_chapter") == "第一百章 归航"
            updated = after.get("#webnovel_updated")
            assert updated.astimezone(timezone(timedelta(hours=8))) == datetime(
                2026, 11, 10, 10, 20, 30, tzinfo=timezone(timedelta(hours=8))
            ), updated
            assert platform_link(after, mi_to_html, html) == "https://m.qidian.com/book/1012345678/"

            synopsis = html.fromstring(after.comments)
            assert synopsis.xpath("//strong[contains(text(), '个人笔记')]")
            assert "这是我自己的文字。" in synopsis.text_content()
            assert "旧简介。" in synopsis.text_content()
            assert not synopsis.xpath('//a[@href=$url]', url=ref.url)
            assert "旧章节" not in synopsis.text_content()
            assert "作品 ID" not in synopsis.text_content()

            apply_book(db, book_id, source, book)
            assert db.field_for("comments", book_id) == after.comments

            missing_fields = BookMetadata(ref=ref, title=book.title, authors=book.authors)
            apply_book(db, book_id, source, missing_fields)
            for key in ("comments", "#webnovel_first_published", "#webnovel_word_count",
                        "#webnovel_status", "#webnovel_updated", "#webnovel_latest_chapter"):
                assert db.field_for(key, book_id) == after.get(key), key
            assert db.cover(book_id) == cover_before

            second_ref = BookRef("qidian", "2048120")
            second = Metadata("第二本书", ["另一位作者"])
            second_id = db.create_book_entry(second)
            second_book = BookMetadata(second_ref, second.title, second.authors, "来自官网的简介。")
            apply_book(db, second_id, source, second_book)
            second_mi = db.get_metadata(second_id)
            assert second_mi.get("#webnovel_word_count") is None
            assert html.fromstring(second_mi.comments).text_content() == "来自官网的简介。"
            assert platform_link(second_mi, mi_to_html, html) == "https://m.qidian.com/book/2048120/"
        finally:
            db.close()

    print("PASS candidate matching, structured fields, per-work links, migration, and preserved book data in Calibre",
          __version__)


if __name__ == "__main__":
    main()

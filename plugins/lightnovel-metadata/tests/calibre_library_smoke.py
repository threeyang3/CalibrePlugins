"""Check the installed LightNovel plugins against a disposable Calibre library.

Use an isolated CALIBRE_CONFIG_DIRECTORY and install both ZIPs before running
calibre-debug -e tests/calibre_library_smoke.py. No network is used.
"""

from datetime import datetime, timezone
from io import BytesIO
import os
from tempfile import TemporaryDirectory
from zipfile import ZipFile


def check(condition, description):
    if not condition:
        raise AssertionError(description)


def image_bytes(color):
    from PIL import Image

    buffer = BytesIO()
    Image.new('RGB', (30, 40), color).save(buffer, 'JPEG')
    return buffer.getvalue()


def epub_bytes():
    buffer = BytesIO()
    with ZipFile(buffer, 'w') as archive:
        archive.writestr('mimetype', 'application/epub+zip')
        archive.writestr('META-INF/container.xml', """
            <container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
              <rootfiles><rootfile full-path="content.opf" media-type="application/oebps-package+xml"/></rootfiles>
            </container>""")
        archive.writestr('content.opf', """
            <package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="book-id">
              <metadata xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:opf="http://www.idpf.org/2007/opf">
                <dc:identifier id="book-id">urn:uuid:5ecce680-12f3-46bf-91fe-d56d38a3bbca</dc:identifier>
                <dc:title>Fixture</dc:title><dc:language>zh</dc:language>
                <dc:contributor opf:role="bkp">个人 EPUB 制作者</dc:contributor>
              </metadata>
              <manifest><item id="chapter" href="chapter.xhtml" media-type="application/xhtml+xml"/></manifest>
              <spine><itemref idref="chapter"/></spine>
            </package>""")
        archive.writestr('chapter.xhtml', '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Fixture</title></head>'
                         '<body><p>Fixture chapter.</p></body></html>')
    return buffer.getvalue()


def main():
    if not os.environ.get('CALIBRE_CONFIG_DIRECTORY'):
        raise SystemExit('Set CALIBRE_CONFIG_DIRECTORY to an isolated test configuration.')

    from calibre.constants import __version__
    from calibre.customize.ui import metadata_plugins
    from calibre.db.backend import DB
    from calibre.db.cache import Cache
    from calibre.ebooks.metadata.book.base import Metadata
    from calibre_plugins.lightnovel_library.storage import apply_book, compatible_columns, ensure_columns
    from calibre_plugins.lightnovel_metadata.models import Record, combine

    source = next(plugin for plugin in metadata_plugins(['identify']) if plugin.name == 'LightNovel Metadata')
    local_isbn13 = '9780306406157'
    local_isbn10 = '0306406152'
    local_labels = {
        '#source': '自购电子版',
        '#progress': '已读',
        '#version': ('民间', '日版'),
        '#comment': '私人批注',
        '#translator': '民间翻译组',
        '#epub_maker': '电子书制作者',
    }

    with TemporaryDirectory(prefix='calibre-lightnovel-maker-') as path:
        db = Cache(DB(path))
        db.init()
        try:
            check('#epub_maker' in ensure_columns(db), 'The personal maker field is created when absent')
        finally:
            db.close()

    with TemporaryDirectory(prefix='calibre-lightnovel-library-') as path:
        db = Cache(DB(path))
        db.init()
        try:
            for key, name in (
                ('source', '来源'), ('comment', '评论'), ('translator', '译者'), ('epub_maker', '制作者')
            ):
                db.create_custom_column(key, name, 'text', False)
            db.create_custom_column('progress', '进度', 'enumeration', False,
                                    display={'enum_values': ['未读', '已读']})
            db.create_custom_column('version', '版本', 'text', True)
        finally:
            db.close()

        # Calibre reloads its field registry after reopening.
        db = Cache(DB(path))
        db.init()
        try:
            missing, invalid = compatible_columns(db)
            check(len(missing) == 4 and not invalid, 'The four public book fields can be created')
            check(len(ensure_columns(db)) == 4, 'An existing personal maker field is reused')
        finally:
            db.close()

        db = Cache(DB(path))
        db.init()
        try:
            check(not any(compatible_columns(db)), 'The created catalogue columns are enabled after reopen')
            check(ensure_columns(db) == [], 'Repeated setup creates no columns')
            local = Metadata('我的书名 第3卷', ['著者', '本地译者', '本地插画师'])
            local.author_sort = '保留的作者排序'
            local.title_sort = '保留的书名排序'
            local.rating = 8
            local.series, local.series_index = '个人丛书', 7.5
            local.comments = '<p>本地介绍和个人备注。</p>'
            local.tags = ['个人标签']
            local.publisher = '旧出版社'
            local.pubdate = datetime(2023, 9, 2, 12, tzinfo=timezone.utc)
            local.languages = ['zho']
            local.set_identifiers({'isbn': local_isbn10, 'file_catalog': 'file-original', 'bangumi': '1234'})
            book_id = db.create_book_entry(local, cover=image_bytes('navy'))
            fixture_epub = epub_bytes()
            check(db.add_format(book_id, 'EPUB', BytesIO(fixture_epub), run_hooks=False),
                  'Fixture EPUB added to the disposable library')
            for field, value in local_labels.items():
                db.set_field(field, {book_id: value})
            db.set_field('#lightnovel_illustrator', {book_id: '手填书目插画师'})
            original_cover = db.cover(book_id)
            original_path = db.field_for('path', book_id)
            original_ids = db.field_for('identifiers', book_id)
            before = db.get_metadata(book_id)

            record = Record('bangumi', '1234', '公共書名 第3卷', ['公开著者'], local_isbn13,
                            original_title='作品原題', publisher='公开出版社', pubdate='2024-02-06',
                            language='jpn', tags=['奇幻'], description='公开简介。',
                            series='公开丛书', series_index=3, translators=['书目译者一', '书目译者二'],
                            illustrators=['书目插画师'], identifiers={'books_tw': '0011234567'})
            check(not apply_book(db, book_id, source, record, cover=image_bytes('red')),
                  'Do not replace the existing cover')
            after = db.get_metadata(book_id)
            check(after.title == local.title and after.authors == local.authors,
                  'Keep the local title and contributor list')
            check((after.title_sort, after.author_sort, after.rating) == (local.title_sort, local.author_sort, 8),
                  'Keep local sort fields and rating')
            check(after.comments == local.comments, 'Keep private comments')
            check((after.languages, after.series, after.series_index) == (['zho'], '个人丛书', 7.5),
                  'Keep existing language, series and volume')
            check((after.publisher, after.pubdate) == (local.publisher, local.pubdate),
                  'Keep existing publisher and publication date')
            check(after.get_identifiers() == {**original_ids, 'books_tw': '0011234567'},
                  'Add catalogue ID without replacing ISBN-10 or existing IDs')
            check(set(after.tags) == {'个人标签', '奇幻'}, 'Keep user tag and add public genre tag')
            for field in local_labels:
                check(after.get(field) == before.get(field), f'Existing field {field} keeps its value')
            check(after.get('#lightnovel_original_title') == '作品原題', 'Fill original title column')
            check(after.get('#lightnovel_translator') == '书目译者一、书目译者二',
                  'Fill the separate catalogue translator column')
            check(after.get('#lightnovel_illustrator') == '手填书目插画师',
                  'Keep a manually entered catalogue illustrator')
            check(after.get('#lightnovel_date_text') is None,
                  'Do not repeat a full date in the original-date column')
            check(db.field_for('path', book_id) == original_path, 'Keep the local format path')
            check(db.cover(book_id) == original_cover, 'Existing cover bytes are identical')
            check(db.format(book_id, 'EPUB') == fixture_epub,
                  'EPUB and embedded book producer credit are identical')

            conflict = Record('bangumi', '4321', '同 ISBN 的冲突条目', [], local_isbn13, publisher='错误出版社')
            try:
                apply_book(db, book_id, source, conflict)
            except ValueError as error:
                check('标识符' in str(error), 'Explain the conflicting source ID')
            else:
                raise AssertionError('Conflicting source identifier accepted')
            check(db.field_for('publisher', book_id) == local.publisher,
                  'Do not modify the existing local publisher')

            bare_record = Record('bangumi', '1234', '缺少可选字段', [], local_isbn13)
            check(not apply_book(db, book_id, source, bare_record), 'No cover update without cover data')
            check(db.field_for('#lightnovel_translator', book_id) == '书目译者一、书目译者二',
                  'A later incomplete source leaves existing credits intact')
            db.set_field('#lightnovel_translator', {book_id: '手填书目译者'})
            apply_book(db, book_id, source, record, cover=image_bytes('red'))
            check(db.field_for('#lightnovel_translator', book_id) == '手填书目译者',
                  'An incoming translator cannot replace a manually entered catalogue credit')
            check(db.field_for('publisher', book_id) == local.publisher,
                  'Do not modify the existing local publisher')

            future_isbn = '9784041234563'
            future = Metadata('待发行示例书', [])
            future.set_identifier('isbn', future_isbn)
            original_pubdate = datetime(2022, 3, 1, 12, tzinfo=timezone.utc)
            future.pubdate = original_pubdate
            future_id = db.create_book_entry(future)
            catalogue = Record('ncl_tw', future_isbn, '待发行示例书', ['公开著者'], future_isbn, date_text='2027-03')
            foreign = Record('books_tw', '0019876543', '待发行示例书 (1)', ['公开著者'], future_isbn,
                             publisher='公开书目出版社', description='只在空白简介里填入。', language='jpn',
                             illustrators=['书目插画师'])
            announcement = combine([catalogue, foreign])[0]
            check(announcement.source != 'ncl_tw' and announcement.field_sources['date_text'] == 'ncl_tw',
                  'Use date-specific NCL provenance after combining')
            check(apply_book(db, future_id, source, announcement, cover=image_bytes('red')),
                  'Fill a missing cover')
            second_cover = db.cover(future_id)
            second = db.get_metadata(future_id)
            check(second.authors == ['公开著者'], 'Fill unknown authors')
            check(second.title == future.title, 'Keep the local title for a book with otherwise missing fields')
            check(second.languages == ['jpn'], 'Fill a missing language')
            check(second.publisher == '公开书目出版社', 'Fill a missing publisher')
            check(second.pubdate == original_pubdate, 'Never use a scheduled NCL date as publication date')
            check((second.series, second.series_index) == ('待发行示例书', 1.0),
                  'Fill missing series and volume together')
            check(second.get('#lightnovel_illustrator') == '书目插画师', 'Fill empty catalogue illustrator')
            check(second.get('#lightnovel_date_text') == '预订出版：2027-03',
                  'Label the NCL date as a planned publication')
            check('只在空白简介里填入。' in second.comments, 'Fill missing synopsis from the source')
            check(second_cover and not apply_book(db, future_id, source, announcement, cover=image_bytes('blue')),
                  'A repeated update preserves the now-present cover')
            check(db.cover(future_id) == second_cover, 'New cover bytes stay identical on repeat')

            undated = Metadata('空出版日期', ['作者'])
            undated.set_identifier('isbn', local_isbn13)
            undated_id = db.create_book_entry(undated)
            apply_book(db, undated_id, source, record)
            check(db.get_metadata(undated_id).pubdate.date().isoformat() == '2024-02-06',
                  'Replace the undefined date with a confirmed full publication date')
        finally:
            db.close()

    print('PASS verified editions, public credit columns, protected personal data and EPUB, cover fill-only in Calibre',
          __version__)


if __name__ == '__main__':
    main()

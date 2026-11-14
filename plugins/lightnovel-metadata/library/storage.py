"""Calibre columns and writes for verified light novel editions."""

from dataclasses import dataclass

from calibre.ebooks.metadata.book.base import Metadata
from calibre.utils.date import is_date_undefined


@dataclass(frozen=True)
class Column:
    label: str
    heading: str
    description: str

    @property
    def key(self):
        return '#' + self.label


COLUMN_SPECS = (
    Column('lightnovel_original_title', '作品原名', '公开书目提供的原作名称。'),
    Column('lightnovel_translator', '译者（书目）', '公开书目列出的译者；现有译者、作者和制作者署名独立保留。'),
    Column('lightnovel_illustrator', '插画师（书目）', '公开书目列出的插画署名。'),
    Column('lightnovel_date_text', '出版日期（原文）', '公开书目的部分日期或预订出版日期。'),
)
EPUB_MAKER = Column('epub_maker', 'EPUB 制作者', '电子书文件的制作者，由你填写。')


def compatible_columns(db):
    """Return the missing and incompatible columns, in display order."""
    fields = db.field_metadata.custom_field_metadata()
    names = {field['name'] for field in fields.values()}
    missing, incompatible = [], []
    for spec in COLUMN_SPECS:
        field = fields.get(spec.key)
        if field is None:
            (incompatible if spec.heading in names else missing).append(spec)
        elif field['datatype'] != 'text' or field['is_multiple']:
            incompatible.append(spec)
    return missing, incompatible


def ensure_columns(db):
    """Create the book metadata columns and an optional personal credit column."""
    missing, incompatible = compatible_columns(db)
    if incompatible:
        raise ValueError('以下栏目与轻小说书目设置冲突：' + '、'.join(spec.heading for spec in incompatible))
    fields = db.field_metadata.custom_field_metadata()
    names = {''.join(field['name'].split()).casefold() for field in fields.values()}
    if EPUB_MAKER.key not in fields and names.isdisjoint({'epub制作者', '电子书制作者', '制作者'}):
        missing.append(EPUB_MAKER)
    for spec in missing:
        db.create_custom_column(spec.label, spec.heading, 'text', False, display={'description': spec.description})
    return [spec.key for spec in missing]


def add_lightnovel_fields(db, book, metadata, current):
    missing, incompatible = compatible_columns(db)
    if missing or incompatible:
        raise ValueError('请先设置轻小说书目栏目：' + '、'.join(spec.heading for spec in (*missing, *incompatible)))

    date_text = book.date_text.strip()
    if date_text and book.field_sources.get('date_text', book.source) == 'ncl_tw':
        date_text = '预订出版：' + date_text
    elif book.pubdate:
        date_text = ''
    values = {
        '#lightnovel_original_title': book.original_title,
        '#lightnovel_translator': '、'.join(book.translators),
        '#lightnovel_illustrator': '、'.join(book.illustrators),
        '#lightnovel_date_text': date_text,
    }
    for key, value in values.items():
        if value and not (current.get(key) or '').strip():
            metadata.set_user_metadata(key, db.field_metadata[key])
            metadata.set(key, value)


def apply_book(db, book_id, source, book, *, cover=None):
    """Save confirmed edition metadata. Return whether a missing cover was filled."""
    from calibre_plugins.lightnovel_metadata import synopsis_html
    from calibre_plugins.lightnovel_metadata.models import SOURCES, isbn

    with db.write_lock:
        current = db.get_metadata(book_id, get_user_categories=False)
        current_ids = current.get_identifiers()
        if book.work_level or not book.isbn or isbn(current_ids.get('isbn')) != book.isbn:
            raise ValueError('书库条目与公开书目没有相同的有效版本 ISBN。')
        incoming = source.metadata_for_book(book)
        incoming_ids = incoming.get_identifiers()
        if any(
            current_ids.get(key) and current_ids[key] != incoming_ids[key]
            for key in incoming_ids.keys() & set(SOURCES)
        ):
            raise ValueError('书库已有的数据源条目标识符与公开书目不一致。')

        fill_authors = current.is_null('authors') and not incoming.is_null('authors')
        metadata = Metadata(current.title, incoming.authors if fill_authors else current.authors)
        if fill_authors and not current.is_null('author_sort'):
            metadata.author_sort = current.author_sort
        metadata.set_identifiers({key: value for key, value in incoming_ids.items() if key not in current_ids})
        if current.is_null('publisher'):
            metadata.publisher = incoming.publisher
        if is_date_undefined(current.pubdate) and book.field_sources.get('pubdate', book.source) != 'ncl_tw':
            metadata.pubdate = incoming.pubdate
        if not current.languages:
            metadata.languages = incoming.languages
        if not current.series and incoming.series and incoming.series_index is not None:
            metadata.series = incoming.series
            metadata.series_index = incoming.series_index
        if not (current.comments or '').strip():
            metadata.comments = synopsis_html(book)
        metadata.tags = list(dict.fromkeys([*(current.tags or []), *(incoming.tags or [])]))
        add_lightnovel_fields(db, book, metadata, current)

        fill_cover = bool(cover and not db.field_for('cover', book_id) and not db.cover(book_id))
        if fill_cover:
            metadata.cover_data = (None, cover)
        db.set_metadata(book_id, metadata, set_title=False, set_authors=fill_authors)
        return fill_cover

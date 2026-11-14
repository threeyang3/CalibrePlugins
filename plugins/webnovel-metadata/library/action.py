"""Fetch official website data and apply it to selected books in Calibre."""

import re
from functools import partial
from html import escape

from lxml import etree, html

from calibre.customize.ui import metadata_plugins
from calibre.gui2 import error_dialog, info_dialog
from calibre.gui2.actions import InterfaceAction
from calibre.gui2.threaded_jobs import ThreadedJob

from .storage import add_webnovel_fields, compatible_columns, ensure_columns


SOURCE_NAME = 'WebNovel Metadata'
ACTION_NAME = 'WebNovel Library'
LEGACY_COLUMNS = {
    '连载状态': '#webnovel_status', '字数': '#webnovel_word_count',
    '首发日期': '#webnovel_first_published', '最近更新': '#webnovel_updated',
    '最新章节': '#webnovel_latest_chapter',
}
LEGACY_DETAIL = re.compile(r'(' + '|'.join(LEGACY_COLUMNS) + r')：\s*\S')


def strip_legacy_details(comments, ref, has_value):
    """Remove the 0.1.0 generated paragraphs for this work, including Qt's HTML variant."""
    if not comments or '作品 ID' not in comments:
        return comments
    from calibre_plugins.webnovel_metadata.providers import PROVIDERS, parse_book_url

    try:
        document = html.fragment_fromstring(comments, create_parent=True)
    except (etree.ParserError, ValueError):
        return comments
    byline = '来源：{} · 作品 ID：{}'.format(PROVIDERS[ref.provider], ref.book_id)
    changed = False
    for paragraph in document.iter('p'):
        links = paragraph.xpath('.//a[@href]')
        if len(links) != 1 or parse_book_url(links[0].get('href')) != ref:
            continue
        if ' '.join(paragraph.text_content().split()) != byline:
            continue
        details = paragraph.getnext()
        if details is not None and details.tag == 'p':
            for br in details.iter('br'):
                br.tail = '\n' + (br.tail or '')
            fields = [LEGACY_DETAIL.match(line.strip()) for line in details.text_content().strip().splitlines()]
            generated = fields and all(fields)
            if generated and all(has_value(LEGACY_COLUMNS[field[1]]) for field in fields):
                details.drop_tree()
            else:
                for br in details.iter('br'):
                    br.tail = br.tail[1:] or None
                if generated:
                    continue
        paragraph.drop_tree()
        changed = True
    if not changed:
        return comments
    if not document.text_content().strip() and not document.xpath('.//img|.//hr'):
        return ''
    return escape(document.text or '') + ''.join(html.tostring(child, encoding='unicode') for child in document)


def apply_book(db, book_id, source, book):
    """Save verified metadata and its typed fields together."""
    current = db.get_metadata(book_id, get_user_categories=False)
    metadata = source.metadata_for_book(book)
    metadata.cover = None
    metadata.cover_data = (None, None)
    metadata.pubdate = None
    metadata.languages = []
    add_webnovel_fields(db, book, metadata)
    if current.comments:
        def has_value(key):
            return metadata.get(key) is not None or current.get(key) is not None

        cleaned = strip_legacy_details(current.comments, book.ref, has_value)
        if cleaned != current.comments:
            metadata.comments = cleaned.strip() or metadata.comments or '<p></p>'
        else:
            metadata.comments = None
    metadata.tags = list(dict.fromkeys([*(current.tags or []), *(metadata.tags or [])]))
    return db.set_metadata(book_id, metadata, set_title=False, set_authors=False)


def fetch_books(source, targets, *, abort, log, notifications):
    """Resolve explicit work IDs, or accept a unique exact title and known author match."""
    from calibre_plugins.webnovel_metadata.engine import clean_query, explicit_refs, known_authors, normalize

    matches, skipped = [], []
    for index, (book_id, title, authors, identifiers) in enumerate(targets):
        if abort.is_set():
            break
        notifications.put((index / len(targets), title))
        try:
            refs, direct = explicit_refs(identifiers, title)
        except ValueError as error:
            skipped.append((title, str(error)))
            continue
        if len(refs) > 1:
            skipped.append((title, '有多个官方作品标识符，请核对要采用的连载平台。'))
            continue
        author_keys = {normalize(author) for author in known_authors(authors)}
        if not direct and not author_keys:
            skipped.append((title, '请填写作者或官方作品标识符。'))
            continue
        results = source.identify_books(log, abort, title=title, authors=authors, identifiers=identifiers)
        if direct:
            candidates = {book.ref: book for book in results if book.ref in refs}
        else:
            title_key = normalize(clean_query(title))
            candidates = {
                book.ref: book for book in results
                if normalize(book.title) == title_key
                and author_keys.intersection(normalize(author) for author in book.authors)
            }
        if len(candidates) == 1:
            matches.append((book_id, title, next(iter(candidates.values()))))
        elif candidates:
            skipped.append((title, '匹配到多个作品，请填写要采用的官方作品标识符。'))
        else:
            skipped.append((title, '未获得可确认的作品，请检查书名、作者或官方作品标识符。'))
    return matches, skipped


class WebNovelLibraryAction(InterfaceAction):
    name = ACTION_NAME
    action_spec = ('网文元数据', 'download-metadata.png', '获取选中书籍的连载平台、首发日期、字数和连载信息', None)
    action_add_menu = True
    action_menu_clone_qaction = '更新选中书籍的网文元数据'
    dont_add_to = frozenset({'toolbar-device', 'context-menu-device', 'menubar-device'})
    action_type = 'current'

    def genesis(self):
        self.job = None
        self.qaction.triggered.connect(self.fetch_selected)
        self.create_menu_action(self.qaction.menu(), 'webnovel-library-create-columns', '建立网文栏目',
                                triggered=self.create_columns)

    def location_selected(self, location):
        enabled = location == 'library'
        self.qaction.setEnabled(enabled)
        if self.menuless_qaction is not None:
            self.menuless_qaction.setEnabled(enabled)

    def create_columns(self):
        if self.gui.must_restart_before_config:
            return info_dialog(self.gui, '请重启 Calibre', '有栏目更改待生效。请重启 Calibre 后继续。', show=True)
        db = self.gui.current_db.new_api
        try:
            created = ensure_columns(db)
        except (ValueError, OSError) as error:
            return error_dialog(self.gui, '未能建立网文栏目', str(error), show=True)
        if created:
            self.gui.must_restart_before_config = True
            return info_dialog(self.gui, '已建立网文栏目', '已在当前书库创建栏目，重启 Calibre 后可以填写。', show=True)
        info_dialog(self.gui, '网文栏目已就绪', '当前书库已包含所需栏目。', show=True)

    def fetch_selected(self):
        if self.job is not None and self.job.duration is None:
            self.gui.status_bar.show_message('正在获取网文元数据', 3000)
            return
        source = next((plugin for plugin in metadata_plugins(['identify']) if plugin.name == SOURCE_NAME), None)
        if source is None or source.version < (0, 2, 0):
            return error_dialog(self.gui, '网文元数据来源未启用',
                                '请安装并启用 WebNovel Metadata 0.2.0 或更新版本。', show=True)
        db = self.gui.current_db.new_api
        missing, incompatible = compatible_columns(db)
        if incompatible:
            headings = '、'.join(spec.heading for spec in incompatible)
            return error_dialog(self.gui, '网文栏目设置冲突', '请在首选项中核对这些栏目：' + headings, show=True)
        if missing:
            return info_dialog(self.gui, '请先建立网文栏目',
                               '选择「网文元数据 → 建立网文栏目」，重启 Calibre 后再次执行。', show=True)
        targets = []
        for book_id in self.gui.library_view.get_selected_ids():
            mi = db.get_metadata(book_id, get_user_categories=False)
            targets.append((book_id, mi.title, mi.authors, mi.get_identifiers()))
        if not targets:
            return info_dialog(self.gui, '请选择书籍', '请先在书库中选中要更新的书籍。', show=True)
        callback = self.Dispatcher(partial(self.finish_fetch, db, source, targets))
        self.job = ThreadedJob('webnovel-library-fetch', '获取网文元数据', fetch_books, (source, targets), {}, callback)
        self.gui.job_manager.run_threaded_job(self.job)
        self.gui.status_bar.show_message('正在获取网文元数据', 3000)

    def finish_fetch(self, db, source, targets, job):
        if self.job is not job:
            return
        self.job = None
        if job.killed or job.abort.is_set():
            return
        if job.failed:
            return self.gui.job_exception(job, dialog_title='未能获取网文元数据')
        if self.gui.current_db.new_api is not db:
            return info_dialog(self.gui, '书库已切换', '请在目标书库中重新获取。', show=True)

        matches, skipped = job.result
        original = {book_id: (title, authors, identifiers) for book_id, title, authors, identifiers in targets}
        applied = set()
        for book_id, title, book in matches:
            if not db.has_id(book_id):
                skipped.append((title, '该书已移出书库。'))
                continue
            current = db.get_metadata(book_id, get_user_categories=False)
            if (current.title, current.authors, current.get_identifiers()) != original[book_id]:
                skipped.append((title, '书名、作者或标识符有更新，请重新获取。'))
                continue
            try:
                apply_book(db, book_id, source, book)
            except (ValueError, OSError) as error:
                skipped.append((title, str(error)))
            else:
                applied.add(book_id)

        if applied:
            self.gui.iactions['Edit Metadata'].refresh_books_after_metadata_edit(applied)
        message = f'已更新 {len(applied)} 本书的网文元数据。'
        if skipped:
            details = '\n'.join(f'{title}（{reason}）' for title, reason in skipped)
            return info_dialog(self.gui, '网文元数据', message + f' 跳过 {len(skipped)} 本。', details, show=True)
        self.gui.status_bar.show_message(message, 5000)

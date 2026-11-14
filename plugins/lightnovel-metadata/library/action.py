"""Look up selected editions by ISBN without replacing owned covers."""

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from functools import partial

from calibre.customize.ui import metadata_plugins
from calibre.gui2 import error_dialog, info_dialog
from calibre.gui2.actions import InterfaceAction
from calibre.gui2.threaded_jobs import ThreadedJob

from .storage import apply_book, compatible_columns, ensure_columns


SOURCE_NAME = 'LightNovel Metadata'
ACTION_NAME = 'LightNovel Library'
TITLE = '轻小说书目'
TAIWAN_ISBN = ('978626', '978957', '978986')
JAPANESE_EDITIONS = {'日版', '日本版', '日文版'}
TAIWAN_EDITIONS = {'台版', '臺版', '台湾版', '台灣版', '臺灣版'}
VOLUME = re.compile(r'第\s*([0-9]{1,3}(?:\.[0-9]+)?|[一二三四五六七八九十]{1,3})\s*[卷巻册冊]')
PART = re.compile(r'[〈《(【\[]\s*([上中下])\s*[〉》)】\]]|([上中下])\s*[卷巻册冊篇編]\s*$')


@dataclass(frozen=True)
class Target:
    book_id: int
    title: str
    authors: tuple
    identifiers: dict
    series: str
    series_index: float
    edition_markers: frozenset
    has_cover: bool = field(compare=False)


def snapshot_book(db, book_id):
    metadata = db.get_metadata(book_id, get_user_categories=False)
    version = metadata.get('#version') or ()
    if isinstance(version, str):
        version = (version,)
    markers = frozenset(value.strip() for value in (*version, *(metadata.tags or ())) if isinstance(value, str))
    return Target(book_id, metadata.title, tuple(metadata.authors or ()), metadata.get_identifiers(),
                  metadata.series, metadata.series_index,
                  markers & (JAPANESE_EDITIONS | TAIWAN_EDITIONS), bool(db.field_for('cover', book_id)))


def isbn_counts(db):
    from calibre_plugins.lightnovel_metadata.models import isbn

    identifiers = db.all_field_for('identifiers', db.all_book_ids())
    return Counter(code for ids in identifiers.values() if (code := isbn((ids or {}).get('isbn'))))


def volume_marks(title):
    from calibre_plugins.lightnovel_metadata.models import volume_info

    title = unicodedata.normalize('NFKC', title or '')
    _, number = volume_info(title)
    part = PART.search(title)
    explicit = VOLUME.search(title)
    if explicit:
        value = explicit[1]
        if value[0].isascii():
            number = float(value)
        else:
            digits = '零一二三四五六七八九'
            cardinal = re.fullmatch(r'([一二三四五六七八九])?十([一二三四五六七八九])?', value)
            if cardinal:
                number = (digits.index(cardinal[1]) if cardinal[1] else 1) * 10 + (digits.index(cardinal[2]) if cardinal[2] else 0)
            elif len(value) == 1:
                number = digits.index(value)
    return number, (part[1] or part[2]) if part else None


def edition_conflict(target, record, isbn_code):
    if (target.edition_markers & TAIWAN_EDITIONS and isbn_code.startswith('9784')) or (
        target.edition_markers & JAPANESE_EDITIONS and isbn_code.startswith(TAIWAN_ISBN)
    ):
        return '已有版本标注与 ISBN 的出版地区冲突。'
    from calibre_plugins.lightnovel_metadata.models import norm

    local_number, local_part = volume_marks(target.title)
    remote_number, remote_part = volume_marks(record.title)
    if local_number is None and target.series and record.series and norm(target.series) == norm(record.series):
        local_number = target.series_index
    official_numbers = {value for value in (remote_number, record.series_index) if value is not None}
    if (local_number is not None and any(number != local_number for number in official_numbers)) or (
        local_part and remote_part and local_part != remote_part
    ):
        return '已有卷次与 ISBN 对应作品的卷次冲突。'
    return ''


def fetch_books(source, targets, counts, *, abort, log, notifications):
    from calibre_plugins.lightnovel_metadata.models import isbn

    matches, skipped = [], []
    for index, target in enumerate(targets):
        if abort.is_set():
            break
        notifications.put((index / len(targets), target.title))
        code = isbn(target.identifiers.get('isbn'))
        if not code:
            skipped.append((target.title, '缺少校验有效的 ISBN。'))
            continue
        if counts[code] > 1:
            skipped.append((target.title, f'书库中有多本书使用 ISBN {code}，请先核对。'))
            continue
        options = source.identify_books(log, abort, identifiers=target.identifiers)
        candidates = [record for record in options if record.isbn == code and not record.work_level]
        if len(candidates) != 1:
            reason = '有相互冲突的版本候选，请在 Calibre 的下载窗口核对。' if candidates else '未找到 ISBN 完全匹配的版本。'
            skipped.append((target.title, reason))
            continue
        record = candidates[0]
        conflict = edition_conflict(target, record, code)
        if conflict:
            skipped.append((target.title, conflict))
            continue
        cover = None
        if record.cover and not target.has_cover and not abort.is_set():
            cover = source.cover_for_book(log, abort, record)
        matches.append((target, record, cover))
    return matches, skipped


class LightNovelLibraryAction(InterfaceAction):
    name = ACTION_NAME
    action_spec = (TITLE, 'download-metadata.png', '按 ISBN 补齐选中轻小说的出版资料和专用栏目', None)
    action_add_menu = True
    action_menu_clone_qaction = '按 ISBN 补齐选中书籍'
    dont_add_to = frozenset({'toolbar-device', 'context-menu-device', 'menubar-device'})
    action_type = 'current'

    def genesis(self):
        self.job = None
        self.qaction.triggered.connect(self.fetch_selected)
        self.create_menu_action(self.qaction.menu(), 'lightnovel-library-create-columns', '建立轻小说书目栏目',
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
            return error_dialog(self.gui, '未能建立轻小说书目栏目', '请检查当前书库的栏目配置。', str(error), show=True)
        if created:
            self.gui.must_restart_before_config = True
            return info_dialog(self.gui, '已建立轻小说书目栏目', '已在当前书库创建栏目，重启 Calibre 后可以填写。', show=True)
        info_dialog(self.gui, '轻小说书目栏目已就绪', '当前书库已包含所需栏目。', show=True)

    def fetch_selected(self):
        if self.job is not None and not self.job.killed:
            self.gui.status_bar.show_message('正在获取轻小说元数据', 3000)
            return
        source = next((plugin for plugin in metadata_plugins(['identify']) if plugin.name == SOURCE_NAME), None)
        if source is None or source.version < (0, 3, 0):
            return error_dialog(self.gui, '轻小说元数据来源未启用',
                                '请安装并启用 LightNovel Metadata 0.3.0 或更新版本。', show=True)
        db = self.gui.current_db.new_api
        missing, incompatible = compatible_columns(db)
        if incompatible:
            headings = '、'.join(spec.heading for spec in incompatible)
            return error_dialog(self.gui, '轻小说书目栏目设置冲突', f'请在首选项中核对这些栏目：{headings}', show=True)
        if missing:
            return info_dialog(self.gui, '请先建立轻小说书目栏目',
                               '选择「轻小说书目 → 建立轻小说书目栏目」，重启 Calibre 后再补齐书籍资料。', show=True)
        targets = [snapshot_book(db, book_id) for book_id in self.gui.library_view.get_selected_ids()]
        if not targets:
            return info_dialog(self.gui, '请选择书籍', '请先在书库中选中要更新的书籍。', show=True)
        callback = self.Dispatcher(partial(self.finish_fetch, db, source))
        self.job = ThreadedJob('lightnovel-library-fetch', '获取轻小说元数据', fetch_books,
                               (source, targets, isbn_counts(db)), {}, callback)
        self.gui.job_manager.run_threaded_job(self.job)
        self.gui.status_bar.show_message('正在获取轻小说元数据', 3000)

    def finish_fetch(self, db, source, job):
        if self.job is not job:
            return
        self.job = None
        if job.killed or job.abort.is_set():
            return
        if job.failed:
            return self.gui.job_exception(job, dialog_title='未能获取轻小说元数据')
        if self.gui.current_db.new_api is not db:
            return info_dialog(self.gui, '书库已切换', '请在目标书库中重新获取。', show=True)

        matches, skipped = job.result
        applied = set()
        covers_added = 0
        counts = isbn_counts(db) if matches else Counter()
        for target, record, cover in matches:
            if not db.has_id(target.book_id) or snapshot_book(db, target.book_id) != target:
                skipped.append((target.title, '下载期间书籍或版本信息发生变化，请重新获取。'))
                continue
            if counts[record.isbn] > 1:
                skipped.append((target.title, f'书库中有多本书使用 ISBN {record.isbn}，请先核对。'))
                continue
            try:
                covers_added += bool(apply_book(db, target.book_id, source, record, cover=cover))
            except (ValueError, OSError) as error:
                skipped.append((target.title, str(error)))
                continue
            applied.add(target.book_id)

        if applied:
            self.gui.iactions['Edit Metadata'].refresh_books_after_metadata_edit(applied)
        message = f'已处理 {len(applied)} 本书，补封面 {covers_added} 张。'
        if skipped:
            details = '\n'.join(f'{title}（{reason}）' for title, reason in skipped)
            return info_dialog(self.gui, TITLE, message + f' 跳过 {len(skipped)} 本。', details, show=True)
        self.gui.status_bar.show_message(message, 5000)

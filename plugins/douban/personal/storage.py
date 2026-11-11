"""Small Calibre database adapter. No network, Qt or direct SQLite access."""

from copy import deepcopy
from dataclasses import dataclass

from .core import DoubanError, subject_id_from_identifiers
from .sync import FIELD_SPECS, build_plan, values_equal


RECEIPT_KEY = 'douban_reading_records.v1'


@dataclass(frozen=True)
class BookTarget:
    book_id: int
    book_uuid: str
    subject_id: str
    title: str
    current: dict
    previous: object


def read_values(db, book_id):
    return {key: db.field_for(spec['column'], book_id)
            for key, spec in FIELD_SPECS.items()}


def capture_targets(db, book_ids):
    previous = db.get_custom_book_data(RECEIPT_KEY, book_ids)
    targets, skipped = [], []
    for book_id in book_ids:
        title = db.field_for('title', book_id) or str(book_id)
        try:
            subject_id = subject_id_from_identifiers(db.field_for('identifiers', book_id) or {})
        except DoubanError as exc:
            skipped.append((title, str(exc)))
            continue
        if not subject_id:
            skipped.append((title, '没有豆瓣条目 ID；请先用 New Douban 下载元数据，或填写 douban:条目数字。'))
            continue
        uuid = db.field_for('uuid', book_id)
        if not uuid:
            skipped.append((title, '书籍身份不可用，已跳过。'))
            continue
        targets.append(BookTarget(book_id, uuid, subject_id, title,
                                  read_values(db, book_id), deepcopy(previous.get(book_id))))
    return targets, skipped


def compatible_columns(db):
    missing, incompatible = [], []
    for spec in FIELD_SPECS.values():
        field = db.field_metadata.get(spec['column'])
        if field is None:
            missing.append(spec['column'])
        elif (field.get('datatype') != spec['datatype']
              or bool(field.get('is_multiple')) != spec['is_multiple']):
            incompatible.append(spec['column'])
    return missing, incompatible


def apply_selected(db, library_id, get_current_db, account_id, selected):
    """Apply approved (target, change, record) rows after a fresh check.

    Persist each applied field's actual readback. A write failure can leave some
    fields applied: report their count and never claim a batch transaction.
    """
    written, skipped = [], []
    for target, change, record in selected:
        try:
            if get_current_db() is not db or db.library_id != library_id:
                return written, skipped, '书库已切换；后续写入已停止。'
            if not change.allowed:
                skipped.append((target.title, '该字段未获准写入。'))
                continue
            if change.key not in FIELD_SPECS or change.column != FIELD_SPECS[change.key]['column']:
                skipped.append((target.title, '字段与预设的个人记录列不符，请重新读取。'))
                continue
            if record.account_id != account_id or record.subject_id != target.subject_id:
                skipped.append((target.title, '预览记录的账号或豆瓣条目不匹配，请重新读取。'))
                continue
            if (db.field_for('uuid', target.book_id) != target.book_uuid
                    or subject_id_from_identifiers(db.field_for('identifiers', target.book_id) or {}) != target.subject_id):
                skipped.append((target.title, '书籍或豆瓣条目关联已改变，请重新读取。'))
                continue
            current = read_values(db, target.book_id)
            if not values_equal(change.key, current[change.key], change.before):
                skipped.append((target.title, '预览后本地字段发生变化，已保留。'))
                continue
            previous = db.get_custom_book_data(RECEIPT_KEY, [target.book_id]).get(target.book_id)
            # Re-check ownership using the current receipt, not the old preview.
            recheck = next(row for row in build_plan(
                target.book_id, target.book_uuid, account_id, target.subject_id,
                current, previous, record.values) if row.key == change.key)
            if not recheck.allowed:
                skipped.append((target.title, recheck.reason))
                continue
            if not values_equal(change.key, recheck.after, change.after):
                skipped.append((target.title, '预览来源的值已改变，请重新读取。'))
                continue
            db.set_field(change.column, {target.book_id: change.after}, allow_case_change=False)
            written.append((target.book_id, change.key))
            receipt = deepcopy(previous) if isinstance(previous, dict) else {
                'account_id': account_id, 'subject_id': target.subject_id,
                'book_uuid': target.book_uuid, 'values': {},
            }
            receipt['values'][change.key] = db.field_for(change.column, target.book_id)
            db.add_custom_book_data(RECEIPT_KEY, {target.book_id: receipt})
        except Exception:
            # Never include exception text: it can contain local paths or content.
            return written, skipped, '写入未能全部完成；已写入的字段保留，后续写入已停止。请重新打开插件核对。'
    return written, skipped, None

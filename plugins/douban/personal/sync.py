"""Plan conservative writes to dedicated Calibre personal-reading columns.

This module has no Calibre or Qt dependency. A plan never writes anything: the
caller must re-check the library, book UUID and current values before applying
selected rows, then save the values actually read back from the database.
"""

from dataclasses import dataclass
from html import escape


FIELD_SPECS = {
    "tags": {
        "column": "#douban_my_tags",
        "name": "豆瓣个人标签",
        "datatype": "text",
        "is_multiple": True,
    },
    "rating": {
        "column": "#douban_my_rating",
        "name": "豆瓣个人评分",
        "datatype": "rating",
        "is_multiple": False,
    },
    "status": {
        "column": "#douban_read_status",
        "name": "豆瓣阅读状态",
        "datatype": "text",
        "is_multiple": False,
    },
    "comment": {
        "column": "#douban_my_comment",
        "name": "豆瓣简评",
        "datatype": "comments",
        "is_multiple": False,
    },
}

STATUS_LABELS = {"wish": "想读", "do": "在读", "collect": "读过"}


@dataclass(frozen=True)
class FieldChange:
    key: str
    column: str
    before: object
    after: object
    allowed: bool
    reason: str


def _empty(key, value):
    if value is None:
        return True
    if key == "rating":
        return value == 0
    if key == "tags" and isinstance(value, (list, tuple)):
        return not value
    return isinstance(value, str) and not value.strip()


def values_equal(key, first, second):
    """Compare DB-shaped values without erasing meaningful local edits.

    Calibre can return multiple text values as tuples and in a different order.
    Tags are therefore compared as sets of exact strings. Comments remain exact
    HTML comparisons: callers should snapshot the database's read-back value.
    """
    if _empty(key, first) and _empty(key, second):
        return True
    if key == "tags" and isinstance(first, (list, tuple)) and isinstance(second, (list, tuple)):
        if all(isinstance(item, str) for item in (*first, *second)):
            return set(first) == set(second)
    return first == second


def _convert(key, value):
    """Convert one recognized source field to a database value.

    ValueError means the source shape is unsupported. Empty recognized values
    remain distinguishable from missing or malformed values, but never authorize
    clearing a local field in this initial import policy.
    """
    if value is None:
        return None
    if key == "tags":
        if not isinstance(value, (list, tuple)) or not all(isinstance(tag, str) for tag in value):
            raise ValueError("tags")
        return list(dict.fromkeys(tag.strip() for tag in value if tag.strip()))
    if key == "rating":
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 5:
            raise ValueError("rating")
        return value * 2
    if key == "status":
        if value == "":
            return ""
        if not isinstance(value, str) or value not in STATUS_LABELS:
            raise ValueError("status")
        return STATUS_LABELS[value]
    if key == "comment":
        if not isinstance(value, str):
            raise ValueError("comment")
        if not value.strip():
            return ""
        text = value.replace("\r\n", "\n").replace("\r", "\n")
        return "<p>" + escape(text).replace("\n", "<br />") + "</p>"
    raise ValueError("field")


def build_plan(book_id, book_uuid, account_id, subject_id, current, previous, incoming_values):
    """Return four preview rows; only ``allowed`` rows may be selected.

    ``current`` and ``previous['values']`` use field keys rather than column
    names. Source values use a five-star integer rating and canonical Douban
    status. A previous snapshot is scoped to the book UUID, account and edition;
    a mismatch blocks the entire book until the caller resolves the association.

    ``book_id`` is accepted for callers that pair plans with their database IDs;
    identity checks deliberately use the persistent UUID instead of that local
    integer. No current values or snapshots are modified by this function.
    """
    identity_error = None
    old_values = {}
    if previous is not None:
        if not isinstance(previous, dict) or not isinstance(previous.get("values"), dict):
            identity_error = "历史同步记录不完整，保留本地值"
        elif any(previous.get(key) != value for key, value in (
            ("book_uuid", book_uuid),
            ("account_id", account_id),
            ("subject_id", subject_id),
        )):
            identity_error = "账号、书籍或豆瓣版本与上次导入不同，保留本地值"
        else:
            old_values = previous["values"]

    plan = []
    for key, spec in FIELD_SPECS.items():
        before = current.get(key)
        after = before
        allowed = False
        if key not in incoming_values:
            reason = "来源未提供此字段，保留本地值"
        else:
            try:
                after = _convert(key, incoming_values[key])
            except ValueError:
                reason = "来源格式无法识别，保留本地值"
            else:
                if identity_error:
                    reason = identity_error
                elif _empty(key, after):
                    reason = "来源为空，保留本地值"
                elif key in old_values:
                    if not values_equal(key, before, old_values[key]):
                        reason = "本地已手动修改或清空，保留本地值"
                    elif values_equal(key, before, after):
                        reason = "未变化"
                    else:
                        allowed = True
                        reason = "更新上次由本插件写入的值"
                elif not _empty(key, before):
                    reason = "本地已有内容，保留手动整理"
                else:
                    allowed = True
                    reason = "填入空白字段"
        plan.append(FieldChange(key, spec["column"], before, after, allowed, reason))
    return plan

"""Custom columns and typed field conversion for the Calibre library action."""

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal


PLATFORMS = {
    "qidian": ("起点中文网", "https://m.qidian.com/book/", "/"),
    "qimao": ("七猫中文网", "https://www.qimao.com/shuku/", "/"),
    "fanqie": ("番茄小说", "https://fanqienovel.com/page/", ""),
}


def platform_link_template():
    branches = [
        (
            f"field('item_value') == '{name}' && "
            f"contains(id = select(ids, '{provider}'), '^[0-9]{{1,32}}$', '1', '') "
            f"then strcat('{prefix}', id, '{suffix}')"
        )
        for provider, (name, prefix, suffix) in PLATFORMS.items()
    ]
    return "program: ids = field('identifiers'); if " + " elif ".join(branches) + " fi"


@dataclass(frozen=True)
class Column:
    label: str
    heading: str
    datatype: str
    display: dict

    @property
    def key(self):
        return "#" + self.label


COLUMN_SPECS = (
    Column("webnovel_platform", "连载平台", "text", {
        "description": "网络连载平台。点击书籍详情中的平台名称可打开该作品；电子书文件来源请记录在「来源」。",
        "web_search_template": platform_link_template(),
    }),
    Column("webnovel_first_published", "首发日期", "datetime", {
        "description": "官网明确提供的作品首发日期。",
        "date_format": "yyyy-MM-dd",
    }),
    Column("webnovel_word_count", "字数", "int", {
        "description": "平台公布的字数。以万字或亿字公布时，换算后保留原数据的精度。",
        "number_format": "{0:,}",
    }),
    Column("webnovel_status", "连载状态", "text", {"description": "平台公布的作品连载状态。"}),
    Column("webnovel_updated", "最近更新", "datetime", {
        "description": "平台公布的最后更新时间；官网未注明时区时按中国标准时间解释。",
        "date_format": "yyyy-MM-dd hh:mm",
    }),
    Column("webnovel_latest_chapter", "最新章节", "text", {"description": "平台公布的最新章节标题。"}),
)

CHINA_TIMEZONE = timezone(timedelta(hours=8))
WORD_COUNT = re.compile(r"([0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)(\.[0-9]+)?([万亿])?字?")
UPDATE_DATETIME = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}[T ][0-9]{2}:[0-9]{2}"
    r"(?::[0-9]{2}(?:\.[0-9]{1,6})?)?(?:Z|[+-][0-9]{2}:[0-9]{2})?"
)


def compatible_columns(db):
    """Return the missing and incompatible column specs, in display order."""
    fields = db.field_metadata.custom_field_metadata()
    names = {field["name"] for field in fields.values()}
    missing, incompatible = [], []
    for spec in COLUMN_SPECS:
        field = fields.get(spec.key)
        if field is None:
            (incompatible if spec.heading in names else missing).append(spec)
        elif (
            field["datatype"] != spec.datatype
            or field["is_multiple"]
            or (
                "web_search_template" in spec.display
                and field["display"].get("web_search_template") != spec.display["web_search_template"]
            )
        ):
            incompatible.append(spec)
    return missing, incompatible


def ensure_columns(db):
    """Create missing columns using Calibre's database API. Reopen to use them."""
    missing, incompatible = compatible_columns(db)
    if incompatible:
        raise ValueError("以下栏目与网文元数据设置冲突：" + "、".join(spec.heading for spec in incompatible))
    for spec in missing:
        db.create_custom_column(spec.label, spec.heading, spec.datatype, False, display=spec.display)
    return [spec.key for spec in missing]


def parse_word_count(value):
    match = WORD_COUNT.fullmatch(re.sub(r"\s+", "", value or ""))
    if not match:
        return None
    whole, decimal, unit = match.groups()
    multiplier = {None: 1, "万": 10000, "亿": 100000000}[unit]
    count = Decimal(whole.replace(",", "") + (decimal or "")) * multiplier
    if count == count.to_integral_value() and 0 <= count <= 2**63 - 1:
        return int(count)
    return None


def first_publication(value):
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value or ""):
        return None
    try:
        return datetime.fromisoformat(value).replace(hour=12, tzinfo=timezone.utc)
    except ValueError:
        return None


def last_update(value):
    value = (value or "").strip()
    if not UPDATE_DATETIME.fullmatch(value):
        return None
    try:
        date = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return date if date.tzinfo else date.replace(tzinfo=CHINA_TIMEZONE)


def add_webnovel_fields(db, data, metadata):
    """Attach a verified candidate's identifier and supplied custom field values."""
    missing, incompatible = compatible_columns(db)
    if missing or incompatible:
        raise ValueError("请先设置网文栏目：" + "、".join(spec.heading for spec in (*missing, *incompatible)))
    metadata.set_identifier(data.ref.provider, data.ref.book_id)
    values = {
        "#webnovel_platform": PLATFORMS[data.ref.provider][0],
        "#webnovel_first_published": first_publication(data.published_at),
        "#webnovel_word_count": parse_word_count(data.word_count),
        "#webnovel_status": data.serialization_status or None,
        "#webnovel_updated": last_update(data.updated_at),
        "#webnovel_latest_chapter": data.latest_chapter or None,
    }
    for key, value in values.items():
        if value is not None:
            metadata.set_user_metadata(key, db.field_metadata[key])
            metadata.set(key, value)
    return metadata

"""Calibre-independent edition records and conservative matching rules."""
from dataclasses import dataclass, field
from datetime import datetime
from copy import deepcopy
from difflib import SequenceMatcher
import re
import unicodedata


def isbn(value):
    """Return a checksum-valid ISBN-13 (or an ISBN-10 converted to ISBN-13)."""
    value = re.sub(r'[-\s]', '', str(value or '')).upper()
    if re.fullmatch(r'97[89][0-9]{10}', value):
        if sum(int(n) * (1 if i % 2 == 0 else 3) for i, n in enumerate(value[:12])) % 10 == (10 - int(value[-1])) % 10:
            return value
    if re.fullmatch(r'[0-9]{9}[0-9X]', value):
        total = sum((10-i) * (10 if n == 'X' else int(n)) for i, n in enumerate(value))
        if total % 11 == 0:
            prefix = '978' + value[:9]
            check = (-sum(int(n) * (1 if i % 2 == 0 else 3) for i, n in enumerate(prefix))) % 10
            return prefix + str(check)
    return ''


def norm(value):
    return ''.join(c for c in unicodedata.normalize('NFKC', str(value or '')).casefold() if c.isalnum())


def clean(value):
    return re.sub(r'\s+', ' ', str(value or '').replace('\u3000', ' ')).strip()


def safe_date(value):
    """Only full dates are eligible for Calibre pubdate; year/month precision stays out."""
    raw = clean(value)
    match = re.fullmatch(r'(\d{4})[-/年]?(\d{1,2})[-/月]?(\d{1,2})日?', raw)
    if not match:
        return ''
    try:
        return datetime(*map(int, match.groups())).strftime('%Y-%m-%d')
    except ValueError:
        return ''


def volume_info(title):
    """Read only an explicit numeric volume marker, never a year or book count.

    Fractional volumes (e.g. 7.5) are meaningful and must not be rounded.
    The text after a marker may be a subtitle.  Side-story labels stay separate.
    """
    title = clean(title)
    forms = (
        r'^(.*?)\s*第\s*(\d{1,3}(?:\.\d)?)\s*[卷巻册冊](?:\s|$)',
        r'^(.*?)\s*[（(]\s*第?\s*(\d{1,3}(?:\.\d)?)\s*[卷巻册冊]?\s*[）)](?=\s|$|[^\d])',
        r'^(.*?)\s+Vol(?:ume)?\.?\s*(\d{1,3}(?:\.\d)?)(?:\s|$)',
    )
    for pattern in forms:
        matched = re.match(pattern, title, re.I)
        if matched and clean(matched.group(1)) and float(matched.group(2)) > 0:
            return clean(matched.group(1)), float(matched.group(2))
    return '', None


@dataclass
class Record:
    source: str
    source_id: str
    title: str
    authors: list = field(default_factory=list)
    isbn: str = ''
    original_title: str = ''
    publisher: str = ''
    pubdate: str = ''
    date_text: str = ''
    language: str = ''
    description: str = ''
    cover: str = ''
    url: str = ''
    tags: list = field(default_factory=list)
    translators: list = field(default_factory=list)
    illustrators: list = field(default_factory=list)
    series: str = ''
    series_index: float = None
    work_level: bool = False
    source_labels: list = field(default_factory=list)
    identifiers: dict = field(default_factory=dict)
    series_subject_id: str = ''
    relations: list = field(default_factory=list)
    field_sources: dict = field(default_factory=dict)

    def __post_init__(self):
        self.isbn = isbn(self.isbn)
        self.title = clean(self.title)
        self.authors = list(dict.fromkeys(clean(x) for x in self.authors if clean(x)))
        self.translators = list(dict.fromkeys(clean(x) for x in self.translators if clean(x)))
        self.illustrators = list(dict.fromkeys(clean(x) for x in self.illustrators if clean(x)))
        self.tags = list(dict.fromkeys(clean(x) for x in self.tags if clean(x)))
        self.pubdate = safe_date(self.pubdate)
        candidate_series, candidate_index = volume_info(self.title)
        if not self.work_level and candidate_index is not None:
            if not self.series:
                self.series, self.series_index = candidate_series, candidate_index
            elif self.series_index is None and norm(self.series) == norm(candidate_series):
                self.series_index = candidate_index
        if self.source in ('bangumi', 'books_tw', 'kadokawa_tw', 'spp_tw') and self.source_id:
            self.identifiers[self.source] = str(self.source_id)
        if not self.source_labels:
            self.source_labels = [self.source]


def relevance(book, query_title, query_authors=()):
    """Never equate different explicit volumes, and don't require cross-script title equality."""
    if not query_title:
        return (0, 0.0)
    text = norm(query_title)
    values = [norm(book.title), norm(book.original_title)]
    score = max((SequenceMatcher(None, text, v).ratio() for v in values if v), default=0)
    q_series, q_volume = volume_info(query_title)
    b_series, b_volume = volume_info(book.title)
    if q_volume is not None:
        if b_volume is not None and q_volume != b_volume:
            return None
        if b_volume is None and book.series_index != q_volume:
            # A bare series name is not evidence that it is this volume.
            return None
    if score < 0.58:
        return None
    # Author matching can be weak across CJK translations; use for ranking only.
    known = [norm(a) for a in (query_authors or ()) if norm(a) not in ('unknown', '未知', '佚名')]
    match_author = not known or any(any(a in norm(b) or norm(b) in a for b in book.authors if norm(b)) for a in known)
    return (0 if score > 0.93 else 1, 1.0 - score + (0 if match_author else 0.1))


FIELD_NAMES = ('title', 'authors', 'original_title', 'publisher', 'pubdate',
               'date_text', 'description', 'cover', 'language', 'series',
               'series_index', 'tags', 'illustrators', 'translators')
SOURCES = ('bangumi', 'books_tw', 'kadokawa_tw', 'spp_tw', 'ncl_tw', 'openbd', 'ndl')


def _source_order(code):
    if code.startswith(('978626', '978986', '978957')):
        return ('kadokawa_tw', 'spp_tw', 'books_tw', 'ncl_tw', 'bangumi', 'openbd', 'ndl')
    return ('openbd', 'ndl', 'bangumi', 'kadokawa_tw', 'spp_tw', 'books_tw', 'ncl_tw')


def combine(records, preferences=None):
    """Fuse *edition-level* evidence by exact checksum-valid ISBN only.

    Per-field preferences apply only within an ISBN identity group. A source
    preference never triggers cross-ISBN borrowing, including covers.
    """
    prefs = preferences or {}
    groups = {}
    for rec in records:
        key = ('isbn:' + rec.isbn if rec.isbn and not rec.work_level
               else '%s:%s' % (rec.source, rec.source_id))
        groups.setdefault(key, []).append(rec)
    result = []
    for group in groups.values():
        if len(group) == 1:
            entry = deepcopy(group[0])
            entry.field_sources = {k: entry.source for k in FIELD_NAMES if getattr(entry, k)}
            result.append(entry)
            continue
        # Even a checksum-valid ISBN should not override direct contradictory
        # evidence. A wrong ISBN copied from another volume is a common source
        # of automatic catalogue corruption.
        explicit_volumes = {r.series_index for r in group if r.series_index is not None}
        explicit_languages = {r.language for r in group if r.language}
        if len(explicit_volumes) > 1 or len(explicit_languages) > 1:
            raise ValueError('同一 ISBN 的卷次或语言互相冲突，拒绝自动融合。')
        order = _source_order(group[0].isbn)
        sorted_group = sorted(group, key=lambda r: order.index(r.source) if r.source in order else 99)
        ids = {}
        for rec in sorted_group:
            for source, sid in rec.identifiers.items():
                if source in ids and ids[source] != sid:
                    raise ValueError('一个 ISBN 对应相互冲突的来源条目 ID，拒绝自动合并。')
                ids[source] = sid
        merged = deepcopy(sorted_group[0])
        merged.identifiers = ids
        merged.source_labels = list(dict.fromkeys(r.source for r in sorted_group))
        merged.field_sources = {}
        for field_name in FIELD_NAMES:
            preferred_source = prefs.get(field_name, 'auto')
            chosen_group = sorted_group
            if preferred_source in SOURCES:
                chosen_group = sorted(sorted_group, key=lambda r: 0 if r.source == preferred_source else 1)
            chosen = next((r for r in chosen_group if getattr(r, field_name)), None)
            if chosen is not None:
                value = getattr(chosen, field_name)
                setattr(merged, field_name, deepcopy(value))
                merged.field_sources[field_name] = chosen.source
            else:
                setattr(merged, field_name, [] if field_name in ('tags', 'translators', 'illustrators', 'authors')
                        else None if field_name == 'series_index' else '')
        # Source-controlled tags/credits may be additive by default; explicit
        # selection switches those fields to single-source preference.
        for key in ('tags', 'translators', 'illustrators'):
            if prefs.get(key, 'auto') == 'auto':
                setattr(merged, key, list(dict.fromkeys(value for r in sorted_group
                                                       for value in getattr(r, key))))
                merged.field_sources[key] = ','.join(r.source for r in sorted_group if getattr(r, key))
        for rec in sorted_group:
            if rec.series_subject_id:
                merged.series_subject_id = rec.series_subject_id
                break
        merged.relations = list(dict.fromkeys((rel.get('id'), rel.get('relation'))
                                                 for rec in sorted_group for rel in rec.relations
                                                 if isinstance(rel, dict)))
        merged.relations = [{'id': sid, 'relation': rel} for sid, rel in merged.relations]
        result.append(merged)
    return result

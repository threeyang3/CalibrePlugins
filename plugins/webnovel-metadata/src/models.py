"""Calibre-independent data exchanged by the platform adapters."""

import re
from dataclasses import dataclass, field
from typing import List


BOOK_URLS = {
    'qidian': 'https://www.qidian.com/book/{}/',
    'qimao': 'https://www.qimao.com/shuku/{}/',
    'fanqie': 'https://fanqienovel.com/page/{}',
}


@dataclass(frozen=True)
class BookRef:
    provider: str
    book_id: str

    def __post_init__(self):
        if self.provider not in BOOK_URLS or not isinstance(self.book_id, str):
            raise ValueError('无效的作品来源或作品 ID。')
        if not re.fullmatch(r'[0-9]{1,32}', self.book_id):
            raise ValueError('作品 ID 必须是十进制数字字符串。')

    @property
    def url(self):
        return BOOK_URLS[self.provider].format(self.book_id)


@dataclass
class BookMetadata:
    ref: BookRef
    title: str
    authors: List[str]
    description: str = ''
    cover_url: str = ''
    tags: List[str] = field(default_factory=list)
    serialization_status: str = ''
    word_count: str = ''
    updated_at: str = ''
    latest_chapter: str = ''
    published_at: str = ''

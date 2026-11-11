"""Seven Cats book metadata, scoped to the book's own information block."""

import re
from urllib.parse import urlsplit

from ..models import BookMetadata
from .common import attr, by_class, class_xpath, first, image_url, node_text, status, text, unique


def parse(root, ref):
    header = first(root, by_class('book-information'))
    title = text(header, './/*[%s]/*[%s]/*[%s]' % (
        class_xpath('wrap-txt'), class_xpath('title'), class_xpath('txt')))
    authors = []
    if header is not None:
        for node in header.xpath('.//*[%s]/*[%s]' % (class_xpath('sub-title'), class_xpath('txt'))):
            if re.match(r'^作者\s*[：:]', node_text(node)):
                author = text(node, './/em/a')
                if author:
                    authors.append(author)
    result = BookMetadata(ref, title, unique(authors))
    result.description = text(root, './/*[%s]//*[%s]' % (
        class_xpath('book-introduction'), class_xpath('intro')), breaks=True)
    cover = image_url(attr(header, './/*[%s]/img' % class_xpath('wrap-pic'), 'src'), ref.url)
    if cover:
        parts = urlsplit(cover)
        if parts.hostname in ('cdn.qimao.com', 'cdn.wtzw.com') and re.match(r'^/bookimg/.*/(?:readerCover|cover)/', parts.path):
            result.cover_url = cover
    tags = first(header, by_class('tags-wrap'))
    if tags is not None:
        result.tags = unique(node_text(node) for node in tags.xpath('.//a[contains(@href, "/shuku/a-")]'))
        for node in tags.xpath('./*[%s]' % class_xpath('qm-tag')):
            result.serialization_status = status(node_text(node))
            if result.serialization_status:
                break
    statistics = first(header, by_class('statistics-wrap'))
    if statistics is not None:
        for node in statistics.xpath('./*[%s]' % class_xpath('txt')):
            value = re.sub(r'\s+', '', node_text(node))
            if re.fullmatch(r'\d[\d,.]*(?:万|亿)?字', value):
                result.word_count = value
                break
    result.updated_at = text(header, './/*[%s]//*[%s]' % (
        class_xpath('update-info'), class_xpath('update-time')))
    result.latest_chapter = text(header, './/*[%s]//*[%s]/a' % (
        class_xpath('update-info'), class_xpath('update-chapter-title')))
    return result

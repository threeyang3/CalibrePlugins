"""Fanqie DOM and identity-bound JSON data; no JavaScript evaluation."""

import json
import re
from urllib.parse import urljoin

from ..models import BookMetadata
from .common import attr, by_class, class_xpath, clean, first, image_url, initial_state, json_roots, node_text, status, text, unique


def page_data(root, ref):
    page = initial_state(root).get('page', {})
    if isinstance(page, dict) and str(page.get('bookId', '')) == ref.book_id:
        return page
    return {}


def parse(root, ref, parse_url):
    header = first(root, by_class('page-header-info'))
    page = page_data(root, ref)
    title = text(header, './/*[%s]/h1' % class_xpath('info-name')) or clean(page.get('bookName'))
    author = text(header, by_class('author-name-text')) or clean(page.get('author'))
    result = BookMetadata(ref, title, [author] if author else [])
    result.description = text(root, './/*[%s]//*[%s]' % (
        class_xpath('page-body'), class_xpath('page-abstract-content')), breaks=True)
    if not result.description:
        # "description" is the author's profile. "abstract" is the book synopsis.
        result.description = page.get('abstract') if isinstance(page.get('abstract'), str) else ''
    for record in json_roots(root):
        own_url = record.get('@id')
        if not isinstance(own_url, str) or parse_url(urljoin(ref.url, own_url)) != ref:
            continue
        values = record.get('images', record.get('image', []))
        values = values if isinstance(values, list) else [values]
        for value in values:
            if isinstance(value, dict):
                value = value.get('url')
            cover = image_url(value, ref.url)
            if cover:
                result.cover_url = cover
                break
        if result.cover_url:
            break
    result.cover_url = (result.cover_url or image_url(page.get('thumbUri'), ref.url)
                        or image_url(attr(header, by_class('book-cover-img'), 'src'), ref.url))
    if header is not None:
        result.tags = unique(node_text(node) for node in header.xpath(by_class('info-label-grey')))
    if not result.tags:
        try:
            categories = json.loads(page.get('categoryV2', '[]'))
        except (ValueError, TypeError):
            categories = []
        if isinstance(categories, list):
            result.tags = unique(clean(item.get('Name')) for item in categories if isinstance(item, dict))
    result.serialization_status = status(text(header, by_class('info-label-yellow')))
    result.word_count = re.sub(r'\s+', '', text(header, by_class('info-count-word')))
    words = page.get('wordNumber')
    if not result.word_count and isinstance(words, int) and not isinstance(words, bool) and words >= 0:
        result.word_count = str(words) + '字'
    result.updated_at = text(header, by_class('info-last-time'))
    result.latest_chapter = text(header, by_class('info-last-title')) or clean(page.get('lastChapterTitle'))
    result.latest_chapter = re.sub(r'^最近更新\s*[：:]\s*', '', result.latest_chapter)
    return result

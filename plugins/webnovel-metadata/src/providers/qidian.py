"""Qidian's public book page, including its older metadata-tag layout."""

import json
import re
from urllib.parse import urljoin

from ..models import BookMetadata
from .common import attr, by_class, class_xpath, clean, document, first, image_url, json_roots, meta, node_text, status, text, unique


def page_data(root):
    # Script text is intentionally excluded by node_text; read the JSON directly.
    script = first(root, '//script[@id="vite-plugin-ssr_pageContext"][@type="application/json"]')
    try:
        data = json.loads(script.text or '') if script is not None else {}
        return data['pageContext']['pageProps']['pageData']['bookInfo']
    except (KeyError, ValueError, TypeError):
        return {}


def parse(root, ref, parse_url):
    header = first(root, '//*[@id="book-detail"]//*[%s]' % class_xpath('book-info-top'))
    legacy = first(root, './/*[%s]/*[%s]' % (
        class_xpath('book-information'), class_xpath('book-info')))
    mobile = first(root, by_class('detail__header'))
    data = page_data(root)
    if not isinstance(data, dict) or str(data.get('bookId', '')) != ref.book_id:
        data = {}
    title = (text(header, './/*[@id="bookName"]')
             or text(mobile, by_class('detail__header-detail__title'))
             or meta(root, 'og:novel:book_name')
             or clean(data.get('bookName'))
             or text(legacy, './/h1/em'))
    author = (text(header, './/*[%s]//*[%s]' % (class_xpath('book-meta'), class_xpath('author')))
              or text(mobile, by_class('detail__header-detail__author-link'))
              or meta(root, 'og:novel:author')
              or clean(data.get('authorName'))
              or text(legacy, './/h1//a[%s]' % class_xpath('writer')))
    author = re.sub(r'^作者\s*[：:]\s*', '', author).strip()
    result = BookMetadata(ref, title, [author] if author else [])
    result.description = (text(root, '//*[@id="book-intro-detail"]', breaks=True)
                          or text(root, by_class('book-intro'), breaks=True)
                          or (node_text(document(data['desc']), breaks=True) if isinstance(data.get('desc'), str) and data['desc'].strip() else '')
                          or text(root, by_class('detail__summary__content'), breaks=True)
                          or meta(root, 'og:novel:description') or meta(root, 'og:description'))
    cover = first(root, '//*[@id="book-detail"]//*[@id="bookImg"]')
    if cover is not None and cover.get('data-bid') == ref.book_id:
        result.cover_url = image_url(attr(cover, './/img', 'src'), ref.url)
    # The mobile Book JSON-LD has a 600px cover instead of the 180px OG image.
    for record in json_roots(root):
        types = record.get('@type', [])
        types = [types] if isinstance(types, str) else types
        own_url = record.get('@id') or record.get('url')
        if isinstance(types, list) and 'Book' in types and isinstance(own_url, str) and parse_url(urljoin(ref.url, own_url)) == ref:
            result.cover_url = result.cover_url or image_url(record.get('image'), ref.url)
    if not result.cover_url:
        result.cover_url = image_url(meta(root, 'og:image'), ref.url)
    if not result.cover_url and legacy is not None:
        result.cover_url = image_url(attr(root, './/*[%s]/*[%s]//img' % (
            class_xpath('book-information'), class_xpath('book-img')), 'src'), ref.url)
    tag_root = first(header, by_class('book-attribute'))
    if tag_root is None:
        tag_root = first(legacy, by_class('tag'))
    if tag_root is not None:
        result.tags = unique(node_text(link) for link in tag_root.xpath('.//a'))
        result.serialization_status = next((status(node_text(node)) for node in tag_root.xpath('.//span') if status(node_text(node))), '')
    if not result.tags and meta(root, 'og:novel:category'):
        result.tags = [meta(root, 'og:novel:category')]
    if mobile is not None:
        result.tags = unique(result.tags + [node_text(node) for node in mobile.xpath(by_class('detail__header-detail__category'))])
    result.serialization_status = result.serialization_status or status(meta(root, 'og:novel:status'))
    if header is not None:
        for label in header.xpath('.//*[%s]//cite' % class_xpath('count')):
            previous = label.getprevious()
            if clean(node_text(label)) == '字' and previous is not None and previous.tag == 'em':
                result.word_count = node_text(previous) + '字'
                break
    result.word_count = result.word_count or meta(root, 'og:novel:word_count')
    if not result.word_count and clean(data.get('showWordsCnt')):
        result.word_count = clean(data['showWordsCnt']) + '字'
    result.updated_at = (text(header, by_class('update-time')) or meta(root, 'og:novel:update_time'))
    result.updated_at = re.sub(r'^更新时间\s*[：:]\s*', '', result.updated_at)
    result.latest_chapter = (text(header, by_class('book-latest-chapter'))
                             or meta(root, 'og:novel:latest_chapter_name'))
    result.latest_chapter = re.sub(r'^最新章节\s*[：:]\s*', '', result.latest_chapter)
    return result

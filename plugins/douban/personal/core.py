# SPDX-License-Identifier: Apache-2.0
"""Pure parsing for the current user's Douban book records.

This module intentionally does not depend on calibre or perform network I/O.
Selectors are restricted to account/navigation and personal collection regions;
community tags, scores and reviews are never substituted for missing own data.
"""

from dataclasses import dataclass
import json
import re
from urllib.parse import urljoin, urlsplit

from lxml import html as lxml_html


class DoubanError(Exception):
    """A user-facing error whose message must not contain response/secret data."""


class NoRecord(DoubanError):
    """No recognizable personal collection record; retain all local fields."""


class LoginRequired(DoubanError):
    pass


class AccessBlocked(DoubanError):
    pass


class Cancelled(DoubanError):
    pass


@dataclass(frozen=True)
class Account:
    user_id: str
    display_name: str


@dataclass(frozen=True)
class PersonalRecord:
    subject_id: str
    account_id: str
    values: dict


_ID = re.compile(r"[1-9][0-9]{0,19}\Z")
_PERSON = re.compile(r"/people/([A-Za-z0-9_-]{1,100})/?\Z")
_SUBJECT = re.compile(r"/subject/([1-9][0-9]{0,19})/?\Z")
_STATUS = {"wish": "wish", "do": "do", "collect": "collect",
           "想读": "wish", "在读": "do", "读过": "collect"}
_CLASS = "contains(concat(' ', normalize-space(@class), ' '), ' %s ')"


def subject_id_from_identifiers(identifiers):
    """Accept only exact IDs from the original/new metadata plugins.

    No title/ISBN guessing and no extracting a numeric substring from a URL.
    A missing ID returns None; invalid or conflicting explicit IDs are errors.
    """
    found = set()
    for key in ("new_douban", "douban"):
        value = identifiers.get(key)
        if value is None or value == "":
            continue
        value = str(value).strip()
        if not _ID.fullmatch(value):
            raise DoubanError("豆瓣标识符必须是完整的数字条目 ID，请先修正该书的标识符。")
        found.add(value)
    if len(found) > 1:
        raise DoubanError("该书的 douban 与 new_douban 标识符冲突，请先确认正确版本。")
    return next(iter(found), None)


def _text(element):
    """Preserve meaningful line breaks without carrying HTML into a column."""
    def walk(node):
        if node.tag in ("script", "style"):
            return ""
        result = node.text or ""
        for child in node:
            if child.tag == "br":
                result += "\n"
            else:
                result += walk(child)
                if child.tag in ("div", "p", "li"):
                    result += "\n"
            result += child.tail or ""
        return result
    value = walk(element).replace("\r\n", "\n").replace("\r", "\n")
    value = "\n".join(re.sub(r"[\t\f\v ]+", " ", line).strip()
                      for line in value.split("\n"))
    return re.sub(r"\n{3,}", "\n\n", value).strip()


def _document(page):
    if not isinstance(page, (str, bytes)) or not page.strip():
        raise DoubanError("豆瓣返回空页面，本次未导入任何数据。")
    try:
        parser = lxml_html.HTMLParser(no_network=True)
        doc = lxml_html.fromstring(page, parser=parser)
    except (ValueError, TypeError, lxml_html.etree.ParserError):
        raise DoubanError("无法解析豆瓣页面，本次未导入任何数据。") from None
    title = " ".join(doc.xpath("//title/text()"))
    if re.search(r"安全验证|人机验证|验证码|captcha", title, re.I):
        raise AccessBlocked("豆瓣要求安全验证，请在登录窗口完成验证后重试。")
    if re.search(r"禁止访问|访问受限|403\s*Forbidden|请求过于频繁", title, re.I):
        raise AccessBlocked("豆瓣暂时限制访问，请稍后再试。")
    if re.search(r"登录豆瓣|豆瓣\s*[-—]\s*登录", title):
        raise LoginRequired("豆瓣登录已失效，请重新登录。")
    for action in doc.xpath("//form/@action"):
        parsed = urlsplit(urljoin("https://www.douban.com/", action))
        if parsed.hostname == "sec.douban.com":
            raise AccessBlocked("豆瓣要求安全验证，请在登录窗口完成验证后重试。")
        if parsed.hostname == "accounts.douban.com" and "login" in parsed.path:
            raise LoginRequired("豆瓣登录已失效，请重新登录。")
    return doc


def _person_from_url(value):
    parsed = urlsplit(urljoin("https://www.douban.com/", value))
    if parsed.scheme not in ("http", "https") or parsed.hostname not in (
        "www.douban.com", "book.douban.com", "douban.com"
    ) or parsed.username or parsed.password:
        return None
    match = _PERSON.fullmatch(parsed.path)
    return match.group(1) if match else None


def _require_nav(doc, expected_account_id=None):
    navs = doc.xpath("//*[%s]" % (_CLASS % "nav-user-account"))
    if not navs:
        raise LoginRequired("未检测到有效的豆瓣登录，请重新登录后再读取个人记录。")
    ids = {_person_from_url(url) for nav in navs for url in nav.xpath(".//a/@href")}
    ids.discard(None)
    if len(ids) > 1 or (expected_account_id and ids and ids != {expected_account_id}):
        raise DoubanError("豆瓣页面中的登录账号发生变化，请重新验证账号。")
    return ids


def parse_account(page, final_url):
    """Parse the response to GET /mine/; public arbitrary profiles are not inputs."""
    parsed = urlsplit(final_url)
    if parsed.scheme != "https" or parsed.hostname != "www.douban.com" or parsed.username:
        raise LoginRequired("豆瓣登录未完成，请重新登录。")
    if parsed.path not in ("/mine", "/mine/") and not _PERSON.fullmatch(parsed.path):
        raise LoginRequired("豆瓣登录未完成，请重新登录。")
    doc = _document(page)
    nav_ids = _require_nav(doc)
    links = doc.xpath("//*[@id='db-usr-profile']/*[%s]/a/@href" % (_CLASS % "pic"))
    ids = {_person_from_url(url) for url in links}
    ids.discard(None)
    if len(ids) != 1:
        raise LoginRequired("无法核对豆瓣账号，请重新登录。")
    user_id = next(iter(ids))
    final_person = _person_from_url(final_url)
    if (final_person and final_person != user_id) or (nav_ids and nav_ids != {user_id}):
        raise DoubanError("豆瓣账号信息不一致，请重新登录。")
    names = doc.xpath("//*[@id='db-usr-profile']//h1")
    display_name = _text(names[0]) if names else " ".join(doc.xpath("//title/text()")).strip()
    return Account(user_id, display_name or user_id)


def _subject_from_url(value):
    parsed = urlsplit(urljoin("https://book.douban.com/", value))
    if parsed.scheme not in ("http", "https") or parsed.hostname != "book.douban.com":
        return None
    match = _SUBJECT.fullmatch(parsed.path)
    return match.group(1) if match else None


def _require_subject(doc, subject_id):
    urls = doc.xpath("//meta[@property='og:url']/@content | //link[@rel='canonical']/@href")
    if not urls:
        for raw in doc.xpath("//script[@type='application/ld+json']/text()"):
            try:
                data = json.loads(raw)
                if isinstance(data, dict) and isinstance(data.get("url"), str):
                    urls.append(data["url"])
            except (ValueError, TypeError):
                pass
    if not urls or any(_subject_from_url(url) != subject_id for url in urls):
        raise DoubanError("无法确认返回页面属于当前图书，请核对豆瓣条目 ID。")


def _status(scope):
    nodes = scope.xpath(".//*[%s]/*[%s] | .//*[@data-field='status']" %
                        (_CLASS % "a_stars", _CLASS % "mr10"))
    for node in nodes:
        value = (node.get("data-value") or _text(node)).strip()
        if value in _STATUS:
            return _STATUS[value]
        match = re.fullmatch(r"我(?:最近)?(想读|在读|读过)这本书", value)
        if match:
            return _STATUS[match.group(1)]
    for value in scope.xpath(".//input[@name='interest'][@checked]/@value"):
        if value in ("wish", "do", "collect"):
            return value
    return None


def _tags(scope):
    inputs = scope.xpath(".//input[@name='tags']")
    if inputs:
        return list(dict.fromkeys((inputs[0].get("value") or "").split()))
    explicit = scope.xpath(".//*[@data-field='tags']")
    if explicit:
        return list(dict.fromkeys(_text(explicit[0]).split()))
    labels = [node for node in scope.xpath(".//span | .//p | .//div")
              if re.match(r"^标签\s*[:：]", _text(node))]
    if not labels:
        return None
    label = min(labels, key=lambda node: len(_text(node)))
    value = re.sub(r"^标签\s*[:：]\s*", "", _text(label))
    if not value:
        value = (label.tail or "").strip()
        if not value:
            parts = []
            for sibling in label.itersiblings():
                # Only a link group or a single adjacent span can be tag
                # values. Continuing through arbitrary spans can consume a
                # short comment that happens to follow the tag display.
                if sibling.tag not in ("a", "span"):
                    break
                if sibling.get("data-field") == "comment" or any(
                    part.startswith("comment") for part in (sibling.get("class") or "").split()
                ):
                    break
                parts.append(_text(sibling))
                if sibling.tag == "span":
                    break
            value = " ".join(parts).strip()
    return list(dict.fromkeys(value.split()))


def _comment(scope, tags):
    expressions = (
        ".//textarea[@name='comment']",
        ".//*[@data-field='comment']",
        ".//*[%s]" % (_CLASS % "comment-text"),
        ".//*[%s]" % (_CLASS % "comment-content"),
    )
    for expression in expressions:
        nodes = scope.xpath(expression)
        if nodes:
            return _text(nodes[0])
    # Classic pages render the short comment as an unlabelled span beside the
    # status/date/tag metadata. Only accept a unique plain candidate in that
    # small region; a changed/ambiguous layout leaves the field unrecognized.
    candidates = []
    for node in scope.xpath("./div/span | ./span"):
        if len(node) or "mr10" in (node.get("class") or "").split():
            continue
        value = _text(node)
        if not value or re.match(r"^标签\s*[:：]", value):
            continue
        if re.fullmatch(r"\d{4}-\d{1,2}-\d{1,2}|\d+(?:\.\d+)?", value):
            continue
        if value in ("想读", "在读", "读过", "评价:", "评价：", "我的评价:", "我的评价：",
                     "修改", "删除", "评分", "暂无评价", "很差", "较差", "还行", "推荐", "力荐"):
            continue
        if tags and all(part in tags for part in value.split()):
            continue
        if re.search(r"rating[0-5]|allstar", node.get("class") or ""):
            continue
        candidates.append(value)
    candidates = list(dict.fromkeys(candidates))
    return candidates[0] if len(candidates) == 1 else None


def _rating(doc, scope):
    inputs = scope.xpath(".//input[@id='n_rating' or @name='rating']")
    # Douban's own rating control can be outside the displayed collection
    # section (e.g. its edit dialog). The prior importer reads this exact ID.
    # This helper is called only after authentication, subject identity and a
    # confirmed personal status have been checked. Generic rating inputs
    # elsewhere on the page are not candidates.
    explicit = doc.xpath("//input[@id='n_rating']")
    if len(explicit) > 1:
        return None
    for node in explicit:
        if node not in inputs:
            inputs.append(node)
    if inputs:
        values = [node.get("value", "") for node in inputs]
        if any(not re.fullmatch(r"[0-5]", value) for value in values):
            return None
        return int(values[0]) if len(set(values)) == 1 else None
    stars = []
    for classes in scope.xpath(".//@class"):
        match = re.search(r"(?:^|\s)(?:rating([1-5])-t|allstar([1-5])0)(?:\s|$)", classes)
        if match:
            stars.append(int(match.group(1) or match.group(2)))
    return stars[0] if len(set(stars)) == 1 else None


def parse_personal_record(page, subject_id, account_id):
    subject_id = str(subject_id)
    if not _ID.fullmatch(subject_id):
        raise DoubanError("豆瓣条目 ID 无效。")
    doc = _document(page)
    _require_subject(doc, subject_id)
    _require_nav(doc, str(account_id))
    scopes = doc.xpath("//*[@id='interest_sect_level' or @id='interest_section' or %s]" %
                       (_CLASS % "collection-section"))
    selected = [(scope, _status(scope)) for scope in scopes]
    selected = [(scope, status) for scope, status in selected if status]
    if not selected:
        raise NoRecord("未读到该书的个人收藏记录；保留本地数据。")
    if len({status for _, status in selected}) != 1:
        raise DoubanError("豆瓣个人阅读状态不一致，本次未导入该页面。")
    scope, status = selected[0]
    values = {"status": status}
    rating = _rating(doc, scope)
    if rating is not None:
        values["rating"] = rating
    tags = _tags(scope)
    if tags is not None:
        values["tags"] = tags
    comment = _comment(scope, tags)
    if comment is not None:
        values["comment"] = comment
    return PersonalRecord(subject_id, str(account_id), values)

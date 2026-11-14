"""openBD's ISBN-specific Japanese book records; not a title search provider."""
from urllib.parse import quote
from ..models import Record, isbn, clean

BASE = 'https://api.openbd.jp/v1/get?isbn='


def _onix_text(value):
    if isinstance(value, dict):
        return clean(value.get('content') or value.get('value') or '')
    return clean(value)


def parse_detail(data, requested):
    requested = isbn(requested)
    if not requested or not isinstance(data, list) or len(data) != 1 or not isinstance(data[0], dict):
        return None
    entry = data[0]
    summary = entry.get('summary') or {}
    if not isinstance(summary, dict) or isbn(summary.get('isbn')) != requested:
        return None
    onix = entry.get('onix') or {}
    descriptive = onix.get('DescriptiveDetail') or {}
    contributors = descriptive.get('Contributor') or []
    if isinstance(contributors, dict):
        contributors = [contributors]
    authors, illustrators, translators = [], [], []
    for member in contributors:
        if not isinstance(member, dict):
            continue
        name = _onix_text(member.get('PersonName', '')) or clean(member.get('CorporateName'))
        roles = member.get('ContributorRole', [])
        roles = roles if isinstance(roles, list) else [roles]
        roles = [str(role.get('value', '')) if isinstance(role, dict) else str(role) for role in roles]
        if not name:
            continue
        if 'A01' in roles:
            authors.append(name)
        if 'A12' in roles:
            illustrators.append(name)
        if 'B06' in roles:
            translators.append(name)
    if not authors and summary.get('author'):
        # Onix-less records sometimes only provide an author line; don't confuse illustrators with authors.
        authors = [clean(summary['author'])]
    title = clean(summary.get('title'))
    if not title:
        return None
    detail = onix.get('CollateralDetail') or {}
    text_contents = detail.get('TextContent') or []
    text_contents = text_contents if isinstance(text_contents, list) else [text_contents]
    blurb = ''
    for item in text_contents:
        if isinstance(item, dict) and str(item.get('TextType')) in ('02', '03') and _onix_text(item.get('Text')):
            blurb = _onix_text(item.get('Text'))
            break
    series = clean(summary.get('series'))
    return Record('openbd', requested, title, authors, requested, publisher=clean(summary.get('publisher')),
                  pubdate=clean(summary.get('pubdate')), date_text=clean(summary.get('pubdate')),
                  language='jpn', description=blurb, cover=clean(summary.get('cover')),
                  illustrators=illustrators, translators=translators, series=series,
                  source_labels=['openbd'])


def detail(client, isbn_value):
    code = isbn(isbn_value)
    if not code:
        raise ValueError('openBD 需要有效 ISBN。')
    # The endpoint returns a one-element JSON list; ISBN identity must match.
    result = parse_detail(client.json(BASE + quote(code)), code)
    if result is None:
        raise ValueError('openBD 未收录这个 ISBN 或返回的 ISBN 不一致。')
    return result

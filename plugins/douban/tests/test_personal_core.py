"""Parsing fixtures are synthetic; no authenticated personal data is stored."""
import importlib
from pathlib import Path
import sys
import types
import unittest

PACKAGE = "douban_personal_backend_tests"
if PACKAGE not in sys.modules:
    package = types.ModuleType(PACKAGE)
    package.__path__ = [str(Path(__file__).resolve().parents[1] / "personal")]
    sys.modules[PACKAGE] = package
core = importlib.import_module(PACKAGE + ".core")


def page(section="", subject="1234567", account="reader", nav=True, extra=""):
    user = ('<div class="nav-user-account"><a href="https://www.douban.com/people/%s/">我</a></div>'
            % account) if nav else ""
    return ('<html><head><meta charset="utf-8"><meta property="og:url" '
            'content="https://book.douban.com/subject/%s/"></head><body>%s%s%s</body></html>'
            % (subject, user, section, extra))


def section(extra="", status="读过"):
    return ('<div id="interest_sect_level"><div class="a_stars">'
            '<span class="mr10">%s</span><span>2026-11-10</span>%s</div></div>'
            % (status, extra))


class PersonalCoreTests(unittest.TestCase):
    def test_all_fields_and_community_fields_stay_separate(self):
        html = page(section('<input id="n_rating" value="4">'
                            '<span>标签：文学 中国</span>'
                            '<textarea name="comment">第一行\n第二行 &amp; 后记</textarea>'),
                    extra='<strong property="v:average">9.9</strong>'
                          '<div class="tags">其他人标签</div>'
                          '<div class="comment-item"><span class="short">他人短评</span></div>')
        record = core.parse_personal_record(html, "1234567", "reader")
        self.assertEqual(record.values, {"status": "collect", "rating": 4,
                                         "tags": ["文学", "中国"],
                                         "comment": "第一行\n第二行 & 后记"})

    def test_missing_fields_are_omitted_not_cleared(self):
        record = core.parse_personal_record(page(section()), "1234567", "reader")
        self.assertEqual(record.values, {"status": "collect"})

    def test_explicit_empty_fields_remain_distinguishable(self):
        record = core.parse_personal_record(page(section(
            '<input id="n_rating" value="0"><input name="tags" value="">'
            '<textarea name="comment"></textarea>')), "1234567", "reader")
        self.assertEqual(record.values, {"status": "collect", "rating": 0,
                                         "tags": [], "comment": ""})

    def test_subject_and_account_mismatch_fail(self):
        for html in (page(section(), subject="7654321"),
                     page(section(), account="someone_else")):
            with self.assertRaises(core.DoubanError):
                core.parse_personal_record(html, "1234567", "reader")

    def test_unverified_and_uncollected_are_not_empty_records(self):
        with self.assertRaises(core.LoginRequired):
            core.parse_personal_record(page(section(), nav=False), "1234567", "reader")
        with self.assertRaises(core.NoRecord):
            core.parse_personal_record(page(), "1234567", "reader")
        with self.assertRaises(core.NoRecord):
            core.parse_personal_record(page('<div id="interest_sect_level">'
                '<input id="n_rating" value="0"><a>想读</a><a>读过</a></div>'),
                "1234567", "reader")

    def test_short_comment_keeps_breaks_and_literal_markup_as_text(self):
        record = core.parse_personal_record(page(section(
            '<div class="comment-text">甲<br>乙 &lt;b&gt;原样&lt;/b&gt;</div>')),
            "1234567", "reader")
        self.assertEqual(record.values["comment"], "甲\n乙 <b>原样</b>")

    def test_legacy_comment_is_unique_and_not_tag_rating_or_date(self):
        html = page(section('<span>标签: one two</span><span class="rating4-t">力荐</span>'
                            '<span>自己的旧版短评。</span>'))
        record = core.parse_personal_record(html, "1234567", "reader")
        self.assertEqual(record.values["comment"], "自己的旧版短评。")
        self.assertEqual(record.values["rating"], 4)
        ambiguous = page(section('<span>不认识的控件</span><span>另一个不认识的控件</span>'))
        self.assertNotIn("comment", core.parse_personal_record(ambiguous, "1234567", "reader").values)

    def test_separate_tag_label_does_not_swallow_following_comment(self):
        html = page(section('<span>标签:</span><span>one two</span>'
                            '<span>这是短评。</span>'))
        record = core.parse_personal_record(html, "1234567", "reader")
        self.assertEqual(record.values["tags"], ["one", "two"])
        self.assertEqual(record.values["comment"], "这是短评。")

    def test_bad_rating_never_becomes_public_rating(self):
        html = page(section('<input id="n_rating" value="9.5">'),
                    extra='<strong property="v:average">8.5</strong>')
        self.assertNotIn("rating", core.parse_personal_record(html, "1234567", "reader").values)

    def test_explicit_external_own_rating_requires_confirmed_collection_and_auth(self):
        outside = '<div id="interest-form"><input id="n_rating" value="4"></div>'
        html = page(section(), extra=outside)
        self.assertEqual(core.parse_personal_record(html, "1234567", "reader").values["rating"], 4)
        with self.assertRaises(core.NoRecord):
            core.parse_personal_record(page(extra=outside), "1234567", "reader")
        with self.assertRaises(core.LoginRequired):
            core.parse_personal_record(page(section(), nav=False, extra=outside), "1234567", "reader")
        generic = page(section(), extra='<input name="rating" value="5"><strong property="v:average">9.8</strong>')
        self.assertNotIn("rating", core.parse_personal_record(generic, "1234567", "reader").values)

    def test_conflicting_or_duplicate_rating_inputs_are_unknown(self):
        fixtures = (
            page(section('<input id="n_rating" value="4">'),
                 extra='<input id="n_rating" value="5">'),
            page(section('<input name="rating" value="4">'),
                 extra='<input id="n_rating" value="5">'),
            page(section('<input name="rating" value="4"><input name="rating" value="3">')),
            page(section(), extra='<input id="n_rating" value="4"><input id="n_rating" value="4">'),
        )
        for html in fixtures:
            self.assertNotIn("rating", core.parse_personal_record(html, "1234567", "reader").values)

    def test_exact_identifiers_and_conflict(self):
        self.assertIsNone(core.subject_id_from_identifiers({"isbn": "1234567"}))
        self.assertEqual(core.subject_id_from_identifiers({"new_douban": "1234567"}), "1234567")
        self.assertEqual(core.subject_id_from_identifiers({"douban": "1234567", "new_douban": "1234567"}), "1234567")
        for identifiers in ({"douban": "https://book.douban.com/subject/1234567/"},
                            {"douban": "1234567", "new_douban": "7654321"},
                            {"douban": "0123"}, {"douban": "../123"}):
            with self.assertRaises(core.DoubanError):
                core.subject_id_from_identifiers(identifiers)

    def test_account_requires_authenticated_own_profile(self):
        html = page(extra='<div id="db-usr-profile"><div class="pic">'
                          '<a href="https://www.douban.com/people/reader/"></a>'
                          '</div><h1>读者</h1></div>')
        self.assertEqual(core.parse_account(html, "https://www.douban.com/mine/"),
                         core.Account("reader", "读者"))
        with self.assertRaises(core.DoubanError):
            core.parse_account(html, "https://www.douban.com/people/other/")
        with self.assertRaises(core.LoginRequired):
            core.parse_account(html, "https://accounts.douban.com/passport/login")
        with self.assertRaises(core.LoginRequired):
            core.parse_account(page(nav=False), "https://www.douban.com/mine/")

    def test_login_challenge_and_forbidden_are_failures(self):
        for title, cls in (("登录豆瓣", core.LoginRequired),
                           ("安全验证", core.AccessBlocked),
                           ("禁止访问", core.AccessBlocked)):
            with self.assertRaises(cls):
                core.parse_personal_record('<html><title>%s</title></html>' % title,
                                           "1234567", "reader")


if __name__ == "__main__":
    unittest.main()

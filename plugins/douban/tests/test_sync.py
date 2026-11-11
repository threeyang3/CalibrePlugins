import importlib.util
import sys
import unittest
from copy import deepcopy
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "personal" / "sync.py"
SPEC = importlib.util.spec_from_file_location("douban_sync_under_test", MODULE_PATH)
sync = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = sync
SPEC.loader.exec_module(sync)


class SyncPlanningTests(unittest.TestCase):
    def plan(self, current=None, previous=None, incoming=None, **identity):
        rows = sync.build_plan(
            7,
            identity.get("book_uuid", "book-uuid"),
            identity.get("account_id", "alice"),
            identity.get("subject_id", "12345"),
            current or {},
            previous,
            incoming or {},
        )
        return {row.key: row for row in rows}

    def snapshot(self, values, **identity):
        return {
            "book_uuid": identity.get("book_uuid", "book-uuid"),
            "account_id": identity.get("account_id", "alice"),
            "subject_id": identity.get("subject_id", "12345"),
            "values": values,
        }

    def test_first_import_maps_each_field_to_a_dedicated_column(self):
        rows = self.plan(incoming={
            "tags": ["文学", " 中国 ", "文学"],
            "rating": 4,
            "status": "collect",
            "comment": "第一次读。\n想再读一遍。",
        })
        self.assertTrue(all(row.allowed for row in rows.values()))
        self.assertEqual(rows["tags"].after, ["文学", "中国"])
        self.assertEqual(rows["rating"].after, 8)
        self.assertEqual(rows["status"].after, "读过")
        self.assertEqual(rows["comment"].after, "<p>第一次读。<br />想再读一遍。</p>")
        self.assertTrue(all(row.column.startswith("#douban_") for row in rows.values()))
        self.assertNotIn("comments", {row.column for row in rows.values()})

    def test_first_import_does_not_overwrite_existing_personal_data(self):
        rows = self.plan(
            current={"tags": ("自己整理",), "rating": 10, "status": "重读中", "comment": "<p>我的笔记</p>"},
            incoming={"tags": ["小说"], "rating": 3, "status": "do", "comment": "豆瓣简评"},
        )
        self.assertFalse(any(row.allowed for row in rows.values()))
        self.assertTrue(all("本地已有" in row.reason for row in rows.values()))

    def test_matching_existing_data_is_not_silently_claimed(self):
        rows = self.plan(current={"rating": 8}, incoming={"rating": 4})
        self.assertFalse(rows["rating"].allowed)
        self.assertIn("本地已有", rows["rating"].reason)

    def test_remote_update_only_changes_values_still_owned_by_importer(self):
        previous = self.snapshot({"rating": 6, "status": "在读"})
        rows = self.plan(
            current={"rating": 6, "status": "已弃读"},
            previous=previous,
            incoming={"rating": 5, "status": "collect"},
        )
        self.assertTrue(rows["rating"].allowed)
        self.assertEqual(rows["rating"].after, 10)
        self.assertFalse(rows["status"].allowed)
        self.assertIn("手动", rows["status"].reason)

    def test_manual_clear_is_not_refilled_on_later_sync(self):
        previous = self.snapshot({"tags": ["小说"], "rating": 8, "status": "在读", "comment": "<p>旧简评</p>"})
        rows = self.plan(
            current={"tags": (), "rating": 0, "status": None, "comment": ""},
            previous=previous,
            incoming={"tags": ["小说"], "rating": 4, "status": "do", "comment": "新简评"},
        )
        self.assertFalse(any(row.allowed for row in rows.values()))
        self.assertTrue(all("手动" in row.reason for row in rows.values()))

    def test_empty_remote_fields_never_clear_existing_values(self):
        current = {"tags": ["小说"], "rating": 8, "status": "在读", "comment": "<p>简评</p>"}
        rows = self.plan(current, self.snapshot(deepcopy(current)), {
            "tags": [], "rating": 0, "status": "", "comment": " \n",
        })
        self.assertFalse(any(row.allowed for row in rows.values()))
        self.assertTrue(all("来源为空" in row.reason for row in rows.values()))

    def test_missing_and_none_are_distinct_but_both_preserve_local_values(self):
        rows = self.plan(current={"rating": 8}, incoming={"rating": None})
        self.assertIn("来源为空", rows["rating"].reason)
        self.assertIn("来源未提供", rows["tags"].reason)
        self.assertFalse(any(row.allowed for row in rows.values()))

    def test_identity_switch_blocks_even_an_empty_field(self):
        for identity in (
            {"account_id": "bob"}, {"subject_id": "99999"}, {"book_uuid": "new-book-uuid"},
        ):
            with self.subTest(identity=identity):
                rows = self.plan(
                    current={"rating": 0}, previous=self.snapshot({"rating": 0}),
                    incoming={"rating": 5}, **identity,
                )
                self.assertFalse(rows["rating"].allowed)
                self.assertIn("上次导入不同", rows["rating"].reason)

    def test_repeated_import_is_unchanged_despite_tag_order_and_container(self):
        previous = self.snapshot({"tags": ["中国", "文学"], "rating": 8})
        rows = self.plan(
            current={"tags": ("文学", "中国"), "rating": 8},
            previous=previous,
            incoming={"tags": ["中国", "文学"], "rating": 4},
        )
        self.assertEqual(rows["tags"].reason, "未变化")
        self.assertEqual(rows["rating"].reason, "未变化")
        self.assertFalse(any(row.allowed for row in rows.values()))

    def test_short_comment_is_text_not_executable_html(self):
        row = self.plan(incoming={"comment": '<script>alert("x")</script> & <img src=x>\r\n下一行'})["comment"]
        self.assertTrue(row.allowed)
        self.assertEqual(row.after, '<p>&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt; &amp; &lt;img src=x&gt;<br />下一行</p>')
        self.assertNotIn("<script", row.after)
        self.assertNotIn("<img", row.after)

    def test_unrecognized_input_is_skipped_without_coercion(self):
        bad = {
            "tags": "one,two",
            "rating": True,
            "status": "读过",
            "comment": {"text": "content"},
        }
        rows = self.plan(incoming=bad)
        self.assertFalse(any(row.allowed for row in rows.values()))
        self.assertTrue(all("格式无法识别" in row.reason for row in rows.values()))
        for invalid in (-1, 6, 4.5, "4"):
            with self.subTest(invalid=invalid):
                self.assertFalse(self.plan(incoming={"rating": invalid})["rating"].allowed)

    def test_planning_does_not_mutate_source_or_snapshots(self):
        current = {"tags": ["old"], "rating": 8}
        previous = self.snapshot(deepcopy(current))
        incoming = {"tags": ["new", "new"], "rating": 5}
        before = deepcopy((current, previous, incoming))
        self.plan(current, previous, incoming)
        self.assertEqual((current, previous, incoming), before)

    def test_malformed_historical_identity_never_authorizes_a_write(self):
        for previous in ({"values": {}}, {"values": []}, []):
            with self.subTest(previous=previous):
                self.assertFalse(self.plan(previous=previous, incoming={"rating": 4})["rating"].allowed)

    def test_value_equality_supports_write_time_checks(self):
        self.assertTrue(sync.values_equal("rating", None, 0))
        self.assertTrue(sync.values_equal("tags", ("a", "b"), ["b", "a"]))
        self.assertFalse(sync.values_equal("tags", ("A",), ["a"]))
        self.assertFalse(sync.values_equal("comment", "<p>text</p>", "text"))


if __name__ == "__main__":
    unittest.main()

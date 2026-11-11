"""Exercise the database adapter against a small new_api protocol fake.

These tests validate adapter behavior; they do not emulate or claim a real
Calibre installation or its GUI/custom-column creation behavior.
"""

import importlib
import sys
import types
import unittest
from copy import deepcopy
from dataclasses import replace
from pathlib import Path


PACKAGE = "douban_storage_under_test"
package = types.ModuleType(PACKAGE)
package.__path__ = [str(Path(__file__).resolve().parents[1] / "personal")]
sys.modules[PACKAGE] = package
storage = importlib.import_module(PACKAGE + ".storage")
sync = importlib.import_module(PACKAGE + ".sync")
core = importlib.import_module(PACKAGE + ".core")


class FakeDB:
    def __init__(self):
        self.library_id = "library-a"
        self.books = {1: {
            "uuid": "book-uuid", "title": "示例图书",
            "identifiers": {"new_douban": "12345"},
        }}
        self.field_metadata = {
            spec["column"]: dict(spec) for spec in sync.FIELD_SPECS.values()
        }
        self.receipts = {}
        self.writes = []
        self.saved_receipts = []
        self.fail_column = None
        self.fail_receipt = False
        self.on_write = None

    def field_for(self, name, book_id):
        return deepcopy(self.books.get(book_id, {}).get(name))

    def get_custom_book_data(self, name, book_ids):
        assert name == storage.RECEIPT_KEY
        return {book_id: deepcopy(self.receipts[book_id])
                for book_id in book_ids if book_id in self.receipts}

    def set_field(self, name, val_map, allow_case_change=False):
        if name == self.fail_column:
            raise RuntimeError("private path or content must not reach the user")
        self.writes.append((name, deepcopy(val_map), allow_case_change))
        for book_id, value in val_map.items():
            if name == "#douban_my_tags":
                value = tuple(sorted(value))
            self.books[book_id][name] = deepcopy(value)
        if self.on_write:
            self.on_write()

    def add_custom_book_data(self, name, val_map):
        assert name == storage.RECEIPT_KEY
        if self.fail_receipt:
            raise RuntimeError("receipt failure with private details")
        self.receipts.update(deepcopy(val_map))
        self.saved_receipts.append(deepcopy(val_map))


class StorageTests(unittest.TestCase):
    def preview(self, db, values=None):
        values = values or {"tags": ["文学", "中国"], "rating": 4,
                            "status": "collect", "comment": "我的简评"}
        targets, skipped = storage.capture_targets(db, [1])
        self.assertFalse(skipped)
        target = targets[0]
        record = core.PersonalRecord(target.subject_id, "alice", deepcopy(values))
        rows = sync.build_plan(target.book_id, target.book_uuid, record.account_id,
                               target.subject_id, target.current, target.previous,
                               record.values)
        return target, record, {row.key: row for row in rows}

    def apply(self, db, selected, get_current_db=None, account_id="alice"):
        return storage.apply_selected(db, "library-a", get_current_db or (lambda: db),
                                      account_id, selected)

    def test_capture_skips_unlinked_or_conflicting_books_and_copies_receipts(self):
        db = FakeDB()
        db.books[2] = {"title": "未匹配", "uuid": "second", "identifiers": {}}
        db.books[3] = {"title": "冲突", "uuid": "third",
                       "identifiers": {"douban": "123", "new_douban": "456"}}
        db.receipts[1] = {"values": {"rating": 8}}
        targets, skipped = storage.capture_targets(db, [1, 2, 3])
        self.assertEqual([target.book_id for target in targets], [1])
        self.assertEqual(len(skipped), 2)
        db.receipts[1]["values"]["rating"] = 10
        self.assertEqual(targets[0].previous["values"]["rating"], 8)

    def test_column_compatibility_reports_missing_and_wrong_types(self):
        db = FakeDB()
        self.assertEqual(storage.compatible_columns(db), ([], []))
        del db.field_metadata["#douban_my_comment"]
        db.field_metadata["#douban_my_rating"]["datatype"] = "text"
        db.field_metadata["#douban_my_tags"]["is_multiple"] = False
        missing, incompatible = storage.compatible_columns(db)
        self.assertEqual(missing, ["#douban_my_comment"])
        self.assertEqual(set(incompatible), {"#douban_my_tags", "#douban_my_rating"})

    def test_only_selected_allowed_rows_write_and_public_fields_remain_untouched(self):
        db = FakeDB()
        db.books[1].update({"#douban_my_rating": 10, "comments": "内容简介", "rating": 6})
        target, record, rows = self.preview(db)
        written, skipped, error = self.apply(db, [
            (target, rows["tags"], record), (target, rows["rating"], record),
        ])
        self.assertEqual(written, [(1, "tags")])
        self.assertEqual(len(skipped), 1)
        self.assertIsNone(error)
        self.assertIsNone(db.field_for("#douban_read_status", 1))
        self.assertEqual(db.books[1]["#douban_my_rating"], 10)
        self.assertEqual(db.books[1]["comments"], "内容简介")
        self.assertEqual(db.books[1]["rating"], 6)
        self.assertEqual(set(db.receipts[1]["values"]), {"tags"})

    def test_preview_row_cannot_redirect_a_write_to_public_comments(self):
        db = FakeDB()
        target, record, rows = self.preview(db)
        forged = replace(rows["comment"], column="comments")
        written, skipped, error = self.apply(db, [(target, forged, record)])
        self.assertFalse(written)
        self.assertEqual(len(skipped), 1)
        self.assertFalse(db.writes)
        self.assertIsNone(error)

    def test_record_account_and_subject_are_bound_to_preview(self):
        for account_id, subject_id in (("bob", "12345"), ("alice", "99999")):
            with self.subTest(account=account_id, subject=subject_id):
                db = FakeDB()
                target, record, rows = self.preview(db)
                record = replace(record, account_id=account_id, subject_id=subject_id)
                written, skipped, error = self.apply(db, [(target, rows["rating"], record)])
                self.assertFalse(written)
                self.assertEqual(len(skipped), 1)
                self.assertIsNone(error)

    def test_changed_book_uuid_or_edition_prevents_writing(self):
        for field, replacement in (("uuid", "different-book"), ("identifiers", {"douban": "99999"})):
            with self.subTest(field=field):
                db = FakeDB()
                target, record, rows = self.preview(db)
                db.books[1][field] = replacement
                written, skipped, error = self.apply(db, [(target, rows["rating"], record)])
                self.assertFalse(written)
                self.assertEqual(len(skipped), 1)
                self.assertIsNone(error)

    def test_library_switch_before_or_between_writes_stops_remaining_rows(self):
        db = FakeDB()
        target, record, rows = self.preview(db)
        selected = [(target, rows["tags"], record), (target, rows["rating"], record)]
        written, _, error = self.apply(db, selected, get_current_db=lambda: FakeDB())
        self.assertFalse(written)
        self.assertIn("书库已切换", error)

        current = [db]
        db.on_write = lambda: current.__setitem__(0, FakeDB())
        written, _, error = self.apply(db, selected, get_current_db=lambda: current[0])
        self.assertEqual(written, [(1, "tags")])
        self.assertIn("书库已切换", error)
        self.assertIsNone(db.field_for("#douban_my_rating", 1))
        self.assertEqual(set(db.receipts[1]["values"]), {"tags"})

    def test_edits_after_preview_are_preserved_while_other_selected_fields_apply(self):
        db = FakeDB()
        target, record, rows = self.preview(db)
        db.books[1]["#douban_my_tags"] = ("本地补充",)
        written, skipped, error = self.apply(db, [
            (target, rows["tags"], record), (target, rows["rating"], record),
        ])
        self.assertEqual(written, [(1, "rating")])
        self.assertEqual(len(skipped), 1)
        self.assertIsNone(error)
        self.assertEqual(db.books[1]["#douban_my_tags"], ("本地补充",))

    def test_receipt_is_rechecked_after_preview_for_account_ownership(self):
        db = FakeDB()
        target, record, rows = self.preview(db)
        db.receipts[1] = {"book_uuid": target.book_uuid, "account_id": "bob",
                          "subject_id": target.subject_id, "values": {}}
        written, skipped, error = self.apply(db, [(target, rows["rating"], record)])
        self.assertFalse(written)
        self.assertEqual(len(skipped), 1)
        self.assertIsNone(error)

    def test_source_value_changes_after_preview_require_a_new_preview(self):
        db = FakeDB()
        target, record, rows = self.preview(db)
        record.values["rating"] = 5
        written, skipped, error = self.apply(db, [(target, rows["rating"], record)])
        self.assertFalse(written)
        self.assertIn("来源的值已改变", skipped[0][1])
        self.assertIsNone(error)

    def test_receipts_accumulate_each_fields_actual_readback_and_repeat_is_noop(self):
        db = FakeDB()
        target, record, rows = self.preview(db)
        written, skipped, error = self.apply(db, [(target, row, record) for row in rows.values()])
        self.assertEqual(len(written), 4)
        self.assertFalse(skipped)
        self.assertIsNone(error)
        self.assertEqual(len(db.saved_receipts), 4)
        self.assertEqual(db.receipts[1]["values"], storage.read_values(db, 1))
        self.assertIsInstance(db.receipts[1]["values"]["tags"], tuple)
        self.assertEqual(db.receipts[1]["account_id"], "alice")
        _, _, repeat_rows = self.preview(db)
        self.assertTrue(all(row.reason == "未变化" for row in repeat_rows.values()))

    def test_partial_write_failure_keeps_prior_writes_and_receipts_without_leaking_error(self):
        db = FakeDB()
        target, record, rows = self.preview(db)
        db.fail_column = "#douban_my_rating"
        written, skipped, error = self.apply(db, [(target, row, record) for row in rows.values()])
        self.assertEqual(written, [(1, "tags")])
        self.assertFalse(skipped)
        self.assertIn("未能全部完成", error)
        self.assertNotIn("private", error)
        self.assertEqual(set(db.receipts[1]["values"]), {"tags"})
        self.assertIsNone(db.field_for("#douban_read_status", 1))

    def test_receipt_failure_reports_written_field_without_claiming_rollback(self):
        db = FakeDB()
        target, record, rows = self.preview(db)
        db.fail_receipt = True
        written, _, error = self.apply(db, [(target, row, record) for row in rows.values()])
        self.assertEqual(written, [(1, "tags")])
        self.assertIn("已写入的字段保留", error)
        self.assertNotIn("private", error)
        self.assertTrue(db.field_for("#douban_my_tags", 1))
        self.assertFalse(db.receipts)
        self.assertIsNone(db.field_for("#douban_my_rating", 1))


if __name__ == "__main__":
    unittest.main()

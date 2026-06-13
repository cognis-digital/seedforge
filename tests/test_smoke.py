"""Smoke tests for SEEDFORGE. Standard library only, no network."""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from seedforge import TOOL_NAME, TOOL_VERSION, generate, Schema  # noqa: E402
from seedforge.core import SchemaError, verify_integrity  # noqa: E402
from seedforge.cli import main  # noqa: E402


SCHEMA = {
    "tables": {
        "users": {
            "count": 5,
            "fields": {
                "id": {"type": "pk", "start": 1},
                "name": "name",
                "email": "email",
            },
        },
        "posts": {
            "count": 12,
            "fields": {
                "id": {"type": "pk"},
                "author_id": {"type": "ref", "ref": "users.id"},
            },
        },
    }
}


class TestCore(unittest.TestCase):
    def test_meta(self):
        self.assertEqual(TOOL_NAME, "seedforge")
        self.assertTrue(TOOL_VERSION)

    def test_counts(self):
        data = generate(SCHEMA, seed=1)
        self.assertEqual(len(data["users"]), 5)
        self.assertEqual(len(data["posts"]), 12)

    def test_referential_integrity(self):
        data = generate(SCHEMA, seed=7)
        user_ids = {u["id"] for u in data["users"]}
        for p in data["posts"]:
            self.assertIn(p["author_id"], user_ids)
        schema = Schema.from_dict(SCHEMA)
        self.assertEqual(verify_integrity(schema, data), [])

    def test_deterministic(self):
        a = generate(SCHEMA, seed=99)
        b = generate(SCHEMA, seed=99)
        self.assertEqual(a, b)

    def test_seed_changes_data(self):
        a = generate(SCHEMA, seed=1)
        b = generate(SCHEMA, seed=2)
        self.assertNotEqual(a, b)

    def test_pk_unique_and_sequential(self):
        data = generate(SCHEMA, seed=3)
        ids = [u["id"] for u in data["users"]]
        self.assertEqual(ids, [1, 2, 3, 4, 5])
        self.assertEqual(len(set(ids)), len(ids))

    def test_topo_order_parents_first(self):
        schema = Schema.from_dict(SCHEMA)
        order = [t.name for t in schema.topo_order()]
        self.assertLess(order.index("users"), order.index("posts"))

    def test_bad_ref_target_rejected(self):
        bad = {
            "tables": {
                "a": {"count": 1, "fields": {
                    "x": {"type": "ref", "ref": "nope.id"}}},
            }
        }
        with self.assertRaises(SchemaError):
            Schema.from_dict(bad)

    def test_ref_must_target_pk(self):
        bad = {
            "tables": {
                "a": {"count": 2, "fields": {"label": "word"}},
                "b": {"count": 2, "fields": {
                    "r": {"type": "ref", "ref": "a.label"}}},
            }
        }
        with self.assertRaises(SchemaError):
            Schema.from_dict(bad)

    def test_cyclic_fk_rejected(self):
        bad = {
            "tables": {
                "a": {"count": 1, "fields": {
                    "id": {"type": "pk"},
                    "b_id": {"type": "ref", "ref": "b.id"}}},
                "b": {"count": 1, "fields": {
                    "id": {"type": "pk"},
                    "a_id": {"type": "ref", "ref": "a.id"}}},
            }
        }
        with self.assertRaises(SchemaError):
            Schema.from_dict(bad)

    def test_unknown_type_rejected(self):
        with self.assertRaises(SchemaError):
            Schema.from_dict({"tables": {"a": {"count": 1,
                             "fields": {"x": {"type": "bogus"}}}}})


class TestCLI(unittest.TestCase):
    def _write_schema(self):
        fd, path = tempfile.mkstemp(suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(SCHEMA, fh)
        return path

    def test_gen_json_exit_zero(self):
        path = self._write_schema()
        try:
            self.assertEqual(main(["--format", "json", "gen", path]), 0)
        finally:
            os.remove(path)

    def test_verify_exit_zero(self):
        path = self._write_schema()
        try:
            self.assertEqual(main(["--format", "json", "verify", path]), 0)
        finally:
            os.remove(path)

    def test_missing_file_nonzero(self):
        self.assertEqual(main(["gen", "/no/such/schema.json"]), 2)


if __name__ == "__main__":
    unittest.main()

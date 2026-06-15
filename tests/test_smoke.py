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

    def test_malformed_json_nonzero(self):
        """A file that is not valid JSON returns exit 2 without a traceback."""
        fd, path = tempfile.mkstemp(suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write("{not: json")
        try:
            self.assertEqual(main(["gen", path]), 2)
        finally:
            os.remove(path)

    def test_schema_error_nonzero(self):
        """A schema with an unknown field type returns exit 2."""
        bad = {"tables": {"t": {"count": 1, "fields": {"x": {"type": "nope"}}}}}
        fd, path = tempfile.mkstemp(suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(bad, fh)
        try:
            self.assertEqual(main(["gen", path]), 2)
        finally:
            os.remove(path)

    def test_zero_count_table_is_valid(self):
        """A table with count=0 is valid and produces an empty list."""
        schema = {"tables": {"t": {"count": 0, "fields": {"id": "pk"}}}}
        data = generate(schema)
        self.assertEqual(data["t"], [])

    def test_verify_table_output_format(self):
        """Verify subcommand in table format returns exit 0 for valid schema."""
        path = self._write_schema()
        try:
            self.assertEqual(main(["--format", "table", "verify", path]), 0)
        finally:
            os.remove(path)


class TestHardening(unittest.TestCase):
    """Edge cases added during production hardening."""

    def test_int_inverted_range_raises(self):
        """int field with min > max raises SchemaError at generation time."""
        bad = {"tables": {"a": {"count": 1, "fields": {"x": {"type": "int", "min": 100, "max": 5}}}}}
        with self.assertRaises(SchemaError):
            generate(bad)

    def test_float_inverted_range_raises(self):
        """float field with min > max raises SchemaError at generation time."""
        bad = {"tables": {"a": {"count": 1, "fields": {"x": {"type": "float", "min": 50.0, "max": 1.0}}}}}
        with self.assertRaises(SchemaError):
            generate(bad)

    def test_date_inverted_year_range_raises(self):
        """date field with year_min > year_max raises SchemaError."""
        bad = {"tables": {"a": {"count": 1, "fields": {"d": {"type": "date", "year_min": 2030, "year_max": 2020}}}}}
        with self.assertRaises(SchemaError):
            generate(bad)

    def test_count_non_integer_raises(self):
        """Non-integer count raises SchemaError with a clear message."""
        bad = {"tables": {"a": {"count": "lots", "fields": {"x": "int"}}}}
        with self.assertRaises(SchemaError) as ctx:
            Schema.from_dict(bad)
        self.assertIn("count", str(ctx.exception))

    def test_nullable_ref_with_empty_parent(self):
        """nullable ref to a zero-row parent table yields None values, not an error."""
        schema = {
            "tables": {
                "parent": {"count": 0, "fields": {"id": "pk"}},
                "child": {"count": 3, "fields": {
                    "p_id": {"type": "ref", "ref": "parent.id", "nullable": True},
                }},
            }
        }
        data = generate(schema)
        self.assertEqual(len(data["child"]), 3)
        for row in data["child"]:
            self.assertIsNone(row["p_id"])

    def test_cli_int_inverted_range_exit_2(self):
        """CLI returns exit 2 (not a raw traceback) for a schema with inverted int range."""
        bad = {"tables": {"a": {"count": 1, "fields": {"x": {"type": "int", "min": 100, "max": 5}}}}}
        fd, path = tempfile.mkstemp(suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(bad, fh)
        try:
            self.assertEqual(main(["gen", path]), 2)
        finally:
            os.remove(path)

    def test_tool_name_and_version_in_core(self):
        """TOOL_NAME and TOOL_VERSION are defined in core (not just __init__ fallback)."""
        from seedforge.core import TOOL_NAME as CN, TOOL_VERSION as CV
        self.assertEqual(CN, "seedforge")
        self.assertTrue(CV)


if __name__ == "__main__":
    unittest.main()

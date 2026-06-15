"""Core engine for SEEDFORGE.

A Schema is a set of named tables. Each table has a count and a list of
fields. Fields produce values via deterministic generators seeded from a
master seed, so a given (seed, schema) always yields identical data --
critical for reproducible test fixtures.

Referential integrity: a field of type "ref" names a target "table.field"
(which must be a primary key, type "pk"). SEEDFORGE topologically sorts tables
by their FK dependencies, generates parents first, then draws child FK values
from the pool of real parent keys -- so every foreign key resolves.
"""
from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass, field as dc_field
from typing import Any, Callable, Dict, List, Optional

TOOL_NAME = "seedforge"
TOOL_VERSION = "1.7.5"


class SeedForgeError(Exception):
    """Base error."""


class SchemaError(SeedForgeError):
    """Raised when a schema is structurally invalid."""


# --- value generators -------------------------------------------------------

_FIRST = ["Ava", "Liam", "Maya", "Noah", "Ivy", "Eli", "Zoe", "Kai",
         "Nora", "Leo", "Ada", "Finn", "Mira", "Owen", "Lena", "Theo"]
_LAST = ["Stone", "Hart", "Vale", "Reed", "Cole", "Frost", "Wren", "Hale",
        "Snow", "Marsh", "Quinn", "Voss", "Lowe", "Pike", "Rhodes", "Bly"]
_DOMAINS = ["example.com", "test.io", "mail.dev", "demo.net", "sandbox.org"]
_WORDS = ["alpha", "delta", "echo", "flux", "gamma", "halo", "ion", "jet",
         "kilo", "lumen", "nova", "orbit", "pulse", "quartz", "rune"]
_STATUSES = ["active", "pending", "closed", "archived"]


def _gen_pk(rng: random.Random, idx: int, spec: dict) -> int:
    start = int(spec.get("start", 1))
    return start + idx


def _gen_int(rng: random.Random, idx: int, spec: dict) -> int:
    lo = int(spec.get("min", 0))
    hi = int(spec.get("max", 1000))
    if lo > hi:
        raise SchemaError(f"int field 'min' ({lo}) must be <= 'max' ({hi})")
    return rng.randint(lo, hi)


def _gen_float(rng: random.Random, idx: int, spec: dict) -> float:
    lo = float(spec.get("min", 0.0))
    hi = float(spec.get("max", 1000.0))
    nd = int(spec.get("round", 2))
    if lo > hi:
        raise SchemaError(f"float field 'min' ({lo}) must be <= 'max' ({hi})")
    return round(lo + rng.random() * (hi - lo), nd)


def _gen_bool(rng: random.Random, idx: int, spec: dict) -> bool:
    return rng.random() < float(spec.get("true_pct", 0.5))


def _gen_first(rng: random.Random, idx: int, spec: dict) -> str:
    return rng.choice(_FIRST)


def _gen_last(rng: random.Random, idx: int, spec: dict) -> str:
    return rng.choice(_LAST)


def _gen_name(rng: random.Random, idx: int, spec: dict) -> str:
    return f"{rng.choice(_FIRST)} {rng.choice(_LAST)}"


def _gen_email(rng: random.Random, idx: int, spec: dict) -> str:
    user = f"{rng.choice(_FIRST)}.{rng.choice(_LAST)}".lower()
    return f"{user}{rng.randint(1, 999)}@{rng.choice(_DOMAINS)}"


def _gen_word(rng: random.Random, idx: int, spec: dict) -> str:
    n = int(spec.get("words", 1))
    return " ".join(rng.choice(_WORDS) for _ in range(max(1, n)))


def _gen_slug(rng: random.Random, idx: int, spec: dict) -> str:
    return f"{rng.choice(_WORDS)}-{rng.choice(_WORDS)}-{rng.randint(100, 999)}"


def _gen_enum(rng: random.Random, idx: int, spec: dict) -> Any:
    choices = spec.get("choices")
    if not choices:
        raise SchemaError("enum field requires non-empty 'choices'")
    return rng.choice(choices)


def _gen_status(rng: random.Random, idx: int, spec: dict) -> str:
    return rng.choice(_STATUSES)


def _gen_date(rng: random.Random, idx: int, spec: dict) -> str:
    ymin = int(spec.get("year_min", 2020))
    ymax = int(spec.get("year_max", 2025))
    if ymin > ymax:
        raise SchemaError(f"date field 'year_min' ({ymin}) must be <= 'year_max' ({ymax})")
    y = rng.randint(ymin, ymax)
    m = rng.randint(1, 12)
    d = rng.randint(1, 28)
    return f"{y:04d}-{m:02d}-{d:02d}"


def _gen_uuid(rng: random.Random, idx: int, spec: dict) -> str:
    hx = "".join(rng.choice("0123456789abcdef") for _ in range(32))
    return f"{hx[:8]}-{hx[8:12]}-{hx[12:16]}-{hx[16:20]}-{hx[20:]}"


FIELD_TYPES: Dict[str, Callable[[random.Random, int, dict], Any]] = {
    "pk": _gen_pk,
    "int": _gen_int,
    "float": _gen_float,
    "bool": _gen_bool,
    "first_name": _gen_first,
    "last_name": _gen_last,
    "name": _gen_name,
    "email": _gen_email,
    "word": _gen_word,
    "slug": _gen_slug,
    "enum": _gen_enum,
    "status": _gen_status,
    "date": _gen_date,
    "uuid": _gen_uuid,
    # "ref" is resolved specially by the Generator (referential integrity)
}


# --- schema model -----------------------------------------------------------

@dataclass
class Field:
    name: str
    type: str
    spec: dict = dc_field(default_factory=dict)


@dataclass
class Table:
    name: str
    count: int
    fields: List[Field]

    def pk_field(self) -> Optional[Field]:
        for f in self.fields:
            if f.type == "pk":
                return f
        return None


@dataclass
class Schema:
    tables: List[Table]

    @classmethod
    def from_dict(cls, data: dict) -> "Schema":
        if not isinstance(data, dict):
            raise SchemaError("schema must be a JSON object")
        raw_tables = data.get("tables")
        if not isinstance(raw_tables, dict) or not raw_tables:
            raise SchemaError("schema must have a non-empty 'tables' object")
        tables: List[Table] = []
        for tname, tdef in raw_tables.items():
            if not isinstance(tdef, dict):
                raise SchemaError(f"table '{tname}' must be an object")
            raw_count = tdef.get("count", 10)
            try:
                count = int(raw_count)
            except (TypeError, ValueError):
                raise SchemaError(
                    f"table '{tname}' count must be an integer, got {raw_count!r}"
                )
            if count < 0:
                raise SchemaError(f"table '{tname}' count must be >= 0")
            raw_fields = tdef.get("fields")
            if not isinstance(raw_fields, dict) or not raw_fields:
                raise SchemaError(f"table '{tname}' must have a non-empty 'fields' object")
            fields: List[Field] = []
            for fname, fdef in raw_fields.items():
                if isinstance(fdef, str):
                    fdef = {"type": fdef}
                if not isinstance(fdef, dict):
                    raise SchemaError(f"field '{tname}.{fname}' must be a type string or object")
                ftype = fdef.get("type")
                if not ftype:
                    raise SchemaError(f"field '{tname}.{fname}' missing 'type'")
                if ftype != "ref" and ftype not in FIELD_TYPES:
                    raise SchemaError(
                        f"field '{tname}.{fname}' has unknown type '{ftype}'"
                    )
                spec = {k: v for k, v in fdef.items() if k != "type"}
                fields.append(Field(name=fname, type=ftype, spec=spec))
            tables.append(Table(name=tname, count=count, fields=fields))
        schema = cls(tables=tables)
        schema.validate()
        return schema

    def table_map(self) -> Dict[str, Table]:
        return {t.name: t for t in self.tables}

    def validate(self) -> None:
        tmap = self.table_map()
        for t in self.tables:
            pks = [f for f in t.fields if f.type == "pk"]
            if len(pks) > 1:
                raise SchemaError(f"table '{t.name}' has multiple pk fields")
            for f in t.fields:
                if f.type != "ref":
                    continue
                target = f.spec.get("ref")
                if not target or "." not in str(target):
                    raise SchemaError(
                        f"ref field '{t.name}.{f.name}' needs 'ref': 'table.field'"
                    )
                rt, rf = str(target).split(".", 1)
                if rt not in tmap:
                    raise SchemaError(
                        f"ref '{t.name}.{f.name}' targets unknown table '{rt}'"
                    )
                tgt_field = next((x for x in tmap[rt].fields if x.name == rf), None)
                if tgt_field is None:
                    raise SchemaError(
                        f"ref '{t.name}.{f.name}' targets unknown field '{rt}.{rf}'"
                    )
                if tgt_field.type != "pk":
                    raise SchemaError(
                        f"ref '{t.name}.{f.name}' must target a pk, "
                        f"but '{rt}.{rf}' is type '{tgt_field.type}'"
                    )
        # ensure FK graph is acyclic by attempting a sort
        self.topo_order()

    def topo_order(self) -> List[Table]:
        """Return tables ordered so every ref target comes before its referrer."""
        tmap = self.table_map()
        deps: Dict[str, set] = {t.name: set() for t in self.tables}
        for t in self.tables:
            for f in t.fields:
                if f.type == "ref":
                    rt = str(f.spec["ref"]).split(".", 1)[0]
                    if rt != t.name:
                        deps[t.name].add(rt)
        order: List[str] = []
        done: set = set()
        # deterministic Kahn-style resolution
        remaining = [t.name for t in self.tables]
        while remaining:
            progressed = False
            for name in list(remaining):
                if deps[name] <= done:
                    order.append(name)
                    done.add(name)
                    remaining.remove(name)
                    progressed = True
            if not progressed:
                raise SchemaError(
                    f"cyclic foreign-key dependency among: {sorted(remaining)}"
                )
        return [tmap[n] for n in order]


# --- generation -------------------------------------------------------------

class Generator:
    """Generates referentially-consistent data for a Schema."""

    def __init__(self, schema: Schema, seed: int = 0):
        self.schema = schema
        self.seed = seed

    def _rng_for(self, *parts: Any) -> random.Random:
        key = "|".join(str(p) for p in (self.seed, *parts))
        h = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return random.Random(int(h[:16], 16))

    def generate(self) -> Dict[str, List[dict]]:
        result: Dict[str, List[dict]] = {}
        pk_pools: Dict[str, List[Any]] = {}
        for table in self.schema.topo_order():
            rows: List[dict] = []
            pk_field = table.pk_field()
            for i in range(table.count):
                row: dict = {}
                for f in table.fields:
                    if f.type == "ref":
                        rt, rf = str(f.spec["ref"]).split(".", 1)
                        pool = pk_pools.get(rt, [])
                        if not pool:
                            if f.spec.get("nullable"):
                                row[f.name] = None
                                continue
                            raise SeedForgeError(
                                f"ref '{table.name}.{f.name}' cannot resolve: "
                                f"parent table '{rt}' produced no rows"
                            )
                        rng = self._rng_for(table.name, i, f.name)
                        row[f.name] = rng.choice(pool)
                    else:
                        rng = self._rng_for(table.name, i, f.name)
                        gen = FIELD_TYPES[f.type]
                        row[f.name] = gen(rng, i, f.spec)
                rows.append(row)
            result[table.name] = rows
            if pk_field is not None:
                pk_pools[table.name] = [r[pk_field.name] for r in rows]
        return result


def generate(schema_dict: dict, seed: int = 0) -> Dict[str, List[dict]]:
    """Convenience: build a Schema from a dict and generate data."""
    schema = Schema.from_dict(schema_dict)
    return Generator(schema, seed=seed).generate()


def verify_integrity(schema: Schema, data: Dict[str, List[dict]]) -> List[str]:
    """Return a list of broken-FK descriptions (empty == fully consistent)."""
    problems: List[str] = []
    pk_sets: Dict[str, set] = {}
    for t in schema.tables:
        pkf = t.pk_field()
        if pkf is not None:
            pk_sets[t.name] = {r[pkf.name] for r in data.get(t.name, [])}
    for t in schema.tables:
        for f in t.fields:
            if f.type != "ref":
                continue
            rt, _rf = str(f.spec["ref"]).split(".", 1)
            valid = pk_sets.get(rt, set())
            for idx, row in enumerate(data.get(t.name, [])):
                val = row.get(f.name)
                if val is None:
                    continue
                if val not in valid:
                    problems.append(
                        f"{t.name}[{idx}].{f.name}={val!r} not in {rt} pks"
                    )
    return problems

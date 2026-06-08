# Demo 01 - Basic: a blog with referential integrity

This demo models a tiny blog database with three related tables:

- `users` (10 rows) - each has an integer primary key `id`, a name, an email,
  and a status.
- `posts` (25 rows) - each has a primary key, a title, a publish date, and an
  `author_id` **foreign key referencing `users.id`**.
- `comments` (60 rows) - each references both a `post_id` (`posts.id`) and a
  `user_id` (`users.id`).

The point of SEEDFORGE is that the foreign keys are **never dangling**. Every
`author_id` is a real user id, every `post_id` is a real post id, and so on.
SEEDFORGE topologically sorts the tables (users -> posts -> comments),
generates parents first, and draws child FKs only from real parent primary
keys.

## Run it

Generate JSON you can load straight into a test fixture:

```
python -m seedforge --format json gen demos/01-basic/blog.schema.json
```

Prove the foreign keys all resolve (exit code 0 == clean, 1 == broken):

```
python -m seedforge --format json verify demos/01-basic/blog.schema.json
```

Generation is deterministic: the same `--seed` (default `0`) always produces
the exact same rows, so your fixtures are reproducible across machines and CI.
Change the seed to get a different-but-still-consistent dataset:

```
python -m seedforge gen demos/01-basic/blog.schema.json --seed 42
```

## Schema field types

`pk`, `int`, `float`, `bool`, `name`, `first_name`, `last_name`, `email`,
`word`, `slug`, `status`, `enum` (needs `choices`), `date`, `uuid`, and `ref`
(needs `"ref": "table.field"` pointing at a `pk`).

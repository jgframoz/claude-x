from __future__ import annotations

from claude_x.store import JsonlStore


def test_append_and_read_round_trip(tmp_path):
    store = JsonlStore(tmp_path / "nested" / "posts.jsonl")
    store.append({"id": "1", "text": "hello"})
    store.append({"id": "2", "text": "world"})

    assert [record["text"] for record in store.read_all()] == ["hello", "world"]


def test_reading_a_missing_file_yields_nothing(tmp_path):
    assert JsonlStore(tmp_path / "absent.jsonl").read_all() == []


def test_unicode_survives_the_round_trip(tmp_path):
    store = JsonlStore(tmp_path / "posts.jsonl")
    store.append({"id": "1", "text": "olá — 🚀"})

    assert store.read_all()[0]["text"] == "olá — 🚀"


def test_corrupt_line_is_skipped_not_fatal(tmp_path):
    path = tmp_path / "posts.jsonl"
    path.write_text('{"id": "1"}\nnot json at all\n{"id": "2"}\n')

    assert [record["id"] for record in JsonlStore(path).read_all()] == ["1", "2"]


def test_find_and_exists(tmp_path):
    store = JsonlStore(tmp_path / "posts.jsonl")
    store.append({"id": "1", "text": "a"})
    store.append({"id": "2", "text": "b"})

    assert store.find("id", "2") == [{"id": "2", "text": "b"}]
    assert store.exists("id", "1") is True
    assert store.exists("id", "99") is False


def test_delete_where_removes_only_matching_records(tmp_path):
    store = JsonlStore(tmp_path / "posts.jsonl")
    store.append({"id": "1", "text": "keep"})
    store.append({"id": "2", "text": "remove"})
    store.append({"id": "3", "text": "keep"})

    removed = store.delete_where("id", "2")

    assert removed == 1
    assert [record["id"] for record in store.read_all()] == ["1", "3"]


def test_delete_where_is_a_noop_when_nothing_matches(tmp_path):
    store = JsonlStore(tmp_path / "posts.jsonl")
    store.append({"id": "1"})

    assert store.delete_where("id", "nope") == 0
    assert len(store.read_all()) == 1


def test_delete_where_leaves_no_temp_files_behind(tmp_path):
    store = JsonlStore(tmp_path / "posts.jsonl")
    store.append({"id": "1"})
    store.append({"id": "2"})

    store.delete_where("id", "1")

    assert [p.name for p in tmp_path.iterdir()] == ["posts.jsonl"]

import os
import pytest
import asyncio

# Use a temporary database for tests
os.environ["DB_PATH"] = ":memory:"

from database import (
    init_db,
    add_quote,
    get_quote,
    remove_quote,
    edit_quote,
    get_random_quote,
    get_quotes_by_author,
    search_quotes,
    DB_PATH,
)

# Since we use :memory:, we need a persistent connection for tests.
# Override DB_PATH won't work with :memory: across connections.
# Instead, use a temp file.
import tempfile


@pytest.fixture(autouse=True)
def setup_db(tmp_path, monkeypatch):
    db_file = str(tmp_path / "test.db")
    monkeypatch.setattr("database.DB_PATH", db_file)
    asyncio.get_event_loop().run_until_complete(init_db())
    yield


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class TestAddQuote:
    def test_add_basic_quote(self):
        qid = run(add_quote("server1", "Hello world", "user1"))
        assert qid == 1

    def test_add_sequential_ids(self):
        q1 = run(add_quote("server1", "First", "user1"))
        q2 = run(add_quote("server1", "Second", "user1"))
        assert q1 == 1
        assert q2 == 2

    def test_ids_scoped_per_server(self):
        q1 = run(add_quote("serverA", "Quote A", "user1"))
        q2 = run(add_quote("serverB", "Quote B", "user1"))
        assert q1 == 1
        assert q2 == 1

    def test_add_with_user_author(self):
        qid = run(add_quote("s1", "Test", "user1", author_user_id="author1"))
        quote = run(get_quote("s1", qid))
        assert quote["author_user_id"] == "author1"
        assert quote["author_name"] is None

    def test_add_with_text_author(self):
        qid = run(add_quote("s1", "Test", "user1", author_name="Shakespeare"))
        quote = run(get_quote("s1", qid))
        assert quote["author_user_id"] is None
        assert quote["author_name"] == "Shakespeare"


class TestGetQuote:
    def test_get_existing(self):
        run(add_quote("s1", "Hello", "u1"))
        quote = run(get_quote("s1", 1))
        assert quote is not None
        assert quote["quote_text"] == "Hello"

    def test_get_nonexistent(self):
        quote = run(get_quote("s1", 999))
        assert quote is None

    def test_server_isolation(self):
        run(add_quote("s1", "Server 1 quote", "u1"))
        quote = run(get_quote("s2", 1))
        assert quote is None


class TestRemoveQuote:
    def test_remove_existing(self):
        run(add_quote("s1", "To remove", "u1"))
        result = run(remove_quote("s1", 1))
        assert result is not None
        assert run(get_quote("s1", 1)) is None

    def test_remove_nonexistent(self):
        result = run(remove_quote("s1", 999))
        assert result is None


class TestEditQuote:
    def test_edit_text(self):
        run(add_quote("s1", "Original", "u1"))
        updated = run(edit_quote("s1", 1, quote_text="Edited"))
        assert updated["quote_text"] == "Edited"

    def test_edit_author_user(self):
        run(add_quote("s1", "Test", "u1", author_name="Old"))
        updated = run(edit_quote("s1", 1, author_user_id="new_user"))
        assert updated["author_user_id"] == "new_user"
        assert updated["author_name"] is None

    def test_edit_author_name(self):
        run(add_quote("s1", "Test", "u1", author_user_id="old_user"))
        updated = run(edit_quote("s1", 1, author_name="New Name"))
        assert updated["author_name"] == "New Name"
        assert updated["author_user_id"] is None

    def test_edit_nonexistent(self):
        result = run(edit_quote("s1", 999, quote_text="Nope"))
        assert result is None


class TestRandomQuote:
    def test_random_from_pool(self):
        run(add_quote("s1", "Q1", "u1"))
        run(add_quote("s1", "Q2", "u1"))
        quote = run(get_random_quote("s1"))
        assert quote is not None
        assert quote["quote_text"] in ("Q1", "Q2")

    def test_random_empty(self):
        quote = run(get_random_quote("empty_server"))
        assert quote is None

    def test_random_filtered_by_user(self):
        run(add_quote("s1", "By A", "u1", author_user_id="authorA"))
        run(add_quote("s1", "By B", "u1", author_user_id="authorB"))
        quote = run(get_random_quote("s1", author_user_id="authorA"))
        assert quote["author_user_id"] == "authorA"


class TestSearchQuotes:
    def test_search_match(self):
        run(add_quote("s1", "The quick brown fox", "u1"))
        run(add_quote("s1", "Lazy dog", "u1"))
        results = run(search_quotes("s1", "quick"))
        assert len(results) == 1
        assert "quick" in results[0]["quote_text"]

    def test_search_no_match(self):
        run(add_quote("s1", "Hello", "u1"))
        results = run(search_quotes("s1", "xyz"))
        assert len(results) == 0

    def test_search_server_isolation(self):
        run(add_quote("s1", "Shared text", "u1"))
        results = run(search_quotes("s2", "Shared"))
        assert len(results) == 0


class TestGetQuotesByAuthor:
    def test_by_user_id(self):
        run(add_quote("s1", "Q1", "u1", author_user_id="a1"))
        run(add_quote("s1", "Q2", "u1", author_user_id="a2"))
        results = run(get_quotes_by_author("s1", author_user_id="a1"))
        assert len(results) == 1

    def test_by_name(self):
        run(add_quote("s1", "Q1", "u1", author_name="Bob"))
        run(add_quote("s1", "Q2", "u1", author_name="Alice"))
        results = run(get_quotes_by_author("s1", author_name="Bob"))
        assert len(results) == 1

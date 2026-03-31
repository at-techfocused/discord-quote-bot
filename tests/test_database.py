import os
import pytest
import asyncio

from database import (
    init_db,
    close_db,
    add_quote,
    get_quote,
    remove_quote,
    edit_quote,
    get_random_quote,
    count_quotes_by_author,
    get_quotes_by_author_page,
    count_search_quotes,
    search_quotes_page,
    count_server_quotes,
    log_audit,
    get_audit_log,
)
import database


@pytest.fixture(autouse=True)
def setup_db(tmp_path, monkeypatch):
    db_file = str(tmp_path / "test.db")
    monkeypatch.setattr(database, "DB_FILE", db_file)
    asyncio.get_event_loop().run_until_complete(init_db())
    yield
    asyncio.get_event_loop().run_until_complete(close_db())


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
        run(remove_quote("s1", 1))
        assert run(get_quote("s1", 1)) is None

    def test_remove_nonexistent(self):
        # Should not raise
        run(remove_quote("s1", 999))


class TestEditQuote:
    def test_edit_text(self):
        run(add_quote("s1", "Original", "u1"))
        updated = run(edit_quote("s1", 1, quote_text="Edited"))
        assert updated["quote_text"] == "Edited"

    def test_edit_author_user(self):
        run(add_quote("s1", "Test", "u1", author_name="Old"))
        updated = run(edit_quote("s1", 1, author_user_id="new_user"))
        assert updated["author_user_id"] == "new_user"

    def test_edit_author_name(self):
        run(add_quote("s1", "Test", "u1", author_user_id="old_user"))
        updated = run(edit_quote("s1", 1, author_name="New Name"))
        assert updated["author_name"] == "New Name"

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


class TestPaginatedSearch:
    def test_count_and_page(self):
        for i in range(12):
            run(add_quote("s1", "Quote %d about cats" % i, "u1"))
        run(add_quote("s1", "About dogs", "u1"))

        count = run(count_search_quotes("s1", "cats"))
        assert count == 12

        page0 = run(search_quotes_page("s1", "cats", 0))
        assert len(page0) == 5

        page1 = run(search_quotes_page("s1", "cats", 1))
        assert len(page1) == 5

        page2 = run(search_quotes_page("s1", "cats", 2))
        assert len(page2) == 2

    def test_search_no_match(self):
        run(add_quote("s1", "Hello", "u1"))
        count = run(count_search_quotes("s1", "xyz"))
        assert count == 0

    def test_search_server_isolation(self):
        run(add_quote("s1", "Shared text", "u1"))
        count = run(count_search_quotes("s2", "Shared"))
        assert count == 0


class TestPaginatedAuthor:
    def test_count_and_page(self):
        for i in range(7):
            run(add_quote("s1", "Q%d" % i, "u1", author_user_id="a1"))
        run(add_quote("s1", "Other", "u1", author_user_id="a2"))

        count = run(count_quotes_by_author("s1", author_user_id="a1"))
        assert count == 7

        page0 = run(get_quotes_by_author_page("s1", 0, author_user_id="a1"))
        assert len(page0) == 5

        page1 = run(get_quotes_by_author_page("s1", 1, author_user_id="a1"))
        assert len(page1) == 2

    def test_by_name(self):
        run(add_quote("s1", "Q1", "u1", author_name="Bob"))
        run(add_quote("s1", "Q2", "u1", author_name="Alice"))
        count = run(count_quotes_by_author("s1", author_name="Bob"))
        assert count == 1

    def test_case_insensitive_author_name(self):
        run(add_quote("s1", "Q1", "u1", author_name="Bob"))
        run(add_quote("s1", "Q2", "u1", author_name="bob"))
        count = run(count_quotes_by_author("s1", author_name="BOB"))
        assert count == 2


class TestAuditLog:
    def test_log_and_retrieve(self):
        run(add_quote("s1", "Q1", "u1"))
        run(log_audit("s1", 1, "edit", "u2", old_value="Q1", new_value="Q1 edited"))
        entries = run(get_audit_log("s1", quote_id=1))
        assert len(entries) == 1
        assert entries[0]["action"] == "edit"
        assert entries[0]["user_id"] == "u2"
        assert entries[0]["old_value"] == "Q1"
        assert entries[0]["new_value"] == "Q1 edited"

    def test_log_delete(self):
        run(add_quote("s1", "Q1", "u1"))
        run(log_audit("s1", 1, "delete", "u3", old_value="Q1"))
        entries = run(get_audit_log("s1", quote_id=1))
        assert len(entries) == 1
        assert entries[0]["action"] == "delete"
        assert entries[0]["new_value"] is None

    def test_log_server_isolation(self):
        run(log_audit("s1", 1, "edit", "u1"))
        run(log_audit("s2", 1, "edit", "u1"))
        assert len(run(get_audit_log("s1"))) == 1
        assert len(run(get_audit_log("s2"))) == 1

    def test_log_recent_first(self):
        run(log_audit("s1", 1, "edit", "u1", old_value="v1", new_value="v2"))
        run(log_audit("s1", 1, "edit", "u1", old_value="v2", new_value="v3"))
        entries = run(get_audit_log("s1"))
        assert entries[0]["new_value"] == "v3"
        assert entries[1]["new_value"] == "v2"


class TestServerCount:
    def test_count_server_quotes(self):
        run(add_quote("s1", "Q1", "u1"))
        run(add_quote("s1", "Q2", "u1"))
        run(add_quote("s2", "Q3", "u1"))
        assert run(count_server_quotes("s1")) == 2
        assert run(count_server_quotes("s2")) == 1
        assert run(count_server_quotes("s3")) == 0

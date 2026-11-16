"""The result-mix report counts replies, retweets and repeated text without double-counting a post."""

import pytest

from scripts.social_result_mix import kinds, mix, open_private_database


def test_each_kind_comes_from_its_own_source_signal():
    assert kinds({"is_reply": True, "body": "@someone Thanks!", "same_body_records": 1}) == {"reply"}
    assert kinds({"is_reply": False, "body": "  RT @Example: New site opens", "same_body_records": 1}) == {"retweet"}
    assert kinds({"is_reply": False, "body": "Same text twice", "same_body_records": 2}) == {"repeated_text"}
    # A mention is not a reply mark, and no mark (Facebook, Instagram) is not a reply.
    assert kinds({"is_reply": None, "body": "@Example see you there", "same_body_records": 1}) == set()


def test_a_post_with_several_kinds_counts_once_in_any():
    rows = [{"is_reply": True, "body": "RT @Example: hello", "same_body_records": 3, "platform": "Twitter"},
            {"is_reply": False, "body": "An original post", "same_body_records": 1, "platform": "Facebook"}]
    report = mix(rows)
    assert report["platforms"] == {"Twitter": 1, "Facebook": 1}
    assert report["counts"] == {"reply": 1, "retweet": 1, "repeated_text": 1, "any": 1}
    assert report["shares"]["any"] == 0.5


def test_an_empty_result_list_has_no_shares():
    assert mix([])["shares"] == {"reply": None, "retweet": None, "repeated_text": None, "any": None}


class FakeCluster:
    def __init__(self, data):
        self.data = data

    def settings(self):
        return {"admin_user": "admin", "admin_password": "a", "app_user": "app", "app_password": "b"}


def fake_connect(data_directory, port):
    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def execute(self, query):
            class Result:
                def fetchone(self):
                    return (str(data_directory), str(port))
            return Result()
    return lambda **kwargs: Connection()


def test_a_server_that_is_not_the_named_private_cluster_is_refused_before_any_read(tmp_path):
    opened = []
    cluster = FakeCluster((tmp_path / "a").resolve())
    for server_data, server_port in ((tmp_path / "b", 47311), (tmp_path / "a", 5432)):
        with pytest.raises(RuntimeError, match="not the named private test cluster"):
            open_private_database(cluster, 47311, connect=fake_connect(server_data, server_port),
                                  database_cls=opened.append, host="127.0.0.1")
    assert opened == []


def test_the_named_private_cluster_is_opened_on_its_port(tmp_path):
    opened = []
    cluster = FakeCluster((tmp_path / "a").resolve())
    open_private_database(cluster, 47311, connect=fake_connect(tmp_path / "a", 47311),
                          database_cls=opened.append, host="127.0.0.1")
    assert len(opened) == 1 and opened[0].endswith("@127.0.0.1:47311/obs_test")

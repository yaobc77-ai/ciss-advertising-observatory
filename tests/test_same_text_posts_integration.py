"""C22 on the private test cluster: an answer's search gives each social text one place.

Fictional posts only, in a schema this module owns on the verified private target (no table of
another fixture is touched). Posts are admitted like imported ones. The earliest post in the
selection is the group's first post; the citation moves to it only when it has the retrieved
passages' exact text; a post outside the selection is not counted; every other caller keeps one
place per post. A post that also carries a passage of another saved text (as a few imported posts
do, one passage per saved observation) is never counted with the posts of its current text; that
passage is added in the module's own schema, since admission leaves a post whose saved texts
differ out of retrieval.
"""

import hashlib
from datetime import date
from uuid import uuid4

import pytest
from postgres_fixtures import configured_test_url, verified_test_connection
from psycopg import sql

from observatory.db import Database
from observatory.import_records import CanonicalRecord
from observatory.models import Filters, ImportBatch, RecordInput
from observatory.social_admission import _admit_group

pytestmark = pytest.mark.integration

SHARED = "Tidal kites will power the harbor and bring local jobs."
OWN = "Our tidal kite festival brings families to the harbor."
TAIL = "Tide crews meet at the jobs fair on Monday."


def admitted_post(number, bodies, account, published_at, platform="Twitter"):
    """One post admitted from one saved observation per body."""
    url = f"https://twitter.com/tidalkites/status/{number}"
    members = [(n, CanonicalRecord(record_id=f"fixture:{number}-{n}", dataset="social", platform=platform, url=url,
                                   body=body, account=account, published_at=published_at, countable=False,
                                   retrievable=False, raw={"body_sha256": hashlib.sha256(body.encode()).hexdigest(),
                                                           "source_row": {"post_text": body}}))
               for n, body in enumerate(bodies, 1)]
    admitted, _ = _admit_group(members, url, "a" * 64,
                               {"data_sha256": "b" * 64,
                                "selections": {"D02": {"id": "synthetic-D02"}, "D03": {"id": "synthetic-D03"}}})
    return admitted


@pytest.fixture(scope="module")
def db():
    url = configured_test_url()
    schema = "obs_same_text_" + uuid4().hex
    with verified_test_connection(url) as conn:
        conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))

    class ScopedDatabase(Database):
        def connect(self, vector=False):
            return verified_test_connection(self.url, schema)

    scoped = ScopedDatabase(url)
    scoped.initialize()
    posts = [admitted_post(101, [SHARED], "Kite Guild", date(2021, 3, 1)),
             admitted_post(102, [SHARED], "Harbor Watch", date(2020, 1, 1)),
             admitted_post(103, [OWN], "Harbor Fest", date(2020, 6, 1)),
             admitted_post(104, [SHARED], "Old Account", date(2019, 1, 1)),  # outside the dated selection
             admitted_post(105, [SHARED], "Mixed Account", date(2020, 2, 1))]  # gets a passage of another text
    first = RecordInput(record_id="first-post", dataset="social", url="https://example.invalid/first", body=SHARED,
                        account="First Account", platform="Twitter", published_at=date(2018, 1, 1),
                        retrievable=False)  # counted, never quotable
    scoped.import_batch(ImportBatch(records=[*posts, first, RecordInput(
        record_id="n1", dataset="native", title="Kite notice", url="https://example.invalid/n1",
        body="Tidal kites will power the harbor and bring local jobs to every dock.", retrievable=True)]))
    scoped.ids = {post.account: post.record_id for post in [*posts, first]}
    tail_hash = hashlib.sha256(TAIL.encode()).hexdigest()
    with scoped.connect() as conn:  # one passage from another saved observation, not retrievable itself
        conn.execute(
            "INSERT INTO chunks(chunk_id,record_id,version_id,text,text_hash,start_char,end_char,paragraph_ids,"
            "token_count,source_observation_id,source_version_id,source_body_hash) "
            "SELECT chunk_id||'-tail',record_id,version_id,%s,%s,0,%s,paragraph_ids,token_count,"
            "'fixture-tail-observation',%s,%s FROM chunks WHERE record_id=%s ORDER BY start_char LIMIT 1",
            [TAIL, tail_hash, len(TAIL), tail_hash, tail_hash, scoped.ids["Mixed Account"]])
    yield scoped
    with verified_test_connection(url) as conn:
        conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


QUERY = "tidal kites harbor jobs"


def test_an_answer_search_gives_each_text_one_place_held_by_the_earliest_post(db):
    ids = db.ids
    hits = db.search(QUERY, Filters(dataset="social", date_from=date(2019, 6, 1)), limit=5, fold_same_text=True)
    assert sorted({hit.record_id for hit in hits}) == sorted([ids["Harbor Watch"], ids["Harbor Fest"],
                                                              ids["Mixed Account"]])
    shared = next(hit for hit in hits if hit.record_id == ids["Harbor Watch"])
    assert [(p.record_id, p.account, p.published_at) for p in shared.same_text_posts] == [
        (ids["Kite Guild"], "Kite Guild", date(2021, 3, 1))]  # the mixed post is not counted as the same text
    assert shared.same_text_first_post is None  # the cited post is the earliest
    assert db.validate_evidence(shared)  # the cited post's own passage, checked against the database
    assert next(hit for hit in hits if hit.record_id == ids["Harbor Fest"]).same_text_posts == []
    assert next(hit for hit in hits if hit.record_id == ids["Mixed Account"]).same_text_posts == []
    assert "body_hash" not in shared.model_dump()  # internal only


def test_the_earliest_post_is_named_when_it_cannot_be_quoted(db):
    ids = db.ids
    folded = db.search(QUERY, Filters(dataset="social"), limit=5, fold_same_text=True)
    shared = next(hit for hit in folded if hit.same_text_posts)
    assert shared.record_id == ids["Old Account"]  # the earliest post with the retrieved passage
    assert shared.same_text_first_post.record_id == ids["First Account"]
    assert [p.record_id for p in shared.same_text_posts] == [ids["First Account"], ids["Harbor Watch"],
                                                              ids["Kite Guild"]]
    assert db.validate_evidence(shared)


def test_every_other_caller_keeps_one_place_per_post(db):
    ids = db.ids
    hits = db.search(QUERY, Filters(dataset="social"), limit=6)
    quotable = [ids[name] for name in ("Kite Guild", "Harbor Watch", "Harbor Fest", "Old Account", "Mixed Account")]
    assert sorted({hit.record_id for hit in hits}) == sorted(quotable)
    assert all(hit.same_text_posts == [] for hit in hits)
    # The mixed post carries no text identity anywhere, so a list never groups it either.
    assert {hit.record_id: bool(hit.body_hash) for hit in hits} == {rid: rid != ids["Mixed Account"] for rid in quotable}
    passages = db.record_passages([ids["Mixed Account"], ids["Kite Guild"]], Filters(dataset="social"))
    assert {p.record_id: bool(p.body_hash) for p in passages} == {ids["Mixed Account"]: False, ids["Kite Guild"]: True}


def test_both_collections_still_alternate_when_a_text_repeats(db):
    hits = db.search(QUERY, Filters(dataset="all"), limit=3, fold_same_text=True)
    datasets = [hit.dataset for hit in hits]
    assert datasets.count("native") == 1 and datasets.count("social") == 2  # one ad, two posts that differ
    assert len({hit.record_id for hit in hits if hit.dataset == "social"}) == 2

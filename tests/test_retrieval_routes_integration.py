"""db.search keeps, for the reader, the words each route matched and the places it gave.

Fictional ferry notices only; no model call, no vector (keyword and title routes). A replay's
question vector is read from the embeddings cache through the real adapter.
"""

from uuid import uuid4

import numpy as np
import pytest
from pgvector.psycopg import register_vector
from postgres_fixtures import configured_test_url, verified_test_connection
from psycopg import sql

from observatory.db import Database
from observatory.models import Filters, ImportBatch, RecordInput
from observatory.retrieval_explain import passage_score


def native(identifier, title, body):
    return RecordInput(record_id=identifier, dataset='native', title=title,
                       url='https://ferry.example.invalid/' + identifier, body=body,
                       retrievable=True, publisher='Harbor Bulletin')


@pytest.fixture(scope='module')
def sample():
    url = configured_test_url()
    schema = 'obs_routes_' + uuid4().hex
    with verified_test_connection(url) as conn:
        conn.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))

    class ScopedDatabase(Database):
        def connect(self, vector=False):
            conn = verified_test_connection(self.url, schema)
            if vector:
                register_vector(conn)
            return conn

    db = ScopedDatabase(url)
    db.initialize()
    db.import_batch(ImportBatch(records=[
        native('lantern', 'Harbor ferry lantern timetable', 'Lantern boats leave the harbor at dusk.'),
        native('pier', 'Pier repairs', 'The ferry stops at the north pier while the harbor is dredged.'),
        native('mugs', 'Painted mugs', 'Ceramic mugs and painted shelves.'),
    ]))
    return db


@pytest.mark.integration
def test_each_found_passage_names_its_words_routes_and_places(sample):
    rows = sample.search('Which ferry ads mention the harbor lantern timetable?', Filters(dataset='native'), limit=5)
    by_id = {row.record_id: row for row in rows}
    assert set(by_id) == {'lantern', 'pier'}
    lantern = by_id['lantern']
    assert lantern.retrieval_routes['run'] == ['keyword', 'title']
    assert set(lantern.retrieval_routes['keyword']['terms']) == {'harbor', 'lantern'}  # 'ferry' is only in its title
    assert set(lantern.retrieval_routes['title']['terms']) == {'ferry', 'harbor', 'lantern', 'timetable'}
    assert 'title' not in by_id['pier'].retrieval_routes
    assert set(by_id['pier'].retrieval_routes['keyword']['terms']) == {'ferry', 'harbor'}
    search = lantern.retrieval_search
    assert {'ads', 'ferry', 'harbor', 'lantern', 'timetable'} <= set(search['terms'])
    assert {'the', 'which'} <= set(search['dropped']) | set(search['unindexed']) and search['cut'] == []
    for row in rows:  # the reader's score is the fusion score rescaled: × 61 ÷ routes run × 100
        assert passage_score(row.retrieval_routes)['score'] == pytest.approx(row.score * 61 / 2 * 100)


@pytest.mark.integration
def test_words_past_the_first_forty_are_reported_as_cut(sample):
    filler = ' '.join(f'word{n:02}x' for n in range(40))
    rows = sample.search('harbor lantern ' + filler, Filters(dataset='native'), limit=5)
    assert rows and rows[0].retrieval_search['cut'] == ['word38x', 'word39x']
    one_word = sample.search('lantern', Filters(dataset='native'), limit=5)
    assert one_word[0].retrieval_routes['run'] == ['keyword']  # a title needs two meaningful words


@pytest.mark.integration
def test_a_cached_question_vector_is_read_back_through_the_real_adapter(sample):
    from observatory.query_demo import cached_vector
    from observatory.rag import digest

    vector = [0.001 * (n % 97) for n in range(1536)]
    with sample.connect(vector=True) as conn:
        conn.execute("INSERT INTO embeddings(text_hash,model,embedding) VALUES (%s,%s,%s)",
                     (digest("harbor lantern"), "text-embedding-3-small", np.array(vector)))
    assert cached_vector(sample, "harbor lantern") == pytest.approx(vector, abs=1e-6)
    assert cached_vector(sample, "a question never embedded") is None

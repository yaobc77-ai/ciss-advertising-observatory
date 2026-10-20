"""A narrow selection is read whole for a content answer (B1K-Q009: 27 posts, top 5 read)."""

from test_list_screening import screening_service

from observatory.models import Filters


def ranked_read(service, db, filters, rows):
    db.public_rows = lambda _: [{"record_id": f"r{n}", "title": "", "dataset": "native"} for n in range(rows)]
    service._answer_evidence("What did Tidal Co say about quiet kites?", filters, "offline", audit=False)
    return [call.kwargs.get("limit") for call in db.search.call_args_list if "vector" in call.kwargs]


def test_a_narrow_selection_is_read_whole():
    service, _, db = screening_service([])
    assert ranked_read(service, db, Filters(dataset="native", sponsors=["Tidal Co"]), 27) == [27]


def test_a_larger_or_unfiltered_selection_keeps_the_ranked_read():
    service, _, db = screening_service([])
    assert ranked_read(service, db, Filters(dataset="native", sponsors=["Tidal Co"]), 31) == [None]
    db.search.reset_mock()
    assert ranked_read(service, db, Filters(dataset="native"), 12) == [None]

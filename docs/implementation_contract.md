# Shared implementation contract

Root owns models.py, config.py, db.py, service.py, rag.py, budget.py, cli.py, SQL and integration.
Data contributor owns ingest.py, quality.py, chunking.py, tests/test_ingest.py, tests/test_quality.py, tests/test_chunking.py, docs/data_dictionary.md and config/social_mapping.example.json.
UI contributor owns app.py, assets/, tests/test_app.py, docs/user_guide.md.
Runtime contributor owns scripts/, docs/local_postgres.md and runtime evidence only.

Python imports use observatory.models contracts. Data functions:

* load_native(root: pathlib.Path) -> ImportBatch, root is workspace root with sources/.
* load_social(path: pathlib.Path, mapping: dict) -> ImportBatch; explicit column mapping.
* inspect_body(body: str) -> list[Issue]; ingestion determines retrievable conservatively.
* chunk_body(body: str, max_tokens=600, overlap_tokens=100) -> list[dict]; each dict has text, start, end, paragraph_ids, token_count; exact original offsets, never normalize stored body.

Service(settings) public methods (root implements):

* browse(filters: Filters) -> list[dict]: public fields record_id, dataset, url, archive_url, publisher, title, date (ISO or None), sponsor, keyword, platform, account, retrievable, labels (list), version_id. No disclosure/raw/local paths.
* facets(dataset: str) -> dict: publishers, sponsors, platforms, keywords, labels are sorted string lists. Unknown text appears as '(Unknown)'.
* statistics(filters) -> dict: total, retrievable, unknown_dates, publishers/sponsors/platforms/keywords list of {name,count,percent}, timeline list of {month,count}, relationships list of {sponsor,publisher,count}. All from same filtered records.
* search(question: str, filters: Filters, limit=5) -> list[Evidence]. Default keyword search, optional embeddings handled by separate answer flow.
* answer(question: str, filters: Filters, visitor: str) -> Answer; errors translated into status, never secret tracebacks to public.
* health() -> dict: status, record_counts, data_version; no DSN or secrets.

Settings from config.py: database_url, show_source_links (bool), host, port, monthly_budget_usd, generation_model, embedding_model. create_app(service, settings) -> dash.Dash.

UI must retain independent native/social filters, show actual unavailable social state, use 6 native columns without disclosure, export exactly browse(filters), source links gated in table AND evidence. Query input maximum 2000 characters. Distinguish lookup search (free) from paid answer button. Both native and social each have filter panel and charts; global search can select all.

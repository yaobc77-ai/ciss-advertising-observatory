-- Whole-collection counts (Database.count_public) spent seconds decompressing every
-- version's payload only to test `countable` (2026-11-05 measurement: 3 s for the social
-- or combined collection). This partial index lists the countable versions by version_id,
-- so a count joins records to it without reading any payload (an index-only scan).
-- Data and answers are unchanged, and the code runs without the index (the count then
-- scans as before), so undoing it is DROP INDEX record_versions_countable; only to let a
-- later `observatory migrate` rebuild it, also delete the version-9 row of schema_migrations.
CREATE INDEX IF NOT EXISTS record_versions_countable
    ON record_versions(version_id) WHERE (payload->>'countable')::boolean;

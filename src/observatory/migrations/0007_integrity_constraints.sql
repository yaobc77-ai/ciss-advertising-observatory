-- Database-level integrity for invariants the application already assumes.
-- Entity and referential integrity: a record's current version and each chunk's
-- version must exist and belong to that same record. Deferrable, because a
-- record row and its first version are written in one transaction.
ALTER TABLE records ADD CONSTRAINT records_current_version_fk
    FOREIGN KEY (record_id, current_version) REFERENCES record_versions(record_id, version_id)
    DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE chunks ADD CONSTRAINT chunks_record_version_fk
    FOREIGN KEY (record_id, version_id) REFERENCES record_versions(record_id, version_id);

-- A version is identified by the hash of its content, so it is immutable:
-- a correction or redaction is a new version, never an in-place rewrite.
CREATE OR REPLACE FUNCTION record_versions_immutable() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'record_versions rows are immutable; write a new version instead'
        USING ERRCODE = 'integrity_constraint_violation';
END
$$;

CREATE TRIGGER record_versions_no_update BEFORE UPDATE OR DELETE ON record_versions
    FOR EACH ROW EXECUTE FUNCTION record_versions_immutable();

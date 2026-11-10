-- A reader's own check of one record in a list answer: relevant to the question or not.
-- Checks never change an answer. They grow the human-labelled set on which the
-- listed / human-check / excluded routes are measured (relevance_triage).
-- One row per visitor, question and record; a second click replaces the first.
CREATE TABLE IF NOT EXISTS relevance_reviews (
 review_id text PRIMARY KEY,
 visitor_hash text NOT NULL,
 question text NOT NULL CHECK(length(question) BETWEEN 1 AND 2000),
 question_sha256 text NOT NULL,
 record_id text NOT NULL REFERENCES records(record_id),
 route text NOT NULL CHECK(route IN ('pass','review','exclude')),
 verdict text NOT NULL CHECK(verdict IN ('relevant','not_relevant')),
 policy text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(visitor_hash, question_sha256, record_id)
);
CREATE INDEX IF NOT EXISTS relevance_reviews_route ON relevance_reviews(route, verdict);

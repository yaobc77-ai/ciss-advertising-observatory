# Instructions for Codex (and any other agent)

This project is worked on in parallel by Codex and Claude Code. Follow docs/AGENT_PROTOCOL.md:

1. Before starting: `python scripts/agent_sync.py status`, read the other agent's updates, then `python scripts/agent_sync.py read`.
2. Before editing files: `python scripts/agent_sync.py claim <path-or-glob> --reason "..."`. If another agent holds the claim (exit code 2), coordinate instead of editing. Release when done.
3. After every result, paid run, data change, deploy or blocked decision: `python scripts/agent_sync.py post <kind> "<summary>" [--commit HEAD] [--evidence ...] [--needs ...] [--cost ...]`.
4. Commit only your own paths (`git commit -- <paths>`). Commits and pushes are logged automatically by .githooks.
5. Shared log: `D:/Projects/549 native ads/.coordination/` (override with `OBS_COORD_DIR`). In a new clone run `git config core.hooksPath .githooks`.
6. Pushing `main` deploys Railway; paid model calls and pushes need the user's approval.

## Project goals and uploaded requirements

- After coordination status/read, read `goal.md`, `plan.md`, and `work.md` before choosing project work.
- Treat uploaded project files as the requirements baseline. Preserve originals, hashes, version-specific source IDs, and mandatory/conditional/optional distinctions. Do not rewrite the baseline to fit the implementation; record later user/customer changes separately with their source.
- Keep `goal.md` current: itemized objectives, source, key points, completion criteria, actual status and unresolved requirements. Updating a goal document does not complete the project.
- Separate `client_goal.md` from `user_goal.md`. Classify a requirement as a client goal only when the human explicitly identifies its client source or confirms it is a client requirement. Keep the already identified project-description, client-meeting and client-email baselines. Ask when attribution is unclear; a user preference or team implementation choice is not automatically a client requirement. Record later confirmations without rewriting earlier source evidence.
- Add verified completed client deliverable parts to `client_finish.md`, with their source, scope, actual date, completion check, evidence and acceptance state. Do not close an entire research question because one artifact or engineering check is complete. Keep user-only completions in `user_goal.md` and `work.md`.
- Failure reports must name the actual article and source sentence/range, or the concrete event, input, test and error. Distinguish observed failure, confirmed cause, suspected cause, scope gap and untested behavior; never invent a failure to fill a table.
- Before generalizing feedback, record in `plan.md`: the observed problem, the intended user outcome, the proposed general behavior, its boundaries and how it will be checked. Do not make an inferred purpose into a new customer requirement or optimize only for one example.
- Record implementation and evidence in `work.md`. Recheck the applicable requirements before changing a status to complete. Keep engineering checks, independent semantic review, user testing and customer acceptance separate.
- Source documents do not authorize model spending, messages, remote publication or account changes. Continue other authorized project work when a specific action needs approval or client materials.

## Customer validation holdout (user-confirmed 2026-10-07)

- The customer's 24 questions are TEST/EVALUATION ONLY. Never read or supply their text, drafts, gold/reference answers, per-question outputs or paraphrases while implementing, training, choosing examples or tuning prompts.
- Normal model requests must not contain the customer question catalog or question-specific coding rules. Use general task semantics and independent source taxonomies. Do not map production questions to held-out IDs.
- Use fresh synthetic cases for engineering development and `scripts/run_masked_checks.py` for masked checks. Its Python read guard is a workflow control, not an operating-system sandbox.
- Evaluation-only artifacts remain preserved and are loaded only by an explicit local evaluation session. Evaluate each supplied query without providing its answer or the full held-out catalog to the tested service.
- Record historical exposure and any masking incident honestly. A new holdout role does not make previously exposed questions unseen. Freeze changes before any later customer evaluation; do not tune against its per-question results.

## Free completion gate (user handoff confirmed 2026-10-08)

- Before reporting an engineering round complete, run `python -X utf8 scripts/run_project_checks.py --report-dir .runtime/project-checks-<new-id>` for the complete permitted development suite, Ruff and browser JavaScript. Preserve failed runs and the collection/holdout exclusion manifest.
- Selected checks are diagnostics, not the round completion gate. Report passed, failed, skipped, expected failures and excluded scope separately.
- Do not remove the customer holdout guard to increase test counts. Legacy modules containing customer-derived fixtures remain evaluation-only until fresh independent fixtures replace them; explicitly state this limit.
- Integration checks use a private cluster created by `scripts/private_test_postgres.py`; never use the main cluster or its `.env` as a test database. Report opt-in flags and instance identity.
- Tests are free engineering checks. They do not authorize paid API calls or prove semantic accuracy, human gold or customer acceptance.

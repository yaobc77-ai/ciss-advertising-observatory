# Media-answer source handoff candidate

Prepared locally on 6 October 2026. This candidate captures the typed media-answer
changes described in [media answers](../architecture/media_answers.md). It is not published and
does not imply client acceptance, real media recognition or answer accuracy.

## Captured source and installed checks

A new source archive is frozen separately from the earlier 628-file package.
The existing handoff rules include runtime code, tests, scripts, dependencies,
schema and public documentation. Private data, customer originals, review
journals, model responses, media assets and credentials remain separate.

The review archive contains **634 payload files**: 87 runtime files, 156 test
files, 47 maintenance scripts, 19 evaluation files and the remaining public
configuration, schema and documentation. It was extracted outside the checkout,
built into a wheel and installed in a fresh external environment using existing
local dependency caches. All runtime bytes match the extracted source, wheel
and installation. All 75 imported Observatory modules come from that installed
package; 13 extracted maintenance commands start their help entries.

The installed regression passed **613 checks across 29 test files**, with zero
failures or errors and three skipped cases. The three skips are handoff-builder
symlink tests because this Windows host cannot create the test links. The checks
cover typed media, fixed-source validation, per-target citation coverage, answer
and failure presentation, prompt/progress rules, statistics, CLI, MCP and package
boundaries. Source and installed bytes stayed unchanged. Network connections
other than the local socketpair used by the MCP transport were denied; no real
database or model was called. These are engineering checks, not answer accuracy
or 613 independent user questions, and they overlap the earlier 496-case run.

The package version remains **0.4.10**; the new wheel SHA-256 is
`41a47474b93edb007f64506d62b5a8b4bd8ad79fb83ae28c0befadbcde160971`.
The final source archive and its SHA-256 sidecar identify the delivered bytes.
Only existing Markdown may be updated after the tested review capture; every
tested non-Markdown byte and package member must remain unchanged. Finalization
and its manifest comparison are recorded separately from installation.

A first final capture passed the archive, extraction, CRC, checksum and manifest
comparison, including all 87 runtime files against the wheel and installed
package. Independent read-only review found no blocking issue. That first
capture is retained. The selected archive is
`ciss-observatory-media-answer-source-20261006-02.zip`, with its SHA-256 sidecar,
`verification_final_02.json` and `source_final_receipt_02.json` in the evidence
directory. The second capture incorporates only the existing documentation
updates and must retain the tested non-Markdown bytes and package members.

Earlier package results are retained for their original bytes and do not verify this one.
Same-machine offline installation will not prove cold-machine or independent-user
reproduction. Database restoration, actual recognition, semantic evaluation,
release approval and client acceptance remain separate requirements.

The new local evidence directory is `.runtime/media_source_handoff_20261006/`:
`installed_summary.json`, `source_review_receipt.json`, `installed_tests.json`,
`installed_selected.junit.xml`, `source_tools.json` and the final archive receipt.
The external environment is `D:/Projects/observatory-media-answer-20261006/`.
See [earlier candidate records](current_source_candidate_20261006.md),
[current handoff](../current_handoff.md) and [engineering execution](../../work.md).

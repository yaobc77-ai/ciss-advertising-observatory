# Collected company social posts

The user confirmed two local review choices on 6 October 2026: present the supplied Twitter material as **collected company posts**, and count **unique original posts**. These are user policy decisions. They do not establish verified paid advertising, reviewed classifications or client acceptance.

## Counting and source differences

The preparation groups observations by platform and canonical original post URL. Twitter/X host aliases, trailing slashes and handle capitalization are normalized; unknown URLs are preserved separately, not invented. Different original URLs remain different posts even when their text is identical.

Every supplied observation is retained, including duplicate source IDs, original URLs, text, historical annotations and reversible explanation encodings. The original prepared input is copied without changing its bytes. New canonical record IDs are derived from the platform and canonical URL; the existing unadmitted source records are not modified.

When observations disagree:

- Company and account fields become unknown; source variants retain every supplied value.
- Different bodies pause retrieval. The detail page explicitly identifies its displayed body as one preserved observation, not an adjudicated version, and displays all variants.
- Different historical boolean values leave the canonical historical annotation unknown. Their original values remain visible per observation. The current thirteen-value annotation contract cannot publish partial historical blocks, so the whole block is withheld rather than manufacturing a merged value.
- Different publication dates become unknown; collection timestamps are not substituted.

The stable source-ID ordering chooses a display observation only. It does not resolve a source disagreement. Post-text-only retrieval does not imply image, audio, video or referenced-post coverage.

## Current private preparation

The actual input has 37,082 source observations and 36,182 unique original URLs. There are 601 duplicate groups involving 1,501 source observations. The source differences affect 65 company groups, 67 account groups, eight body groups and one historical-label group. Publication dates agree within every group.

All 36,182 unique posts are prepared for collection counts. Of these, 36,163 have permitted post text for retrieval; eight body-disagreement groups and eleven text-quality observations remain outside retrieval. The private package is in `.runtime/decision_followup_20261006/social/admission_v1/`. Its `receipt.json` binds the original input, review-data version, exact D02/D03 events, canonical output and conflict members. Preparation is not a database import or deployment.

## Verified local application after review

The original v1 preparation above remains frozen. The first local import was atomically rolled back when strict sentence validation detected omitted source characters. A full preflight found 13 affected posts. A separately saved v2 changes only those posts' retrieval permission; their original bodies, observations and count eligibility are preserved.

On 6 October 2026, the local application imported **36,182 unique company posts**, with **36,150 retrievable and 32 paused**: eight body-conflict groups, eleven text-quality cases and thirteen strict-segmentation failures. All **37,082 observations** remain in the preserved source variants. An exact reimport created zero versions; every current payload and version matches the prepared v2. Native data, embeddings, classification results, answers and API budget entries remained unchanged.

The collection and CSV use company-post wording and explicitly unverified paid-ad status. Paused records remain countable; model tools expose only permitted metadata and the review reason. They do not return paused source text or source variants. Human record details can still show the supplied variants for review.

No model or embedding calls, remote writes or deployment were performed. The pre-import backup's table of contents was verified, but a full restore was not rehearsed. Paid-ad identity, client acceptance and actual image/video analysis remain pending. See [reviewed execution and evidence](decision_followup.zh-CN.md) and the [local verification receipt](../.runtime/decision_followup_20261006/decisions/local_import_verification.json).

## Repeat preparation

Use a new output directory. The tool will reject overwritten outputs, changed review-data versions, unconfirmed selections, duplicate source IDs or source-body hash drift.

```sh
python scripts/prepare_social_admission.py /private/unadmitted-records.jsonl \
  --review-data /private/review-data.json \
  --reviews /private/reviews.jsonl \
  --out .runtime/social-admission-next
```

This performs no database, model or network operations. Validate the generated canonical file with the existing loader:

```sh
python -m observatory.cli import-records .runtime/social-admission-next/records.jsonl \
  --dataset social --dry-run --out .runtime/social-admission-next/import-check.json
```

## Local import and rollback

Before importing, verify the prepared source/review/canonical hashes, the approved collection wording and the source-variant detail view. Save a verified database backup and a complete list of current social record IDs, active states and versions. Native metadata, current body versions, chunks, embeddings, classification tables and budget entries must be compared before and after the social import.

The ordinary reviewed local import uses **upsert**, preserving unrelated records:

```sh
python -m observatory.cli import-records .runtime/social-admission-next/records.jsonl \
  --dataset social --mode upsert --out .runtime/social-admission-next/local-import.json
```

Repeat the same import to verify idempotency. New canonical IDs are listed in `members.json`; the rollback must target only those actually introduced by this run. Preserve both imports and the source package. A rollback can deactivate only the new canonical IDs under the import lock, or restore the verified pre-import backup. Do not delete the 37,082 supplied observations, rewrite native records or run a dataset snapshot that retires unrelated records.

The default collection-level total counts unique posts once. Source company/account disagreements are unknown groups. Company affiliations are not paid sponsorship relationships. The detail projection exposes only permitted source text, company, account, publication date, original/archive URLs, source record references and historical states; local paths, complete raw JSON and generated explanations are not exposed.

## Validation boundary

The new policy and detail projections have 27 focused checks. Combined with existing detail and historical-label regressions, 80 offline checks pass, including unchanged native detail rendering. The private row reconciliation separately compares every source observation and every canonical group's membership and unresolved fields. These checks establish source preservation and deterministic policy behavior; they do not establish semantic classification quality, independent usability, verified paid-ad status or client acceptance.

See [the supplied social input](social_archive_input.md), [historical annotation limits](social_historical_annotations.md) and [current task status](../plan.md).

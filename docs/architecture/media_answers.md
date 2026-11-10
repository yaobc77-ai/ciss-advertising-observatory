# Media evidence in query answers

Checked against the local source on 6 October 2026. This describes an implemented
answer interface, not a deployed media service or a measured recognition result.

## What goes in and what comes out

**Input:** a question, the submitted collection filters, permitted current body
text, and any fixed media evidence package reviewed and configured by an operator.
The question cannot supply a file path or choose another package.

**Output:** a summary, findings, numbered supporting evidence and scope limits.
Body quotations and derived media excerpts have separate cards. Each media card
states the origin and quality note, links its source, and shows its supplied image
page/region or video segment.
An unknown page or time remains unknown. A supplied video segment does not imply
word-level alignment. Source links follow the application's link setting; local
file paths are not exposed. Hashes and derived-text offsets are collapsed under
**Technical details**.

When an answer cannot be supported, the page shows the status, reason and next
step. Any displayed retrieval candidates remain candidates, not findings.

| Evidence | What the label means |
| --- | --- |
| Original body / saved page text | Retained article or post text with original character positions. Saved page text is not a subtitle. |
| OCR text | Text extracted from an image, bound to that asset and location. It is not an original-body quotation. |
| Image description | A supplied human or model description of the image. It is not a direct quotation or proof of what the image means. |
| Publisher caption | Supplied caption text with its own source and segment. |
| Automatic caption / transcript | Derived speech text with the supplied segment; errors and unknown alignment remain visible. |
| Video description | A supplied human description of a video, with a supplied segment if available. |

Media snippets currently carry `image_or_speech_semantics_verified=false`.
There is no automatic semantic approval path. Finding a source excerpt does not
establish that the sponsor's claim is true.

## How a content question is answered

1. The web model interprets the question and selects the existing `search_records`
   tool. The submitted filters remain authoritative.
2. For each requested comparison target, the service reads permitted body text
   and the fixed media package. Body search combines keyword and vector results;
   image and video derived text use separate bounded lexical retrieval.
3. Current records, source versions, body ranges, package and asset hashes are
   checked. The results form one program-built numbered reference catalog.
4. The answer model selects those reference IDs and writes paraphrases. The
   program restores the exact source excerpts, evidence types and locations.
5. Chosen media evidence is checked again, including after generation. The UI
   renders original text and derived media separately with shared citation numbers.

This adds no new web tool. The standard MCP catalog still has **10** read-only
tools and the web model catalog **9**. Direct `get_media_evidence` remains
MCP-only; the web service performs its media reads internally. The reader itself
does not download media, perform recognition, call a model or change records.
Model interpretation and generation retain their existing budget accounting.

## What coverage means

Scope shows retrieved body passages, image/video units and actually cited source
records for each target. An uncited comparison target remains incomplete even
when its candidates were retrieved. A source can support several numbered
citations; evidence-unit counts are not advertisement counts.

**Cited coverage is a structural check.** It does not show that every paraphrase
is supported, that OCR or speech text is accurate, or that all matching ads were
found. Those require independent source and semantic review. A retrieval result
cannot replace the full-source review needed for the 24-question matching lists.

## Missing information and failures

| State | User-facing meaning |
| --- | --- |
| `not_configured` | No complete media configuration is available. Body evidence can still be considered. |
| `missing_material` | A valid package lacks the requested permitted media. |
| `no_match` | Available permitted media produced no lexical match for this query. |
| Source or evidence mismatch | The source changed, the selected reference no longer agrees, or the evidence identity is invalid. The affected answer is blocked. |
| Partial comparison | One or more requested targets has no usable or actually cited evidence. The answer must retain that limitation. |

None of the first three states proves that the original ad lacks the content.
An external search may supplement a permitted unresolved question under the
existing configuration and budget rules. It cannot hide a broken citation,
source change or media-integrity error, and outside sources do not enter counts.
Loading messages represent actual retrieval or generation stages, not simulated
internal reasoning.

## Configuration and current material

Media reads require all three operator-reviewed settings:
`OBS_MEDIA_BUNDLE_PATH`, `OBS_MEDIA_BUNDLE_SHA256` and `OBS_MEDIA_ASSET_ROOT`.
Setting them selects a fixed package; it does not approve source meaning,
perform recognition or authorize a paid run. Materials submitted through the
local review form remain pending until separately reviewed and packaged.

All three production settings remain **unconfigured**. Earlier real read-only
checks covered **six saved-page text assets and 23 retained text units**. These
are page text, not captions. Actual image OCR/recognition, captions and video
transcription remain **zero**. The local 26-source material form does not activate
those sources. Paused company-post bodies remain unavailable to media retrieval.

The earlier **628-file** source candidate predates this web answer change. Its
build/install receipts do not verify the new source. The new
[634-file source candidate](../data/media_source_candidate_20261006.md) was separately
extracted, built and installed outside the checkout: 613 selected engineering
checks passed, with three Windows link-test skips. Its exact bytes, final archive
comparison and same-machine limits remain in that candidate's own receipt.
This integration made no paid calls, business data or configuration changes,
remote publication or customer-acceptance decision.

## Local presentation review

Open the temporary [local media-answer preview](http://127.0.0.1:8071/) while the
review server is running. It replays synthetic typed answers, not real ads or a
live model response. The three controls show:

- **Both companies cited:** separate image-description and caption evidence,
  a shared numbered summary and cited coverage for both targets.
- **One company not cited:** a retrieved candidate remains visible, but the
  comparison reports that this target was not cited.
- **Source changed: answer withheld:** a controlled mismatch scenario displays
  a refusal instead of an answer or a substitute web finding.

The preview checks presentation only. It does not activate the media package or
perform recognition, paid calls, database/environment changes or publication.
Real OCR/captions/transcription remain zero; the three production settings remain
unconfigured. This temporary local page is separate from the deployed dashboard.

The [final engineering receipt](../../.runtime/media_web_answers_20261006/verification.json)
is local and private. The selected regression passed **496 engineering checks
across 22 test files**, with zero failures; source fingerprints
and the exact scope remain in that receipt and `selected-final.junit.xml` beside
it. Browser review checked the preview's three states. The local application
restart retained the prior health, data/index versions and counts. These checks
do not measure recognition, answer meaning or client acceptance. The preview
source is stored separately at `.runtime/media_web_answers_20261006/preview.py`.

## What remains to be reviewed

- Obtain actual images, descriptions, reliable captions or speech material and
  check source identity and supplied locations.
- Review the fixed package and operator configuration before using real media.
- Freeze the actual inputs, model, call/token limits, spending cap and stop rules
  for a new pilot; obtain separate execution authorization. The old text-only
  three-call plan is not authorization for this media path.
- Review recognition errors, attribution, negation, numbers and whether each
  paraphrase is supported. Keep independent test data separate from development.
- Freeze and reproduce the changed source, then separately approve publication
  and complete client acceptance. No current semantic performance score is supplied.

The user permits some transcription accuracy loss **for video efficiency only**.
This does not relax article/image quality or change the client requirements.

## Implementation and references

[Typed models](../../src/observatory/models.py),
[fixed media reader](../../src/observatory/media_reader.py),
[service](../../src/observatory/service.py), [reference validation](../../src/observatory/rag.py),
[prompts](../../src/observatory/prompts.py) and [UI checks](../../tests/test_media_answer_ui.py)
define the implementation. Controlled tests verify interfaces and refusal paths;
they do not measure real recognition or answer accuracy.

[OpenAI Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs)
constrains response structure; source and semantic checks remain separate.
The retained 6 October read-only mechanism audit considered LlamaIndex's
[multimodal overview](https://github.com/run-llama/llama_index/blob/main/docs/src/content/docs/framework/module_guides/models/multi_modal.md),
[multimodal retriever](https://github.com/run-llama/llama_index/blob/main/llama-index-core/llama_index/core/indices/multi_modal/retriever.py)
and [citation query engine](https://github.com/run-llama/llama_index/blob/main/llama-index-core/llama_index/core/query_engine/citation_query_engine.py).
These are design examples, not dependencies installed for this change or direct
replacements for the application's record/version and location checks. The saved
audit is private at `.runtime/delivery_followup_20261006/research/audit.json` and
`research/multimodal_web_route.md` in the same private follow-up directory.

See [system design](architecture.md), [user guide](../operations/guide.md),
[current handoff](../current_handoff.md) and [reviewed decisions](../evaluation/decision_followup.zh-CN.md).

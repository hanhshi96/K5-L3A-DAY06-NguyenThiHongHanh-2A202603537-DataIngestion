# Lab 06: API embedding retrieval experiment

Automatic results below are generated from actual runs. Manual assessment is pending unless completed in manual_review.csv.

## 1. Retrieval accuracy

|Strategy|Split|Hit@1|Evidence Hit@3|Filter compliance|

|---|---|---|---|---|

|A|dev|7/15 (46.7%)|11/15 (73.3%)|3/3|

|A|test|2/5 (40.0%)|5/5 (100.0%)|2/2|

|B|dev|7/15 (46.7%)|10/15 (66.7%)|3/3|

|B|test|2/5 (40.0%)|3/5 (60.0%)|2/2|

|C|dev|7/15 (46.7%)|10/15 (66.7%)|3/3|

|C|test|2/5 (40.0%)|3/5 (60.0%)|2/2|



Matching requires gold document/page and a full normalized quote inside one chunk. Whitespace is ignored; accents, punctuation and case are preserved. Human equivalent evidence may require adjudication; auto scores can underestimate valid paraphrases. Cross-chunk unions do not count as the required Hit@3.

## 2. Chunk coherence

Complete coherence rows in manual_review.csv using manual_evidence.md and source PDFs. Same ten fixed anchors across A/B/C. Score 0=cut/unclear, 1=partly understandable, 2=self-contained. If multiple chunks cover one anchor, score all and average within the anchor before averaging the ten anchors.

## 3. Metadata usefulness

Complete metadata rows for the five test queries × top-3 × three strategies. Enter metadata_correct as 1/0, verify source/page/language against PDF. Report correct/checked, not merely presence. Filter values are explicit user-language scopes supplied before search. Empty result sets fail filter compliance. A/B intentionally do not apply filters; C applies only supplied filters.

## 4. Grounding quality

Complete all 15 grounding rows: 0=no evidence, 1=incomplete/context missing, 2=sufficient and traceable. Report counts at 0/1/2 and mean /2 per strategy. Do not substitute automated Hit@3 for these labels. Student is the reviewer; disclose self-assessment bias.

## 5. Strategy impact

A: fixed 900 characters, overlap 150. B: paragraph grouping with 900-character maximum, whitespace fallback for long paragraphs. C: reuses exactly B chunks/vectors and applies language filter only when supplied. Same API model and exact cosine store. PDF paragraph structure may be weak, reducing the distinction between A and B.

Use metrics and ingestion_stats.json to compare A–B and B–C. C reuses B embeddings, so its incremental embedding cost is zero; do not interpret cache reuse as independent speed superiority.

## Scope and reproducibility

38 content pages: NĐ13 physical PDF pages 1–29; paper pages 1–9. Gold uses physical PDF page numbers, not printed Công báo numbers. 15 dev + 5 test fixed before runs. Questions/evidence were AI-assisted and require student review. Mixed legal/ML topics deviate from the suggested narrow topic and make filter benefits harder to demonstrate. Small test and shared topics across splits limit generalization.

NĐ13 is a historical snapshot and has ceased to be effective from 2026-01-01 under Article 42 of NĐ356/2025. Do not present answers as current legal advice.

Model text-embedding-3-small; dimensions explicitly 1536. UTF-8 input guard; no silent truncation. Query/document use same endpoint. Real API usage is recorded per invocation; no mocked vectors. API cost is not assumed zero: compute actual billed tokens using applicable account pricing. Cache reuse and retries may cause billing totals to differ from successful-response token counts.

Database table lab06_api_chunks; exact pgvector cosine. Upserts repeated and count-checked. Full current snapshot per document is supplied; stale chunks removed by store. Removed documents cleaned for each strategy. Original lab06_chunks is untouched.

See experiment_lock, manifest, runtime, run usage, traces and error log. Keep .env and cache out of public git. PDFs not included; use source URLs and checksums.

## Dev selection (predeclared rule)

Suggested by fixed dev-only rule: A. Test must not be used to change the configuration.

## Manual label completion (no imputation)

A coherence: 0/10 labeled with reason.

A grounding: 0/5 labeled with reason.

A metadata: 0/15 labeled with reason.

B coherence: 0/10 labeled with reason.

B grounding: 0/5 labeled with reason.

B metadata: 0/15 labeled with reason.

C coherence: 0/10 labeled with reason.

C grounding: 0/5 labeled with reason.

C metadata: 0/15 labeled with reason.
# Design

More depth (fallbacks, token accounting, MCP, scaling) is in [ARCHITECTURE.md](ARCHITECTURE.md).

## 1. Tables and the scanned document

`ingestion/pipeline.py` runs at startup in the background; `/health` returns 503 until it finishes.

Each loader turns its format into ordered blocks (heading, text, table):
- **PDF** (PyMuPDF): headings are lines that are bold and larger than the body text. Running headers and footers are dropped.
- **DOCX**: heading styles, with tables kept in document order.
- **HTML**: `h1`–`h4`, `p`/`li`, `table`.
- **Markdown**: `#` headings and pipe tables.

**Tables:** each cell is read by its bounding box, which keeps the word spacing that `Table.extract()` loses. The ONNX layout model is turned off so results are deterministic. Tables are stored as Markdown rows and kept whole inside a chunk; when a table must be split, its header row is repeated. The document-control table is skipped because the manifest already holds those values.

**Scanned pages:** a page with an image and no text layer is rendered at 200 dpi and read with RapidOCR (PP-OCR models on ONNX Runtime, CPU, models in the wheel). Its text boxes are rebuilt into lines and paragraphs, and low-confidence boxes such as a signature are dropped.

**Holidays:** `holidays.py` reads table rows that contain a date in any common format. Rows under a "restricted / optional" heading are stored as `restricted` and don't count as days off. Nothing is typed in by hand.

## 2. Chunking and retrieval

**Chunking:** one chunk per section (at most 380 tokens), prefixed with its heading path; the locator is the nearest heading. HR rules map to sections, so each rule stays next to its conditions and citations point at a section.

**Retrieval:** dense search (bge-small, Qdrant) and BM25 run side by side.
- Fusion: the top 3 of each retriever are always kept, and the rest are ranked by reciprocal-rank fusion. Plain fusion buried the OCR'd memo, whose embedding is diluted by header and signature text.
- At most 2 chunks per document, so v1, v2, the FAQ and the addendum can all reach the precedence step.

**Budget:** passages are packed until 3,000 `cl100k_base` tokens, counting headers. `call_llm` refuses any call over budget and logs `corpus_tokens`.

## 3. Section 5 rules

- **Eligibility** (`retrieval/eligibility.py`): the requester's role can read the document's access level, the region matches (or the document is GLOBAL), and `effective_date ≤ reference date`. It is applied as a Qdrant filter, so ineligible documents are never retrieved.
- **Reference date:** today in `APP_TIMEZONE`. A past date or year in the question ("in 2025") is detected in code (`orchestration/dates.py: past_reference_date`).
- **Precedence** (`retrieval/precedence.py`): the sort key is `(authority, scope, effective_date)`, compared in that order. That matches "move to the next test only if this one does not decide".
- **Flow:**
  1. The extract model only lists candidate values per rule.
  2. Code drops candidates whose main number is not in their passage, or whose passage does not mention the rule (`is_grounded`, `rule_matches_passage`).
  3. `resolve_rule` picks the winner. It reports a conflict only when different top-tier documents disagree; several values from one document are conditions, not a conflict.
  4. It reports an upcoming change only when the future document would win and changes the value.
- **Citations** come from winners and upcoming changes only, so overruled documents are never cited.
- **Not covered:** no facts gives `no_answer`; if only part of the question is covered, the answer says which part is missing.

## 4. Where access control is enforced

- **Identity:** `identity/auth.py` — `resolve_requester` (401), `check_session_owner` (403). UI and MCP tokens: `identity/tokens.py`.
- **Documents:** `eligibility.eligible_doc_ids` becomes the filter in `index.dense_search` / `lexical_search`; `search._search` checks it again. Restricted documents never become evidence, a citation or a trace entry.
- **Leave data:** `tools/permissions.can_view_employee` and `ToolContext._check_target`, which also allows at most one other employee per message.
  - `get_team_leave` requires the manager role.
  - `apply_leave` / `cancel_leave` act only on `ToolContext.employee`; `execute_proposal` checks who owns the proposal.
  - The sandbox, the REST dashboards (`api/app_routes.py`) and MCP (`mcp_server.py`) all call these same functions. The model never supplies identity.
- Unknown and forbidden employees get the same refusal.

## 5. Personal data

- **Logs and traces:** `observability/pii.scrub_for_logs`, run as a structlog processor and on span attributes, replaces names, emails and phones with employee IDs. Prompt bodies are not written to logs.
- **Prompts:**
  - The planner gets IDs, role, region, level and dates only — no names.
  - The compose step gets the requester's first name, to address them.
  - Tool results never contain email or phone.
- **Answers and tool-call arguments:** `mask_for_user` masks emails, strips phone numbers and hides names the requester may not see.

## 6. Failure modes found

| Failure | Status |
|---|---|
| `Table.extract()` dropped spaces, which broke date parsing | Fixed: read cells by bounding box |
| ONNX layout model crashed under memory pressure | Fixed: line-based detection |
| FAQ and v1 contradict v2; restricted holidays counted as days off | Fixed: precedence; `restricted` kind |
| Model assumed "annual", including from an earlier unrelated question | Fixed: leave type taken only from the current request |
| Extractor invented values; a rate table read as a conflict | Fixed: grounding check; values by condition |
| Wrong service tier; forgotten `as_of`; month name treated as ambiguous | Fixed: computed in code; prompt rule |
| Scanned memo lost in rank fusion | Fixed: per-retriever top-3 |
| NIM 503s and timeouts | Fixed: fallback chain, hedged requests, deadline with a saved trace |
| Answer contains numbers that are in no source | Detected and traced, not blocked (results of calculations are legitimate) |

## 7. At 10,000 documents

**What breaks first:**
- Startup ingestion (OCR plus embeddings on every boot) misses the 10-minute health window.
- The in-memory BM25 index stops fitting.

**Fixes:**
- Incremental ingestion keyed by content hash, a persistent Qdrant collection, and an ingestion worker queue. Health then means "serving", not "fully re-indexed".
- Sparse vectors in Qdrant instead of in-memory BM25.
- Payload indexes on `access_level` / `regions` / `effective_date` instead of a doc-ID list.
- Document families, so superseded versions are pruned before ranking.
- A cross-encoder reranker to keep the 3,000-token budget precise.

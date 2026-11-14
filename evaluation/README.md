# OpsPilot evaluation

Everything here is reproducible from the repository. No number in a report is entered by hand:
`evaluation/run.py` measures it, stores it in the database (`evaluation_runs`, `evaluation_results`)
and writes it to `evaluation/reports/`.

## Dataset v1 (synthetic)

- **Corpus:** 24 Markdown documents in `datasets/v1/corpus/`: runbooks, architecture notes,
  troubleshooting guides, deploy notes and 8 past incident reports for 7 fictional services.
  All content is invented for this project; there is no real company data.
- **Questions:** 100 in `datasets/v1/questions.jsonl`, generated from `build_questions.py`
  (the source of truth). Each lists the document sections that contain its answer.

| Kind | Count | Stresses |
|---|---|---|
| lexical | 28 | exact error codes and identifiers (`PAY_GATEWAY_502`, `SQLSTATE 40P01`) |
| semantic | 44 | paraphrased symptoms with little word overlap |
| multi | 8 | answers spread over two sections |
| unanswerable | 20 | not covered by the corpus; the right behaviour is to abstain |

- **Split:** 30 questions are for **tuning** (used to choose settings) and 70 are **test**
  (held out, reported). Settings are never chosen by looking at test results.
- **Hash:** each run records a SHA-256 of the corpus and questions, so results from different data
  can't be mixed up.

## Retrieval metrics

Relevance is binary at **section level**: a retrieved chunk counts if it comes from an expected
document and its section path ends with the expected heading. Several chunks from one section get
credit once for recall/nDCG (each still counts for precision). Unanswerable questions are excluded.

- **Recall@k**: share of expected sections found in the top k.
- **Precision@5**: share of the top 5 chunks that are relevant.
- **MRR**: mean of 1 / rank of the first relevant chunk.
- **nDCG@k**: rank-discounted gain, normalised by the best possible ranking.
- **Latency**: wall-clock per query on this machine, including query embedding (and reranking).

Configurations compared on identical data and code:

| Label | Retrieval |
|---|---|
| A_lexical | PostgreSQL full-text search (`ts_rank_cd`), **not BM25** |
| B_vector | pgvector cosine similarity, `bge-m3` embeddings |
| C_hybrid_rrf | A and B fused with Reciprocal Rank Fusion (k = 60) |
| D_hybrid_rrf_rerank | C, then `BAAI/bge-reranker-base` cross-encoder over the top 30 |

## Answer metrics

Run with `--answers`; uses hybrid retrieval and the local LLM (`opspilot-qwen3-8b`).

- **Abstention accuracy**: answers answerable questions and abstains on unanswerable ones.
- **Citation precision**: share of an answer's citations that point to an expected section.
- **Citation coverage**: share of answered questions with at least one correct citation.
- **Expected-fact match**: every expected key phrase appears in the answer (a strict string match; it
  under-counts correct paraphrases).
- **Faithfulness is not measured yet.** There is no LLM judge or human grading of every answer, so this
  metric is deliberately absent rather than estimated.

## Running

```bash
uv run --project backend python evaluation/run.py --split tune      # choose settings here
uv run --project backend python evaluation/run.py --split test      # report these
uv run --project backend python evaluation/run.py --answers --split test
```

Runs can also be queued from the dashboard (`POST /api/v1/evaluations/run`).

## Limitations

- The corpus is small (24 documents), synthetic and written by the same author as the questions, so
  scores are optimistic and say little about a real knowledge base.
- 70 test questions give wide uncertainty: one question changes Recall@5 by about 1.8 points.
- Section-level labels are judged by one author; a few related sections could also be counted relevant.
- Latency was measured on one Apple Silicon laptop with all services local.

## Tuning log

| Date | Split | What | Result | Reports |
|---|---|---|---|---|
| 2026-11-14 | tune | All configs A–D, RRF k = 60 | baseline | `reports/20261114-061412-retrieval-tune.*` |
| 2026-11-14 | tune | C_hybrid_rrf with RRF k = 10, 30, 60, 100 | identical metrics (MRR 0.865 for every k). Top-10 order changed for 28/30 questions, but only within the same sections. k stays 60 | `reports/20261114-0617{06,11,17,22}-retrieval-tune.*` (k is in each JSON `config.rrf_k`) |
| 2026-11-14 | test | All configs A–D, k = 60 (reported) | see the root README | `reports/20261114-061751-retrieval-test.*` |

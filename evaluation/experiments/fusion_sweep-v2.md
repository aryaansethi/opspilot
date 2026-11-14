# Fusion sweep on dataset v2, TUNE split (57 answerable questions)

## Diagnosis

- Lexical (OR) returns 30.0 of 50 possible candidates per question on average: almost every chunk shares some word with a natural-language question, so the lexical list is long and noisy.
- First relevant chunk: lexical ranks it higher in 10 questions, vector in 17, tie in 30; lexical misses it entirely in 0.
- In 14 questions vector has the right chunk at rank 1 but lexical does not. Equal-weight RRF gives both lists the same vote, so a confident vector rank 1 can be pushed down by lexical noise.

## Variants (k = 60 throughout; vector weight 1.0)

| Variant | Recall@5 | MRR | nDCG@10 |
|---|---|---|---|
| RRF k=60 lexical=OR w_lex=0.5 depth=10 **(selected)** | 0.930 | 0.823 | 0.860 |
| RRF k=60 lexical=AND-first w_lex=0.5 depth=10 | 0.930 | 0.823 | 0.860 |
| RRF k=60 lexical=OR w_lex=0.5 depth=20 | 0.921 | 0.821 | 0.859 |
| RRF k=60 lexical=AND-first w_lex=0.5 depth=20 | 0.921 | 0.821 | 0.859 |
| RRF k=60 lexical=OR w_lex=0.35 depth=10 | 0.912 | 0.819 | 0.857 |
| RRF k=60 lexical=AND-first w_lex=0.35 depth=10 | 0.912 | 0.819 | 0.857 |
| RRF k=60 lexical=OR w_lex=0.5 depth=50 | 0.921 | 0.819 | 0.853 |
| RRF k=60 lexical=AND-first w_lex=0.5 depth=50 | 0.921 | 0.819 | 0.853 |
| RRF k=60 lexical=OR w_lex=0.25 depth=10 | 0.912 | 0.819 | 0.859 |
| RRF k=60 lexical=AND-first w_lex=0.25 depth=10 | 0.912 | 0.819 | 0.859 |
| RRF k=60 lexical=OR w_lex=0.75 depth=10 | 0.930 | 0.818 | 0.857 |
| RRF k=60 lexical=AND-first w_lex=0.75 depth=10 | 0.930 | 0.818 | 0.857 |
| RRF k=60 lexical=OR w_lex=0.75 depth=20 | 0.912 | 0.817 | 0.856 |
| RRF k=60 lexical=AND-first w_lex=0.75 depth=20 | 0.912 | 0.817 | 0.856 |
| RRF k=60 lexical=OR w_lex=0.75 depth=50 | 0.912 | 0.817 | 0.855 |
| RRF k=60 lexical=AND-first w_lex=0.75 depth=50 | 0.912 | 0.817 | 0.855 |
| RRF k=60 lexical=OR w_lex=0.35 depth=20 | 0.904 | 0.817 | 0.855 |
| RRF k=60 lexical=AND-first w_lex=0.35 depth=20 | 0.904 | 0.817 | 0.855 |
| RRF k=60 lexical=OR w_lex=0.35 depth=50 | 0.904 | 0.815 | 0.847 |
| RRF k=60 lexical=OR w_lex=0.25 depth=50 | 0.904 | 0.815 | 0.846 |
| RRF k=60 lexical=OR w_lex=0.25 depth=20 | 0.904 | 0.815 | 0.846 |
| RRF k=60 lexical=AND-first w_lex=0.35 depth=50 | 0.904 | 0.815 | 0.847 |
| RRF k=60 lexical=AND-first w_lex=0.25 depth=50 | 0.904 | 0.815 | 0.846 |
| RRF k=60 lexical=AND-first w_lex=0.25 depth=20 | 0.904 | 0.815 | 0.846 |
| vector only (B) | 0.912 | 0.812 | 0.846 |
| RRF k=60 lexical=OR w_lex=1.0 depth=10 | 0.930 | 0.806 | 0.848 |
| RRF k=60 lexical=AND-first w_lex=1.0 depth=10 | 0.930 | 0.806 | 0.848 |
| RRF k=60 lexical=OR w_lex=1.0 depth=20 | 0.912 | 0.805 | 0.847 |
| RRF k=60 lexical=AND-first w_lex=1.0 depth=20 | 0.912 | 0.805 | 0.847 |
| RRF k=60 lexical=OR w_lex=1.0 depth=50 | 0.912 | 0.805 | 0.847 |
| RRF k=60 lexical=AND-first w_lex=1.0 depth=50 | 0.912 | 0.805 | 0.847 |
| lexical AND-first only | 0.930 | 0.737 | 0.782 |
| lexical OR only (A) | 0.930 | 0.728 | 0.776 |

Selected by highest MRR (then nDCG@10) among fusion variants: **RRF k=60 lexical=OR w_lex=0.5 depth=10**.
This selection uses only the tune split; the test split is evaluated afterwards as config E.

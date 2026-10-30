# LLM-as-judge rubric (fixed judge model: `JUDGE_MODEL`)

The judge receives the task, the project files and the implementation prompt, and returns an integer **1-5** per criterion.
Deterministic checks (invented paths, answers recorded with the wrong source label, missing choices, unlabeled mocks, CLI input robustness, bounded loops) are NOT judged
by the LLM - they are asserted in `tests/` and reported as columns by `compare_models.py` (`invented_paths`, `verified`, `open_items`...).
A confident but unsupported brief must score low on `factual_accuracy`.

| Criterion | 5 | 3 | 1 |
|---|---|---|---|
| **relevance** | Prepares this exact task: context, dependencies, tests, risks. | Partly generic or drifts into writing the implementation. | Off-topic or just code. |
| **factual_accuracy** | Every file/API/technology/convention exists in the project files; unknowns are marked UNKNOWN. | A few unsupported claims. | Invented paths/APIs, or assumptions stated as facts. |
| **completeness** | All sections A-G present; sources of every finding, chosen decisions, mock limits and open items explicit. | Several sections thin or missing. | Most missing. |
| **format** | Clean Markdown, sections in order, concise, explicit instructions to the implementing AI. | Readable but out of order / verbose. | Unstructured. |
| **scope_control** | Nothing beyond the task; no new architecture/dependency without evidence. | Some unjustified additions. | Large silent scope expansion. |
| **assumption_handling** | Every assumption/mock/open decision labeled; unresolved decisions never written as final instructions. | Some labeled, some implicit. | Unknowns presented as settled facts. |

Return JSON: `{"relevance":n,"factual_accuracy":n,"completeness":n,"format":n,"scope_control":n,"assumption_handling":n,"comment":"<one sentence>"}`.
Time is measured automatically; cost is computed from tokens x pricing.

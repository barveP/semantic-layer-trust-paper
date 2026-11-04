> Historical protocol draft. The completed study and final methods are reported in `paper/paper.pdf`.

# When the semantic layer is wrong: accuracy and trust of data agents (protocol draft v0.2)

**Status: draft, 31 October 2026. Nothing has been run against a model, no API money has been spent and nothing is frozen.** v0.2 replaces v0.1 as the working draft.

## What changed from v0.1, and why

| Change | Reason |
|---|---|
| Data are TPC-DS SF1 generated with DuckDB `dsdgen` in `SLSTUDY.TPCDS_SF1`, not `SNOWFLAKE_SAMPLE_DATA` | Size (decision record). The data are deterministic: two independent generations matched |
| Detection is scored in two tiers, D1 and D2, and both are also scored on the correct layer | Models often notice a conflict without locating it (literature pass, row 13); false alarms need a denominator |
| New arm **E**, the layer with only the faulted element removed | Makes "wrong vs missing" (RQ2) a like-for-like comparison; comparing with C0 mixes in the value of the rest of the layer (literature row 14) |
| New **named-suspect** audit arms (secondary block) | Separate "could not detect" from "did not look" (literature row 15) |
| **Discriminability gate**: a (question, fault) pair is used only if the faulty gold result differs from the correct gold result on the data | Otherwise the fault is invisible in the answer (literature row 10). It already removes one operator: see the next row |
| The fiscal vs calendar operator is redefined as a **fiscal-year definition** fault in a derived field | In TPC-DS SF1, `d_fy_year = d_year`, `d_fy_quarter_seq = d_quarter_seq` and `d_fy_week_seq = d_week_seq` on all 73,049 `date_dim` rows (checked 31 October), so the v0.1 version would never change a result |
| New **value-mapping** operator (wrong literal for a category or flag) | One of the natural evidence-error types reported for BIRD (literature row 9) |
| Structured `concerns[]` objects | Detection can then be scored by deterministic code |
| Pre-registered directional hypotheses; resampling by question **and** by fault operator | Literature rows 4 and 13 |

## 1. Research questions

- **RQ1 (value).** How much accuracy does the correct layer add over the DDL alone? Secondary: which Ossie constructs carry the gain?
- **RQ2 (harm).** Is a wrong element worse than a missing one (F vs E), and is a wrong layer worse than no layer (F vs C0)?
- **RQ3 (silent failure).** When the layer is wrong, how often does the agent follow it and raise no layer-directed concern? Does it matter whether the fault can be seen by reading (F2, contradictory) or not (F1, coherent)?
- **RQ4 (cost of skepticism).** Does an audit instruction raise detection, and at what cost in false alarms and accuracy on a correct layer?

**Pre-registered directions** (checked, not assumed): H1, fault-faithful rate F1 > F2. H2, accuracy E > F1. H3, the generic audit raises D2 on F2 and raises D1 false alarms on C1.

## 2. Data, layer and questions

- **Data.** 24 TPC-DS tables at SF1 in `SLSTUDY.TPCDS_SF1`. Load receipt: `data/TPCDS-SF1-LOAD-RECEIPT.json`, once loaded. Sales years are 1998–2003.
- **Layer.** Ossie `examples/tpcds_semantic_model.yaml` at `2fd19c7a`, sha256 `c6bdcaaf…`: five datasets, four relationships, eight metrics. The `source` fields are rewritten to `SLSTUDY.TPCDS_SF1.<table>` and the diff is recorded. Additions needed by the operators (a fiscal-year field, a "preferred customer" segment, synonyms) are added to the *correct* layer first. Every arm sees the same correct base.
- **Questions.** 24 business-style questions, each anchored on exactly one layer element that one operator will change. Each of the six operators gets four questions.
- **Gold answers.** Each question has two independently written gold queries, which must agree on SF1, plus a faulty-gold query that applies the faulty definition.
- **Discriminability gate.** If the faulty-gold result equals the correct-gold result, the pair is replaced and the replacement is logged.

## 3. Fault operators

The faults are mechanical edits to the YAML, and each has a known faulty answer.

| Operator | Example on this layer | F1, coherent | F2, contradictory |
|---|---|---|---|
| Metric-formula drift | `total_sales` uses `ss_net_paid` instead of `ss_ext_sales_price` | Expression and description changed together | Expression changed; description still says extended sales price |
| Hidden scope filter | A metric silently restricted to one year or one store state | The filter is also stated in the description | Description still says "all sales" |
| Synonym mis-mapping | "revenue" listed as a synonym of `total_profit` | `total_sales` no longer lists it | `total_sales` still lists it |
| Fiscal-year definition | `fiscal_year` defined with the wrong start month | Description states the wrong start month | Description states the right start month |
| Wrong relationship key | Customer join on `ss_addr_sk` instead of `ss_customer_sk` | Relationship description matches | Description names the customer key |
| Value mapping | "Preferred customers" mapped to `c_preferred_cust_flag = 'N'` | Description says 'N' | Description says 'Y' |

A *loud* control, a reference to a column that does not exist, separates silent from loud failure. Some F1 faults may be given away by column names in the DDL, or detected through remembered TPC-DS conventions. This is analysed as a threat, not prevented.

## 4. Arms

Every arm uses the same neutral system prompt unless marked.

| Block | Arm | The agent sees |
|---|---|---|
| Primary (all 24 questions) | C0 | DDL of the five layer tables |
| | C1 | DDL + correct layer |
| | E | C1 with the anchored element removed |
| | F1, F2 | C1 with the question's fault, coherent or contradictory |
| | C1+A, F1+A, F2+A | The same, plus "check the layer against the DDL before answering; report concerns" |
| Secondary (12 questions, 2 per operator) | C1+N, F1+N, F2+N | Audit that names the anchored element as suspect |
| | C1a, C1b | C1 without metrics; C1 without descriptions and `ai_context` |

**Agent output.** One JSON object with these fields:
- `sql`
- `assumptions[]`
- `concerns[]`: each concern is `{target: "layer"|"question"|"data"|"other", object: <identifier or null>, text}`
- `confidence`

Agents are single-turn and have no execution tool. A tool-using loop is a phase-2 option.

**Models.** As in v0.1: `claude-opus-5-5@high`, `gpt-6.1-sol@high` and `claude-haiku-5-5@medium`, each subject to an access probe.

## 5. Outcomes and grading (frozen before the pilot's scored trials)

**Answer class.** Each trial is classed by deterministic result-set comparison:
- correct: matches the correct gold;
- fault-faithful: matches the faulty gold;
- other-wrong;
- execution error.

Comparison rules: row order is ignored unless the question asks for a ranking; decimals use a relative tolerance of 1e-9; column names are ignored. Extra columns are allowed only when the gold columns appear as a subset, a rule frozen with the grader.

**Detection.**
- **D1, layer concern:** at least one concern with `target = "layer"` whose `object` names an identifier that exists in the layer. Concerns that name no identifier ("the layer may be outdated") do not count.
- **D2, located concern:** `object` equals the mutated identifier, case-insensitive, allowing a `dataset.field` qualification.
- **False alarm:** D1 on C1, C1+A or C1+N.

**Silent failure.** Fault-faithful with no D1 concern, reported with two denominators: all faulty trials, and fault-faithful trials.

**Human audit.** A human reads a 20% random sample of concerns, stratified by arm, to check the validity of D1 and D2. Any model judge is a separate, labelled sensitivity analysis.

**Analysis.** Comparisons are paired by question, with bootstrap intervals resampled by question and, separately, by fault operator. A mixed-effects logistic model with a question random effect is a check. `confidence` is descriptive only. With 24 questions the intervals will be wide, and the write-up says so. Null and negative results are reported.

## 6. Cost and envelopes

Per-call figures are carried over from v0.1: about 7K input and 3–6K output tokens per call, roughly $0.13 for Opus, $0.06 for Sol and $0.003 for Haiku, or about $0.19 per question-arm across the three models. **The pilot replaces these estimates with measured usage.**

| Stage | Size | Calls | Estimate | Proposed envelope |
|---|---|---|---|---|
| Pilot | 12 questions × {C0, C1, F1, F2, F2+A} × 3 models × 1 rep | 180 | about $12 | **$20** |
| Main | (24 × 8 primary + 12 × 5 secondary) × 3 models × 2 reps | 1,512 | about $97 (Anthropic about $67, OpenAI about $30) | **$170** overall: Anthropic at most $120, OpenAI at most $55 |
| Snowflake | A few thousand queries on SF1, XS warehouse | — | 1–2 credits | Resource monitor at 5 credits |

The main envelope is re-set after the pilot. The ledger reading and the cap discrepancy in v0.1 section 5 still need to be resolved at gate 1.

## 7. Gates before any paid call

1. The envelope is adopted in a versioned amendment under the standing API authority.
2. Model-access probes pass.
3. Questions, gold queries, faulty-gold queries, fault YAMLs, prompts and the grader are hashed and frozen.
4. **The discriminability gate passes for every pair.**
5. Offline infrastructure tests with a fake provider pass. These are infrastructure tests, not results.
6. The Snowflake connection check passes: the read-only user cannot write and its session cap is 120 s.

## 8. Safety and isolation

Unchanged from v0.1 section 6. The executor container runs agent SQL as `SLSTUDY_USER` (SELECT only, 120 s cap, IP-restricted) and accepts a single `SELECT`/`WITH` statement after a `sqlglot` parse. The dispatcher holds the API keys and never the Snowflake key.

## 9. Threats to validity

These are declared in advance:
- One public schema, which models may partly remember.
- 24 questions.
- Injected faults. A natural-fault check on the BIRD items that Jin et al. corrected, scored against the original wrong evidence (literature row 10), is a phase-2 option.
- The same authors write the layer additions, the faults and the gold queries.
- Single-turn agents.
- A draft Ossie spec (0.2.0.dev0).
- Results describe prompting an LLM with a model file, not any vendor's semantic engine.
- The literature pass was done by a model and had limited reach (literature section 6).

## 10. Next steps

1. Load the data and pass gate 6.
2. Write the layer additions and the 24 questions with gold and faulty-gold queries; run the discriminability gate.
3. Build the executor container, the grader and the fake-provider tests.
4. Write the funding amendment and run the access probes.
5. Freeze, then run the pilot.

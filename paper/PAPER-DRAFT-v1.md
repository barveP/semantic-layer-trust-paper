> Historical draft, superseded by `paper.tex` and `paper.pdf`.

# When the Semantic Layer Is Wrong: Do LLM Data Agents Follow or Flag Faulty Business Definitions?

*Draft v1, 31 October 2026. Every number is taken from generated files:*
- *`results/main-ANALYSIS.json`, rendered in [RESULTS-main.md](RESULTS-main.md) and `results/main-TABLES.md`;*
- *`results/main-RQ2-WRONG-VS-NONE.json`;*
- *`results/pilot-g1.1-ANALYSIS.json`.*

*The detection rule was checked against the author's labels on 417 sampled concerns, giving `results/main-HUMAN-AUDIT-AGREEMENT.json` (2 November 2026; §3, §6). Nothing here has been submitted or published.*

## Abstract

Semantic layers make LLM data agents more accurate, but published benchmarks assume the layer is correct. We injected 24 controlled, typed faults into an Apache Ossie semantic model over TPC-DS, covering six kinds:
- metric formula;
- hidden filter;
- synonym;
- fiscal calendar;
- join key;
- value mapping.

Each fault came in two forms: *coherent*, where the documentation agrees with the fault, and *contradictory*, where only the definition changes. We measured whether three frontier models follow the fault or flag it, over 1,512 single-turn trials scored by deterministic execution against Snowflake.
- **A correct layer helps:** accuracy rose from 60–71% without a layer to 100% with one, for every model.
- **Coherent faults were followed in 46–73% of trials**, and a coherent wrong element left agents **less accurate than having no layer at all** (−26 points, 95% CI −43 to −9).
- **Contradictory faults were flagged almost always (92–100%)** but still followed in 4–33% of trials.
- **Agents often flagged a fault and then followed it anyway.**
- **A generic "audit the layer first" instruction did not reliably reduce following**, and it raised concerns on the correct layer by 17 points.

What predicts following is whether the fault clashes with something the agent can see:
- wrong join keys whose column names give them away were never followed;
- plausible business definitions, such as a fiscal-year start, were always followed.

## 1. Introduction

LLM data agents increasingly answer business questions through a semantic layer instead of raw tables. Examples include dbt's semantic layer, Snowflake Cortex Analyst semantic models, Cube, and Apache Ossie (incubating), a vendor-neutral YAML format formerly called the Open Semantic Interchange. A semantic layer defines what "revenue", "fiscal year" or "preferred customer" mean, how tables join, and which words are synonyms.

The case for semantic layers rests on comparing an agent with a correct layer against one without. Layers are maintained by hand, however, and they drift. A layer is dangerous when it is wrong *because* it is authoritative: an agent that follows a wrong definition writes a query that runs and returns a plausible number.

We ask:
- **RQ1:** How much does a correct layer help?
- **RQ2:** Is a wrong element worse than a missing one, or than no layer at all?
- **RQ3:** When the layer is wrong, do agents follow it silently? Does it matter whether the fault can be seen by reading?
- **RQ4:** Does asking agents to audit the layer help, and what does it cost?

## 2. Related work

The literature record covers 28 primary sources, was read by a model, and had three claims spot-checked.

- **Semantic layer vs raw schema** (arXiv 2604.25149, 2606.31041, 2608.26157, 2608.09254). Every one of these studies assumes the layer is correct. 2604.25149 defines "silent hallucination" but does not measure it. 2608.09254 notes that an error in a metric definition can escape both of its checks.
- **Wrong evidence in text-to-SQL.** SEED (arXiv 2506.07423) finds incorrect evidence in 105 of 1,534 BIRD dev pairs. Jin et al. (arXiv 2601.08778) correct external knowledge in 17 of 100 examples. Both measure the effect on accuracy of naturally occurring errors, not following versus flagging.
- **Robustness benchmarks.** Dr.Spider, EvoSchema and SAGE perturb the question or the schema; R-NL2SQL formalises documentation but never perturbs it.
- **Silent failure.** DiscRun-Bench scores caveats separately from correctness.
- **Knowledge conflicts.** Models follow coherent counterfactual context, and they notice conflicts more often than they locate them (arXiv 2403.08319).
- **Documentation errors in code.** Incorrect docstrings hurt models more than missing ones (arXiv 2404.03114).

As far as our search reached, no study injects controlled, typed faults into a semantic layer and measures both following and flagging, or contrasts coherent faults with contradictory ones.

## 3. Method

The full protocol is [PROTOCOL-DRAFT-v0.2](../PROTOCOL-DRAFT-v0.2.md). Changes made after the pilot are in [POST-PILOT-AMENDMENT-01](../operations/POST-PILOT-AMENDMENT-01.md).

**Data and execution.**
- TPC-DS SF1 is generated deterministically with DuckDB `dsdgen` and loaded into Snowflake. All 24 tables were verified column by column.
- Agent SQL runs in an isolated container, as a read-only key-pair user with a 120 s statement cap. A `sqlglot` check first confirms the input is a single SELECT.

**Layer.**
- The base is the Ossie TPC-DS example at revision `2fd19c7a`, with these logged edits:
  - sources retargeted;
  - three metric descriptions made explicit about their formulas;
  - fields, metrics and synonyms added for the fault operators;
  - two conflicting synonyms removed;
  - one fan-out error in the example's `store_productivity` fixed. It divided by a sum of employee counts over joined sales rows.
- All 75 layer files validate against Ossie's JSON schema.

**Questions and faults.**
- 24 business questions, four per operator, each anchored on one layer element.
- Each fault has two forms:
  - **F1, coherent:** the descriptions are edited to agree with the fault;
  - **F2, contradictory:** only the expression, mapping or join changes.
- Every pair passes a discriminability gate: the faulty definition changes the answer on the data.
- Gold queries were written twice. The second set came from a separate model that saw only the questions, the layer and the DDL. The two sets agree on 24 of 24 questions, and DuckDB and Snowflake return identical results.

**Arms.**

| Arm | Shown to the agent | Questions |
|---|---|---|
| C0 | DDL only | 24 |
| C1 | DDL + correct layer | 24 |
| E | Correct layer with the anchored element removed | 24 |
| F1, F2 | Faulty layer (coherent, contradictory) | 24 |
| C1+A, F1+A, F2+A | Plus "check the semantic model against the table definitions and the question" | 24 |
| C1+N, F1+N, F2+N | Plus an instruction naming the anchored element as suspect | 12 |
| C1a / C1b | Correct layer without metrics / without descriptions and `ai_context` | 12 |

**Agents.**
- Models: Claude Opus 5.5 (high effort), GPT-6.1 Sol (high reasoning) and Claude Haiku 5.5 (medium), with 2 repetitions each.
- 1,512 trials in total.
- Single turn, with no tools.
- The system prompt is identical across arms. It says the organization maintains a semantic model, but tells the agent neither to trust it nor to verify it.
- Output is one JSON object with `sql`, `assumptions`, structured `concerns` and `confidence`.

**Outcomes.** All are computed by deterministic code frozen before dispatch.
- Answer classes:
  - correct: equal to the gold result, including forms the layer's descriptions license;
  - followed: equal to the faulty definition's result;
  - other wrong;
  - no usable answer.
- **D1:** a layer-targeted concern that names something in the layer.
- **D2:** a D1 concern that names the faulted element.
- **Silent failure:** followed, with no D1 concern.
- **Concern on the correct layer:** D1 on C1.

**Human check of the detection rule.** The author labelled a 20% sample of concerns, stratified by arm: 417 concerns from 376 trials. Labelling was blind to the rule's output and to the model. Each concern got two labels: whether it is about the semantic layer, and, when a fault was planted, whether it identifies that fault. Intervals are bootstrapped over trials.
- **D1:** 94.5% agreement, κ = 0.89 [0.85, 0.93]. The rule's precision is 0.995 [0.98, 1.0] and its recall 0.90 [0.86, 0.94].
- **D2,** on the 219 concerns from fault arms: 95.4% agreement, κ = 0.90 [0.84, 0.96]. Precision and recall are both 0.96, with 5 errors in each direction.

**Analysis.** Each pre-registered comparison is paired by question:
- H1: following, F1 > F2;
- H2: correct, E > F1;
- H3a: D2, F2+A > F2;
- H3b: D1, C1+A > C1.

Intervals are 95% cluster-bootstrap intervals over questions (10,000 resamples), with an operator-cluster sensitivity analysis and a logistic GEE check. Comparisons added after the pilot are labelled exploratory (X1–X5).

**Pilot.**
- The pilot ran 180 trials for $4.02 and found two benchmark defects, both fixed before the main run:
  1. The TPC-DS source flag `d_weekend = 'Y'` marks Fridays and Saturdays, so Q22 was redesigned.
  2. TPC-DS injects NULLs independently into derived columns, so formulas computed from component columns are now accepted as equivalent.
- Main-run cost: $36.41 for 1,512 trials, all completed with none invalid. Total model spend for the study: $40.44.

## 4. Results

The numbers below come from [RESULTS-main.md](RESULTS-main.md) and `results/main-TABLES.md`. Figure 1 is `results/figures/main-outcomes.png`. Arms marked N, C1a and C1b use the 12-question subset.

### RQ1: a correct layer helps

| | Claude Opus 5.5 | GPT-6.1 Sol | Claude Haiku 5.5 |
|---|---|---|---|
| No layer (C0) | 71% | 62% | 60% |
| Correct layer (C1) | 100% | 100% | 100% |

The pooled difference is **+35 points [+19, +53]** (X4). Without a layer, agents miss business definitions they cannot infer: the fiscal calendar, apparel categories, the store-size threshold, the meaning of "preferred". Removing only the anchored element (E) keeps most of the benefit for the rest of the question: E − C0 = +7 [+1, +15].

### RQ2: a wrong element is worse than a missing one, and worse than none

| | Claude Opus 5.5 | GPT-6.1 Sol | Claude Haiku 5.5 |
|---|---|---|---|
| Element removed (E) | 79% | 69% | 67% |
| Coherent fault (F1) | 52% | 23% | 42% |

- **H2 is supported:** E − F1 = **+33 points [+18, +48]**. The result holds under operator clusters [+11, +54] and under GEE (p < 0.001).
- Against **no layer at all**, a coherent wrong element is also worse: C0 − F1 = **+26 points [+9, +43]**, or +19, +19 and +40 for Opus, Haiku and Sol. This comparison is named in the protocol's RQ2, without a pre-registered direction.
- A contradictory fault is not worse than no layer: C0 − F2 = −19 [−40, +2].

### RQ3: coherent faults are followed, often silently, sometimes knowingly

Faults followed:

| | Claude Opus 5.5 | GPT-6.1 Sol | Claude Haiku 5.5 |
|---|---|---|---|
| Coherent (F1) | 46% | 73% | 56% |
| Contradictory (F2) | 4% | 33% | 12% |

- **H1 is supported:** F1 − F2 = **+42 points [+27, +56]**, consistent across models (+42, +40, +44). It holds under operator clusters [+18, +69] and GEE (p < 0.001).
- **Silent failure** on F1, as a share of trials: Opus 23%, Sol 52%, Haiku 17%.
- **Flag-and-follow.** Many followed faults were flagged in the same response. On F1 this was:
  - Haiku: 19 of 27 followed trials;
  - Opus: 11 of 22;
  - Sol: 10 of 35.

  On F2, Sol flagged the contradiction in 12 of its 16 follows. Agents frequently wrote "this definition looks wrong" and then used it anyway. Typical wording was "I follow the governed metric".
- **By operator** (pooled, F1 followed / silent):

  | Operator | Followed | Silent |
  |---|---|---|
  | Wrong join key | 0% | 0% |
  | Synonym | 50% | 17% |
  | Formula drift | 54% | 17% |
  | Hidden filter | 71% | 29% |
  | Value mapping | 75% | 54% |
  | Fiscal-year definition | 100% | 67% |

  Faults that clash with visible schema semantics are caught. Joining `ss_addr_sk` to `c_customer_sk` gives itself away by name. Faults that look like plausible business decisions are followed: a July fiscal start, a 240-employee threshold, which categories count as apparel.

### RQ4: asking for an audit adds concerns, not correctness

- **H3a is not supported:** located detection on F2 is already at ceiling (92–100%). The audit changes it by −1 point [−4, +1].
- **H3b is supported:** the audit raises concerns on the *correct* layer by **+17 points [+5, +29]**:

  | | Claude Opus 5.5 | GPT-6.1 Sol | Claude Haiku 5.5 |
  |---|---|---|---|
  | C1 | 23% | 2% | 35% |
  | C1+A | 52% | 6% | 52% |

  Operator clusters give [+4, +29] and GEE gives p = 0.011.
- **Exploratory:** the audit barely reduces *following*.
  - X1, F2 − F2+A: +3 [−1, +9]. Sol gains most (+17), Haiku gets slightly worse (−6).
  - X2, F1 − F1+A: +3 [−3, +8].
- Naming the suspect element (F1+N) raises located detection on coherent faults. D2 is 88% for Opus, 92% for Sol and 62% for Haiku. Agents still followed the fault in 42–58% of those trials.
- **Caveat on "concerns on the correct layer".** These are not all false alarms. The objects flagged most often on C1 are:
  - `total_profit`: our description gives the component formula, while the expression uses the derived column;
  - `customer_lifetime_value` and `average_ticket_value`: genuine definitional choices;
  - `i_brand`: the official example lists "manufacturer" as a synonym for brand.

  The human check labelled whether a concern is about the layer, not whether it is justified, so separating substantive concerns from noise is still open.

## 5. Discussion

- **The danger is coherence, not error.** Agents are good at spotting a definition that disagrees with its own documentation or with the schema. They are poor at spotting one that is internally consistent and plausible as a business choice. That is the realistic failure mode: a layer updated on purpose but wrongly, or for one report and never reverted.
- **Concerns are not a safety mechanism on their own.** Flag-and-follow means a concern can sit beside a wrong number. Any pipeline that shows the number and hides the concern turns a detected fault back into a silent one. Products built on semantic layers should surface concerns as first-class output, or refuse to answer when the agent's own concern names the element it used.
- **Prompting for skepticism is a weak lever.** A generic audit instruction mostly made agents talk more, not answer better. Naming the suspect helped detection but not correction. Checking a *coherent* fault needs evidence outside the layer: data profiles, tests, reconciliation queries. This points to two things:
  - tool-using agents that can test a definition against the data, the most direct follow-up;
  - semantic layers that carry their own **assertions**, for example "total_sales for 2001 reconciles with the finance ledger", which a format like Ossie could standardise.
- **Model differences.**
  - GPT-6.1 Sol was the most compliant: it followed most often and most silently.
  - Claude Opus 5.5 was the most skeptical, and also raised the most concerns when asked to audit.
  - Claude Haiku 5.5 flagged often but followed anyway.
- **For Ossie specifically.** Building the benchmark surfaced two problems in the official example:
  - a metric whose plain-SQL reading double-counts under joins;
  - a misleading synonym ("manufacturer" for brand).

  A linter that checks descriptions against expressions, and flags model-scoped metrics with ambiguous join paths, would have caught these and the contradictory faults studied here.

## 6. Threats to validity

- **Scale.** 24 questions on one public schema, so models may know TPC-DS conventions. The intervals are wide and question-level. The 12-question subset arms are smaller still.
- **The faults are injected, not natural.** Plausibility is argued, not measured. One author wrote the layer additions, the faults and gold A. Gold B was written by a model. The Q22 redesign and the equivalence grading were changed after the pilot, before the main run, and both are documented.
- **Our base layer has imperfections.** Some descriptions do not match their expressions exactly (for example `total_profit`), which raises concerns on the correct layer. The base-layer edits are logged in `tasks/layers-v1.1/MANIFEST.json`.
- **Detection is rule-based and conservative.** Against the author's labels the rule almost never over-counts D1: precision 0.995. It misses about one layer concern in ten, and two kinds account for almost all the misses:
  - concerns that the layer *lacks* a definition, which name no layer identifier;
  - layer concerns filed under the question or the data.

  Misses are concentrated in arm E, where D1 agreement is 78%. D1 rates are therefore lower bounds, especially for E. D2 errors are balanced. Free-text concerns that do not use the structured `object` field are not counted.
- **The human check has limits.**
  - It used one rater.
  - On Q13–Q16 the rating page showed only the `fiscal_year` change, although the fault also changed `fiscal_quarter`. This affects 34 concerns. Without them, D2 agreement is unchanged at κ = 0.90.
- **Agents are single-turn, with no tools,** so the results do not describe agents that can query the data.
- **The literature pass was done by a model** and had limited reach.
- **One more statistical caveat.** The GEE check is degenerate for X4, because every model scores 100% on C1.

## 7. Reproducibility

- Every input, prompt, plan, grader and analysis script is hashed in [FREEZE-PILOT](../operations/FREEZE-PILOT.json) and [FREEZE-MAIN](../operations/FREEZE-MAIN.json).
- Raw responses are kept in the ignored `local/slstudy-runs/`, and the graded trials are in `results/main-trials.jsonl`.
- The data are regenerable with `harness/load_tpcds_sf1.py`.
- To regenerate every number: `run/grade.py main` → `run/analyze.py main` → `paper/build_results.py main`.

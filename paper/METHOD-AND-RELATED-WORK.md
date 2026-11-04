> Historical draft, superseded by `paper.tex` and `paper.pdf`.

# Paper draft, part 1: motivation, related work, method (written before results)

*Draft, 31 October 2026. Written while the pilot ran, before any main-run result existed. Results sections are generated from `results/` by code; no number in this file depends on a result.*

## 1. Motivation

Semantic layers are increasingly the interface between LLM data agents and warehouses:
- dbt's semantic layer;
- Snowflake Cortex Analyst semantic models;
- Cube;
- Apache Ossie (incubating), formerly the Open Semantic Interchange, a vendor-neutral YAML format.

The evidence that they help compares an agent **with** a layer against one **without**. In those benchmarks the layer is assumed correct. In practice, layers are maintained by hand and drift: a metric is redefined, a filter is added for one report, a synonym is copied to the wrong metric, a join key is mistyped. A wrong layer is dangerous because it is authoritative. An agent that follows it writes a query that runs, returns a plausible number and gives no sign of trouble.

We ask what agents do when the layer is wrong:
- Do they follow it, or notice?
- Does it matter whether the error can be seen by reading the layer?
- Is a wrong element worse than a missing one?
- What does asking the agent to check the layer cost in false alarms?

## 2. Related work

The full record covers 28 primary sources, model-read, with three claims spot-checked.

- **Semantic layer vs raw schema.** These studies all assume a correct layer:
  - Rumiantsau & Fokeev (arXiv 2604.25149): a paired benchmark over three models. They define "silent hallucination" but do not measure it.
  - QUVI (arXiv 2606.31041).
  - GROUND (arXiv 2608.26157).
  - Lee (arXiv 2608.09254), which notes that an error in a metric definition can escape both of its checks.
- **Wrong evidence in text-to-SQL.** BIRD's evidence field is a small semantic layer. SEED (arXiv 2506.07423) finds incorrect evidence in 105 of 1,534 BIRD dev pairs (6.84%), and correcting it raises accuracy. Jin et al. (arXiv 2601.08778) correct external knowledge in 17 of 100 examples. Both measure accuracy only, on naturally occurring and untyped errors; neither asks whether models follow or flag the error.
- **Robustness benchmarks.** Dr.Spider, EvoSchema and SAGE perturb the question or the schema, preserving meaning or changing the database itself. None plants a wrong definition over unchanged data. R-NL2SQL (arXiv 2603.17017) formalises auxiliary documentation but does not perturb it.
- **Silent failure and caveats.** DiscRun-Bench scores correctness and caveats separately. Agents almost never surfaced documentation/data format mismatches: 18 of 19 and 18 of 18 runs missed them.
- **Knowledge conflicts.** LLMs readily follow coherent, convincing context that conflicts with what they know, and often notice a conflict without locating it (survey, arXiv 2403.08319).
- **Code documentation.** Incorrect docstrings hurt code understanding more than missing ones (Macke & Doyle, arXiv 2404.03114). This is the closest precedent for "wrong is worse than missing".

**Contribution, as narrowed by the literature pass.** We found no study that injects *controlled, typed* faults into a semantic layer and measures both *following* (the agent's result equals the faulty definition's result) and *flagging* (a structured concern that names the faulted element). We also found none that contrasts faults whose documentation agrees with them against faults whose documentation contradicts them.

## 3. Method

**Data and engine.**
- TPC-DS at scale factor 1, generated deterministically with DuckDB's `dsdgen` and loaded into Snowflake.
- All 24 tables were verified column by column against the generator's checksums.
- Agents write Snowflake SQL. The SQL runs in an isolated container, as a read-only user with a 120 s statement cap, after a single-SELECT parse check.

**Semantic layer.**
- The base is the Apache Ossie TPC-DS example at revision `2fd19c7a`, with the following logged edits:
  - sources retargeted;
  - descriptions made explicit about formulas;
  - fields, metrics and synonyms added for the fault operators;
  - two conflicting synonyms removed;
  - one fan-out error in the example's `store_productivity` metric fixed.
- All 75 layer files validate against Ossie's JSON schema.

**Questions and faults.**
- 24 business questions, four for each of six fault operators:
  - metric-formula drift;
  - hidden scope filter;
  - synonym mis-mapping;
  - fiscal-year definition;
  - wrong relationship key;
  - wrong value mapping.
- Each question is anchored on one layer element. Its fault has two forms: **F1, coherent**, where descriptions are edited to agree with the fault, and **F2, contradictory**, where only the expression or mapping changes.
- Every (question, fault) pair passes a **discriminability gate**: the faulty definition changes the answer on the data.
- Gold answers were written twice, independently (the second by a separate model that saw only the questions, the layer and the DDL). The two agree on 24 of 24, and the result sets are identical on DuckDB and Snowflake.

**Arms.**

| Arm | The agent sees |
|---|---|
| C0 | DDL only |
| C1 | DDL + correct layer |
| E | Correct layer with the anchored element removed |
| F1, F2 | Faulty layer, coherent or contradictory |
| +A | Plus a generic instruction to check the layer against the DDL and the question |
| +N | Plus an instruction naming the anchored element as suspect |
| C1a / C1b | Correct layer without metrics / without descriptions and `ai_context` |

**Agents.** Claude Opus 5.5 (high effort), GPT-6.1 Sol (high reasoning) and Claude Haiku 5.5 (medium effort). Each answers in a single turn with one JSON object: `sql`, `assumptions`, structured `concerns` (`target`, `object`, `text`) and `confidence`. The system prompt is identical across arms. It says that the organization maintains a semantic model and neither tells the agent to trust it nor to verify it.

**Outcomes.** All are scored by deterministic code frozen before dispatch.
- **Answer:**
  - correct: the result equals the gold result;
  - fault-match: the result equals the faulty-definition result;
  - other wrong;
  - no usable answer.
- **D1:** a concern targeted at the layer that names something in the layer shown.
- **D2:** a D1 concern that names the faulted element, an identifier the fault changed, or the moved synonym.
- **Silent failure:** a fault-match with no D1 concern.
- **False alarm:** D1 on a correct layer.

**Analysis.** Rates by model × arm. Pre-registered paired comparisons, all by question:
- H1: fault-match F1 > F2.
- H2: correct E > F1.
- H3a: D2 F2+A > F2.
- H3b: false alarms C1+A > C1.

Intervals come from a cluster bootstrap over questions (10,000 resamples), with a sensitivity bootstrap over operators and a logistic GEE check.

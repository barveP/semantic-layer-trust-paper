# Sources and revisions read for the semantic-layer study (31 October 2026)

Primary sources are marked **P**; secondary, vendor or aggregator sources are marked **S** and are not used for any quantitative claim without checking the primary.

| | Source | What was read | Revision / date |
|---|---|---|---|
| P | https://github.com/apache/ossie | README, `core-spec/spec.md`, `examples/tpcds_semantic_model.yaml` (shallow clone, read only, not executed) | `2fd19c7a40b360bb87c18e8e0b7db482684b220a`, committed 2026-10-30. Core spec v0.2.0.dev0, "Draft"; previous release 0.1.1. Apache-2.0. README title "Apache Ossie (incubating)", formerly Open Semantic Interchange |
| P | https://github.com/apache/ossie-converters | Directory listing; `snowflake/README.md` | `46c673d18dd23e6c424798d952d7fd97496fd0cf`, 2026-10-30. Converters exist for snowflake (Cortex Analyst YAML, offline), dbt, cube, databricks, gooddata, honeydew, hex, omni, polaris, salesforce, sigma, thoughtspot and others. The snowflake README says it is under active development and not thoroughly tested |
| P | https://github.com/dbt-labs/dbt-llm-sl-bench | Cloned for reading (ACME DDL, questions, `run_bench.py`) | `a29f2429b1bb38cee9d591892299e96f1e197ff9`, 2026-08-10 |
| S | https://docs.getdbt.com/blog/semantic-layer-vs-text-to-sql-2026 | Benchmark design and numbers (11 questions × 20 runs, ACME Insurance, 15 tables; Sonnet 4.6 text-to-SQL 90.0% vs semantic layer 98.2%; GPT-5.3 Codex 84.1% vs 100.0%). Vendor-authored; grading procedure not documented on the page | accessed 2026-10-31 |
| P | https://arxiv.org/abs/2604.25149 | Abstract only (Rumiantsau and Fokeev, submitted 28 April 2026): Contoso retail in ClickHouse, 100 questions, schema vs schema + 4 KB markdown document, three models; +17 to +23 points. Hallucination definition, grading and limitations not yet read | accessed 2026-10-31 |
| S | Snowflake blog "Open Semantic Interchange (OSI) updates: specification live" (snowflake.com) and the Atlan article on Cortex Analyst vs custom text-to-SQL | Search snippets only. The "57% to 78%" BIRD figure is attributed to Snowflake by Atlan and was not found in the Snowflake post; **do not cite** | — |
| S | everydev.ai listing of Apache Ossie | Rename claim; **confirmed** against the primary README above | — |

## Claims deliberately not made

- No claim that the study's question is novel. Only abstracts and blogs were read; the literature pass is milestone 1 of the protocol.
- No claim from practitioner blogs about how often semantic layers go stale. They motivate the fault taxonomy; they are not prevalence data.
- Some figures in the web-search summaries (for example the description of Anthropic's internal analytics agent) were second-hand and were not verified against a primary post.

> Historical preparation notes. Completed results and current reproduction commands are in the root README.

# Task material for the wrong-layer study (draft v1, 31 October 2026)

**Not frozen.** These files are preparation for [protocol v0.2](../PROTOCOL-DRAFT-v0.2.md). No model has seen them and no API money has been spent. The gates below ran on a local DuckDB copy of the same TPC-DS SF1 data that goes into Snowflake. They will be repeated on Snowflake once access works.

| File | What it is |
|---|---|
| [questions-v1.yaml](questions-v1.yaml) | The 24 questions, four per fault operator. Each has the anchored element, `gold_a` (the correct answer), `faulty_gold` (the answer from faithfully following the faulted layer), the fault edits, the element removed in arm E, and the identifiers that count as "located" (D2) |
| [questions-text-v1.yaml](questions-text-v1.yaml) | Question texts only, with no SQL, for the independent second gold writer |
| [ddl-five-tables.sql](ddl-five-tables.sql) | DDL of the five tables the layer covers; this is what arm C0 shows |
| [build_layers.py](build_layers.py) | Builds the base layer `layers/C1.yaml` from the Ossie example and the 72 per-question arm layers (`layers/Qnn/{E,F1,F2}.yaml`). It validates every file against Ossie's JSON schema and checks that the arms differ |
| [layers/MANIFEST.json](layers/MANIFEST.json) | Input hashes (Ossie revision, example, schema, questions, builder), the list of base-layer edits and a sha256 for every layer file |
| [results.py](results.py) | Result-set comparison: row order and column order ignored, numbers within 1e-9 relative. The grader will reuse it |
| [gate_local.py](gate_local.py) | Discriminability gate (`faulty_gold` must differ from `gold_a`) and gold-agreement gate (`gold_b` must equal `gold_a`) |
| `gold-b-v1.yaml` | Independent second gold queries, written by a separate model agent that saw only the question texts, `C1.yaml` and the DDL |
| [gates/](gates/) | Gate receipts |

## Base layer: the edits made to the Ossie example

The edits are listed in [layers/MANIFEST.json](layers/MANIFEST.json) (`base_layer_edits`) and made in code in `build_layers.py`. In summary:
- Sources are rewritten to `SLSTUDY.TPCDS_SF1`, and the vendor `custom_extensions` are dropped.
- Three metric descriptions now state their formula, so that a contradictory (F2) fault can be seen by careful reading.
- Fields, metrics, synonyms and relationship instructions are added where the operators need them: fiscal calendar, weekend, preferred customer, apparel, store size, item class, net sales, gross profit, average ticket value, distinct customers.
- Two conflicting synonyms are removed.
- **One error in the official example is fixed.** `store_productivity` divides by `SUM(store.s_number_employees)` over joined sales rows. In plain SQL this repeats each store's employee count once per sale (fan-out), so the denominator is inflated by the number of sales rows. The base layer uses `MAX` per store group instead.

  Ossie's own `core-spec/relational_semantics.md` §10.3 says model-scoped metrics have no home relation and their join path is left to each query. The example's metric is a concrete case of that hazard. Leaving it in would have turned honest concerns on the correct layer into "false alarms". This is a candidate upstream fix to the Ossie example; nothing has been submitted.

The example also has ambiguous synonyms that were **left in place**, and no question depends on them: "price" (on both `ss_sales_price` and `i_current_price`) and "location" (on both `ss_store_sk` and `s_city`).

## Gate results so far (local DuckDB, preparation only)

- **Discriminability: 24 of 24 pass.** Receipt: [gates/GATE-LOCAL-20261031.json](gates/GATE-LOCAL-20261031.json). The size of the change varies widely. Weekend sales, for example, go from 291.3M to 727.9M when the flag is inverted. Five faults change the answer by about 0.1–0.8%: Q05, Q13, Q15, Q16 and Q17. These are subtle faults, discriminable only under exact grading.
- **Gold agreement: 24 of 24.** The independent `gold-b-v1.yaml` was written independently by a separate LLM that read only the question texts, `C1.yaml` and the DDL. All 24 of its result sets equal gold A's. Receipt: [gates/GATE-LOCAL-20261031-with-gold-b.json](gates/GATE-LOCAL-20261031-with-gold-b.json); discriminability passes again in the same run.
- **Ambiguities the second writer flagged.** They are recorded in the `notes` fields of `gold-b-v1.yaml`. Two readers agreeing does not prove there is no ambiguity. One change was made: the base description of `customer_lifetime_value` now says that sales with no customer are excluded, because an agent could reasonably include them in the numerator. Gold B was written against the earlier base layer (C1 sha256 `ebd26ac7…`); the current one is `ce195c8a…`. The change only spells out what both gold queries already do. The other flags are left as they are, each with its reasoning:
  - Q17 excludes NULL birth years.
  - Q19 and Q20 store names are unique among the stores that have sales.
  - Q14's fiscal quarter comes out as a double in DuckDB; comparison is numeric.
  - Q07's "January to March" is calendar, as the question says.

## Known limits of this draft

- One author wrote the questions, gold A, the faults and the layer additions.
- Gold B is a second *model*, not a human.
- The fault "plausibility" is argued, not measured.
- Some F1 faults can be given away by DDL column names, for example `ss_addr_sk` in Q17 and Q18. This is declared in protocol v0.2 section 3.

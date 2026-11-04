# Post-pilot amendment 01 (31 October 2026): before any main-run call

The pilot ran 180 calls (12 questions × C0, C1, F1, F2, F2+A × 3 models × 1 rep): 180 of 180 completed, $4.02 actual. The materials it used are frozen in [FREEZE-PILOT.json](FREEZE-PILOT.json) and kept unchanged:
- `tasks/questions-v1.yaml`, `tasks/layers/`, `run/prompts/` and `run/plans/`;
- the original grades in `results/pilot-trials.jsonl`.

Reviewing the pilot's actual outputs found two defects in the **benchmark**, not in the models. Both are fixed as new versioned files for the main run. The pilot is reported under both the original grading and the amended grading.

## 1. Q22 redesigned (question set v1.1)

**Finding.** In TPC-DS SF1 the source flag `d_weekend = 'Y'` marks **Fridays and Saturdays**; in 2001, Friday 52 and Saturday 52 are 'Y', Sunday 52 is 'N'.
- The v1 base layer defined `is_weekend` as `d_weekend = 'Y'`, so the layer called "correct" was itself semantically wrong for "weekend".
- On that correct layer, Claude Opus flagged it in the pilot ("TPC-DS generated data can set this flag on days that are not Saturday and Sunday") and filtered by day name, which was scored "other wrong".

**Change (v1.1).**
- **Base layer:** `is_weekend = d_day_name IN ('Saturday', 'Sunday')`, described as "True when the date falls on a Saturday or Sunday".
- **Fault:** trust the source flag, `d_weekend = 'Y'`. F1 says so in the description; F2 keeps the day-name description. This is a realistic value-mapping fault.
- **Gates for v1.1 on Snowflake:** discriminable (292.4M vs 727.9M), gold agreement and cross-engine all pass for all 24 questions ([GATE-SNOWFLAKE-20261031-v1.1.json](../tasks/gates/GATE-SNOWFLAKE-20261031-v1.1.json)).
- **Q22's second gold query** in `gold-b-v1.1.yaml` (ISO day of week) was written with the benchmark, not by the independent writer.

**Effect.** All 74 context files that contain `is_weekend` change between `run/prompts/` and `run/prompts-v1.1/`. Nothing else in the prompts changes. Rebuilding v1 reproduces the pilot's layers byte for byte.

## 2. Grading amendment 01 (description-licensed equivalent forms)

**Finding.** TPC-DS injects NULLs into each column independently:
- 97,425 `store_sales` rows have `ss_net_profit` but lack `ss_net_paid` or `ss_ext_wholesale_cost`;
- 96,998 rows have `ss_ext_sales_price` but lack `ss_quantity` or `ss_sales_price`.

Where every input is present, `ss_ext_sales_price = ss_quantity × ss_sales_price` and `ss_net_profit = ss_net_paid − ss_ext_wholesale_cost` exactly.

In the pilot, five agents saw the contradictory Q02 fault, repaired `total_profit` from its description ("net amount paid … minus the extended wholesale cost") and were scored "other wrong", only because of those NULLs. The five are Q02 F2 and F2+A for Opus and Haiku, and F2+A for Sol.

**Change.** `run/grade.py --grading v1.1` (the default from now on) also runs every gold and faulty-gold query with those two licensed substitutions, in every combination:
- **correct** = the result equals any correct form;
- **fault_match** = the result equals any faulty form.

The grader stops if any correct form equals any faulty form; none does.

**Effect on the pilot.** Exactly those five trials change, from other_wrong to correct. Nothing else changes. Results: `results/pilot-g1.1-*`. The fake-provider test passes under both gradings.

## 3. Exploratory comparisons added (labelled as such)

The pilot showed located detection (D2) at ceiling on the contradictory fault: every model flagged it in all 12 cases. Some agents still *followed* the fault they had flagged (GPT-6.1 Sol: 6 of 12). The pre-registered H3a (D2 under audit) therefore cannot move. Added before the main run and reported as **exploratory**, separately from H1–H3b:
- X1, following F2 vs F2+A;
- X2, following F1 vs F1+A;
- X3, silent F1 vs F1+A;
- X4, correct C1 vs C0;
- X5, correct E vs C0.

## Not changed

- System prompt and arm list.
- Models and reps.
- Detection rules (D1, D2, silent).
- The other 23 questions and their faults.
- The envelope: pilot cost was $4.02, so the main run is projected at about $34, well inside $170.

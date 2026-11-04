# Human audit of the detection rule (about 1–2 hours)

**Easiest way:** rate on the Layer Audit page (see `../audit-site/README.md`). It holds the same 417 concerns and saves each answer as you go. Press Finish at the end. The CSV route below works too.

The grader decides automatically whether an agent's concern counts as:
- **D1**, a concern about the semantic layer, and, if so,
- **D2**, a concern that identifies the planted fault.

This audit checks those decisions against a person's judgement on a 20% random sample of concerns, stratified by arm. It is the protocol's only human measurement. Rate **without** looking at the grader's columns first.

**File:** `results/main-HUMAN-AUDIT-SAMPLE.csv`. It is generated after the main run. `results/pilot-g1.1-HUMAN-AUDIT-SAMPLE.csv` is a small pilot version you can use to warm up.

For each row:
1. Read:
   - the question;
   - the planted fault, or "no semantic layer shown", or "none (correct layer)";
   - the agent's concern: its target, object and text.
2. **RATER_about_semantic_layer:** `yes` if the concern is about the semantic model (a metric, field, relationship, synonym or description in it). Otherwise `no`.
3. **RATER_identifies_planted_fault:**
   - `yes` if the concern points at the specific element that was faulted, or at what is wrong with it;
   - `no` if it does not;
   - `na` if no fault was planted.
4. **RATER_note** is optional. Note anything odd, for example a concern that is right about a *different* real problem.

Hide or ignore the last two columns (`grader_d1_counted`, `grader_d2_counted`) while rating. They are compared with your answers afterwards to estimate agreement.

Keep the filled-in copy out of Git, in `local/`. For ratings made on the page, `audit-site/intake.py` reads the page's export and computes the agreement.

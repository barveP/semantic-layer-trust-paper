# Layer Audit

The annotation key is `results/main-HUMAN-RATINGS.csv`: Poorva Barve's two judgments and note for each of the 417 sampled concerns. Item and trial identifiers join it to `results/main-HUMAN-AUDIT-SAMPLE.csv`.

Regenerate agreement statistics from the published annotations:

```bash
python3 audit-site/intake.py
```

The script checks completeness, unique item identifiers, trial identifiers and answer applicability before computing agreement, Cohen's kappa, precision and recall. Its 10,000 bootstrap resamples keep concerns from the same trial together. The report also includes a sensitivity analysis excluding Q13-Q16.

## Annotation interface

The optional browser interface contains the question, the concern, and the changed definition alongside the reference definition. It includes no automatic labels, trial identifiers, model names or arm names. On fiscal questions, both changed fields are shown. The original sample CSV described only `fiscal_year`; the published notes also identify changes to `fiscal_quarter`.

```bash
python3 audit-site/build_site.py
python3 -m http.server 8000 --directory local/slstudy-audit-site/v1
```

Open `http://localhost:8000`. Answers and notes save in the current browser's local storage, scoped to the item list. Export ratings produces a portable CSV with the sample checksum. To analyze a completed export:

```bash
python3 audit-site/intake.py --ratings human-ratings.csv
```

The exported annotations are independent of the automatic labels. Keep the completed author key separate from the interface when collecting new blinded judgments.

## Browser checks

```bash
pip install playwright
python3 -m playwright install chromium
python3 audit-site/build_site.py
python3 audit-site/qa_site.py
```

The checks use synthetic answers to exercise keyboard entry, edits, notes, reload persistence, CSV export and mobile layout. Their artifacts stay under the ignored `local/` directory.

# When the semantic layer is wrong

Do LLM data agents follow or flag faulty business definitions? This study injects controlled faults into an [Apache Ossie](https://github.com/apache/ossie) model over TPC-DS and scores SQL execution results against Snowflake.

The paper is [paper/paper.pdf](paper/paper.pdf), built from [paper/paper.tex](paper/paper.tex). This repository contains the publication artifact. The original experiment was completed before this artifact was assembled; the Git history records its import and subsequent revisions.

## Findings

- On 24 benchmark questions, a correct layer raised accuracy from 60-71% to 100%.
- Coherent faults were followed in 46-73% of trials. Pooled accuracy was 26 percentage points lower than with no layer (95% CI, 9-43).
- Contradictory faults were located in 92-100% of trials, yet followed in 4-33%.
- Some responses raised a located concern about a faulted definition and still used it. A general concern about a different metric is reported separately.
- A generic audit instruction raised concerns on the reference layer by 17 percentage points, without a clear reduction in following.
- Author annotations of 417 sampled concerns gave agreement with the rule of kappa = 0.89 for D1 and 0.90 for D2.

The pilot used 180 trials ($4.02); the main experiment used 1,512 trials ($36.41). Coherent policy changes may be indistinguishable from valid business conventions using the supplied context alone. The experiment measures reliance against fixed reference definitions in a single-turn, tool-free setting.

## Reproduce the paper outputs

Use Python 3.12 and the pinned requirements. The distributed SQL, concerns and author annotations are sufficient to regenerate the publication statistics without model or Snowflake calls.

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python3 reproduce.py
```

To compile the PDF as well, install Tectonic or a TeX distribution with latexmk and IEEEtran:

```bash
python3 reproduce.py --pdf
```

The manuscript includes the repository URL, page numbers and PDF title/author metadata. The statistical table omits the separated logistic fit for X4; the question-cluster bootstrap is the primary analysis.

## Human annotations

[results/main-HUMAN-RATINGS.csv](results/main-HUMAN-RATINGS.csv) contains the author's judgments and note for all 417 items. Item and trial identifiers link these annotations to [the sampled concerns](results/main-HUMAN-AUDIT-SAMPLE.csv). Regenerate agreement with:

```bash
python3 audit-site/intake.py
```

The annotation interface is optional and runs locally; see [audit-site/README.md](audit-site/README.md). The author key is kept separate from the blinded page.

## Artifact layout

| Path | Contents |
|---|---|
| [PROTOCOL-DRAFT-v0.2.md](PROTOCOL-DRAFT-v0.2.md) | Historical protocol: outcomes, arms, directions and gates |
| [operations/](operations/) | Original freeze records, receipts and setup templates |
| [data/](data/) | TPC-DS DDL and local/Snowflake load receipts |
| [harness/](harness/) | Connections, loader and isolated SQL executor |
| [tasks/](tasks/) | Questions, faults, reference queries, layers and gate receipts |
| [run/](run/) | Prompts, frozen plans, grader, analysis and artifact validation |
| [results/](results/) | Graded trials, derived statistics and author annotations |
| [paper/](paper/) | Final PDF, source, tables, figure and historical drafts |
| [provenance/](provenance/) | Sources and original revisions |

Earlier Markdown manuscripts are retained as historical drafts. The PDF and its LaTeX source are the current paper.

## Experiment reruns and frozen inputs

A full rerun additionally requires generated TPC-DS data, a Snowflake account, the executor image and an external LLM dispatcher. The dispatcher and its model adapters are not distributed; `run/dispatch_sl.py` documents the required interface. Credentials and unparsed responses are excluded.

The original plans contain archived workspace paths. Resolve them into a separate local plan while checking every prompt hash:

```bash
python3 run/prepare_plan.py run/plans-v1.1/main.jsonl local/main-plan.jsonl
```

The original `FREEZE-MAIN.json` and `FREEZE-PILOT.json` describe the experiment inputs at run time. They are historical records rather than manifests of this revised publication artifact. Before this copy, seven source files had already changed in paths, comments or wording: the prompt builder, grader, dispatcher wrapper, layer builder, v1.1 questions, v1.1 second gold queries and post-pilot amendment. The pilot record also predates the v1.1 amendment. An envelope file and two external dispatcher modules listed in the freezes are not included.

Publication revisions add the author annotation key, portable annotation tools, explicit D1/D2 reporting, a separation guard, reproducible RQ2 comparisons, validation and manuscript improvements. The graded trials, questions, layers and frozen prompt/plan contents are preserved. The current artifact manifest lists the distributed file hashes; it does not establish an independent preregistration date.

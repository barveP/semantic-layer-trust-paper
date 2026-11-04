"""Figure and tables for the LaTeX paper, built from the main-run results.

  python3 paper/build_assets.py

Writes paper/figures/outcomes.pdf and paper/tables/*.tex. Every number in the tables comes from
results/main-ANALYSIS.json, results/main-RQ2-WRONG-VS-NONE.json and
results/main-HUMAN-AUDIT-AGREEMENT.json; the figure is drawn from results/main-trials.jsonl.
"""
import json
import pathlib
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

PAPER = pathlib.Path(__file__).resolve().parent
ROOT = PAPER.parent
RES = ROOT / "results"
sys.path.insert(0, str(ROOT / "run"))
from figures import CATS, MODELS, category  # noqa: E402

ARMS = ["C0", "C1", "C1a", "C1b", "E", "F1", "F2", "C1A", "F1A", "F2A", "C1N", "F1N", "F2N"]
SHORT = {"opus": "Opus", "sol": "Sol", "haiku": "Haiku"}
OPERATORS = [("formula_drift", "Formula drift"), ("hidden_filter", "Hidden filter"), ("synonym", "Synonym"),
             ("fiscal_definition", "Fiscal definition"), ("relationship_key", "Relationship key"),
             ("value_mapping", "Value mapping")]


def label(arm):
    """C1A -> C1+A, F2N -> F2+N; other arm names unchanged."""
    return arm[:-1] + "+" + arm[-1] if arm[-1] in "AN" and len(arm) == 3 else arm


def pct(x):
    return f"{round(100 * x)}\\%"


def pts(x):
    v = round(100 * x)
    return f"$+{v}$" if v > 0 else f"${v}$"


def ci(c):
    lo, hi = (round(100 * v) for v in c)
    f = lambda v: f"+{v}" if v > 0 else str(v)  # noqa: E731
    return f"[{f(lo)}, {f(hi)}]".replace("-", "$-$")


def p_value(p):
    return "--" if p is None else "$<0.001$" if p < 0.001 else f"{p:.3f}"


def figure(trials):
    plt.rcParams.update({"font.size": 7, "pdf.fonttype": 42, "font.family": "DejaVu Sans"})
    fig, axes = plt.subplots(1, 3, figsize=(7.1, 3.3), sharey=True)
    for ax, (model, title) in zip(axes, MODELS):
        for y, arm in enumerate(ARMS):
            sub = [t for t in trials if t["model"] == model and t["arm"] == arm]
            left = 0.0
            for key, _, colour in CATS:
                share = sum(category(t) == key for t in sub) / len(sub)
                if share:
                    ax.barh(y, share, left=left, height=0.66, color=colour, edgecolor="white", linewidth=0.8)
                left += share
        ax.set_title(title, fontsize=8, loc="left")
        ax.set_xlim(0, 1)
        ax.set_xticks([0, 0.5, 1])
        ax.set_xticklabels(["0%", "50%", "100%"], color="#52514e")
        ax.invert_yaxis()
        for s in ("top", "right", "left"):
            ax.spines[s].set_visible(False)
        ax.spines["bottom"].set_color("#bdbcb6")
        ax.tick_params(axis="y", length=0)
        ax.grid(axis="x", color="#e4e3de", linewidth=0.5)
        ax.set_axisbelow(True)
    axes[0].set_yticks(range(len(ARMS)))
    axes[0].set_yticklabels([label(a) for a in ARMS])
    handles = [plt.Rectangle((0, 0), 1, 1, color=c) for _, _, c in CATS]
    fig.legend(handles, [name for _, name, _ in CATS], loc="upper center", ncol=5, frameon=False,
               bbox_to_anchor=(0.5, 1.0), handlelength=1.2, columnspacing=1.4)
    fig.tight_layout(rect=(0, 0, 1, 0.94), w_pad=1.2)
    out = PAPER / "figures"
    out.mkdir(exist_ok=True)
    fig.savefig(out / "outcomes.pdf")
    plt.close(fig)


def rows_by(analysis):
    return {(r["model"], r["arm"]): r for r in analysis["by_model_arm"]}


def table_outcomes(analysis):
    r = rows_by(analysis)
    lines = []
    for model, name in MODELS:
        cells = [pct(r[model, "C0"]["correct"]), pct(r[model, "C1"]["correct"]), pct(r[model, "E"]["correct"]),
                 pct(r[model, "F1"]["correct"]), pct(r[model, "F1"]["fault_match"]),
                 pct(r[model, "F2"]["correct"]), pct(r[model, "F2"]["fault_match"])]
        lines.append(f"{SHORT[model]} & " + " & ".join(cells) + r" \\")
    return "\n".join(lines) + "\n"


def table_detection(analysis):
    r = rows_by(analysis)
    silent = analysis["silent_failure"]
    flagged = analysis["flagged_following"]
    lines = []
    for model, _ in MODELS:
        s = silent[f"{model}/F1"]
        cells = [pct(r[model, "F1"]["d1"]), pct(r[model, "F1"]["d2"]), pct(s["silent_over_trials"]),
                 f"{flagged[f'{model}/F1']['located_concern']}/{s['fault_match']}",
                 pct(r[model, "F2"]["d2"]), pct(r[model, "C1"]["d1"]), pct(r[model, "C1A"]["d1"])]
        lines.append(f"{SHORT[model]} & " + " & ".join(cells) + r" \\")
    return "\n".join(lines) + "\n"


def table_operators(analysis):
    r = {(x["operator"], x["arm"]): x for x in analysis["by_operator_arm"]}
    lines = []
    for op, name in OPERATORS:
        cells = [pct(r[op, "F1"]["fault_match"]), pct(r[op, "F1"]["silent"]), pct(r[op, "F2"]["fault_match"]),
                 pct(r[op, "F2"]["d2"]), pct(r[op, "F1A"]["fault_match"])]
        lines.append(f"{name} & " + " & ".join(cells) + r" \\")
    return "\n".join(lines) + "\n"


OUTCOME = {"fault_match": "Followed", "correct": "Correct", "d1": "D1", "d2": "D2", "silent": "Silent"}


def table_comparisons(analysis, rq2):
    h = analysis["hypotheses"]
    lines = []
    for key in ["H1", "H2", "H3a", "H3b", "X1", "X2", "X3", "X4", "X5"]:
        c = h[key]
        lines.append(" & ".join([key, OUTCOME[c["outcome"]], f"{label(c['arm_a'])} $-$ {label(c['arm_b'])}",
                                 pts(c["pooled"]["estimate"]), ci(c["pooled"]["ci95"]),
                                 ci(c["pooled_by_operator_clusters"]["ci95"]), p_value(c["gee_check"].get("p_value"))])
                     + r" \\")
        if key == "H3b":
            lines.append(r"\midrule")
    lines.append(r"\midrule")
    for key, contrast in [("C0_minus_F1_correct", "C0 $-$ F1"), ("C0_minus_F2_correct", "C0 $-$ F2")]:
        c = rq2[key]
        lines.append(" & ".join(["RQ2", "Correct", contrast, pts(c["estimate"]), ci(c["ci95"]), "--", "--"]) + r" \\")
    return "\n".join(lines) + "\n"


def table_audit(audit):
    lines = []
    for key, name in [("D1_about_layer", "D1 (about the layer)"), ("D2_identifies_as_asked", "D2 (names the fault)"),
                      ("D2_without_two_field_fiscal_faults", "D2 without Q13--Q16")]:
        a = audit[key]
        k = a["ci95"]["kappa"]
        cells = [str(a["n"]), f"{a['agreement']:.3f}", f"{a['kappa']:.2f} [{k[0]:.2f}, {k[1]:.2f}]",
                 f"{a['rule_precision']:.3f}", f"{a['rule_recall']:.3f}"]
        lines.append(f"{name} & " + " & ".join(cells) + r" \\")
    return "\n".join(lines) + "\n"


def main():
    trials = [json.loads(x) for x in (RES / "main-trials.jsonl").read_text().splitlines()]
    analysis = json.loads((RES / "main-ANALYSIS.json").read_text().replace("NaN", "null"))
    rq2 = json.loads((RES / "main-RQ2-WRONG-VS-NONE.json").read_text())
    audit = json.loads((RES / "main-HUMAN-AUDIT-AGREEMENT.json").read_text())
    figure(trials)
    out = PAPER / "tables"
    out.mkdir(exist_ok=True)
    # \bottomrule is written here: after an \input it would be a misplaced \noalign
    for name, body in [("outcomes", table_outcomes(analysis)), ("detection", table_detection(analysis)),
                       ("operators", table_operators(analysis)), ("comparisons", table_comparisons(analysis, rq2)),
                       ("audit", table_audit(audit))]:
        (out / f"{name}.tex").write_text(body + "\\bottomrule\n")
    print(sorted(p.name for p in out.iterdir()), out.parent / "figures" / "outcomes.pdf")


if __name__ == "__main__":
    main()

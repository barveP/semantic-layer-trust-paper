"""Analysis for the wrong-layer study (sl1). Reads results/<stage>-trials.jsonl.

  analyze.py <stage>   ->  results/<stage>-ANALYSIS.json, results/<stage>-TABLES.md

Pre-registered outcomes (protocol v0.2 section 5):
- answer rates per model x arm: correct, fault_match, other_wrong, exec_error/rejected/no_answer
- detection per model x arm: D1 (layer concern), D2 (located); false alarm = D1 on C1, C1A, C1N
- silent failure on fault arms, two denominators: all fault-arm trials; fault_match trials
Pre-registered directions, tested per model and pooled, paired by question:
- H1  fault_match(F1) > fault_match(F2)
- H2  correct(E) > correct(F1)
- H3a D2(F2A) > D2(F2);  H3b D1(C1A) > D1(C1)  (false alarms rise under the audit)
Uncertainty: cluster bootstrap over questions (10,000 resamples, seed 20261031), percentile 95%
intervals for each paired difference; a sensitivity bootstrap over fault operators (6 clusters);
and a check with a logistic GEE (exchangeable correlation, clustered by question), which is
population-averaged rather than the mixed model named in the protocol (recorded deviation).
"""
import json
import pathlib
import sys
import warnings

import numpy as np
import pandas as pd

RUN = pathlib.Path(__file__).resolve().parent
RES = RUN.parent / "results"
SEED = 20261031
B = 10_000
FAULT_ARMS = ["F1", "F2", "F1A", "F2A", "F1N", "F2N"]
FALSE_ALARM_ARMS = ["C1", "C1A", "C1N"]
HYPOTHESES = {
    "H1": ("fault_match", "F1", "F2"),
    "H2": ("correct", "E", "F1"),
    "H3a": ("d2", "F2A", "F2"),
    "H3b": ("d1", "C1A", "C1"),
}
# Exploratory comparisons added after the pilot and before the main run (POST-PILOT-AMENDMENT-01):
# the pilot showed D2 at ceiling on F2, while agents still followed flagged faults; these ask
# whether the audit instructions change following (behaviour) rather than detection.
EXPLORATORY = {
    "X1": ("fault_match", "F2", "F2A"),
    "X2": ("fault_match", "F1", "F1A"),
    "X3": ("silent", "F1", "F1A"),
    "X4": ("correct", "C1", "C0"),
    "X5": ("correct", "E", "C0"),
}


def load(stage):
    rows = [json.loads(x) for x in (RES / f"{stage}-trials.jsonl").read_text().splitlines()]
    if not rows:
        raise SystemExit("no trials")
    df = pd.DataFrame(rows)
    for k in ("correct", "fault_match", "other_wrong"):
        df[k] = (df["answer"] == k).astype(float)
    df["failed_to_answer"] = df["answer"].isin(["exec_error", "rejected", "no_answer"]).astype(float)
    for k in ("d1", "d2", "silent"):
        df[k] = df[k].map({True: 1.0, False: 0.0, None: np.nan})
    return df


def rate_table(df, by):
    g = df.groupby(by)
    out = g.agg(n=("trial_id", "size"), correct=("correct", "mean"), fault_match=("fault_match", "mean"),
                other_wrong=("other_wrong", "mean"), failed=("failed_to_answer", "mean"),
                d1=("d1", "mean"), d2=("d2", "mean"), silent=("silent", "mean"))
    return out.reset_index()


def paired_diff(df, outcome, arm_a, arm_b, cluster="qid", rng=None):
    """Mean over clusters of (mean outcome in arm_a - mean outcome in arm_b), with a cluster bootstrap."""
    sub = df[df["arm"].isin([arm_a, arm_b])].dropna(subset=[outcome])
    per = sub.groupby([cluster, "arm"])[outcome].mean().unstack()
    if arm_a not in per or arm_b not in per:
        return None
    per = per.dropna()
    if per.empty:
        return None
    d = (per[arm_a] - per[arm_b]).to_numpy()
    rng = rng or np.random.default_rng(SEED)
    idx = rng.integers(0, len(d), size=(B, len(d)))
    boot = d[idx].mean(axis=1)
    return {"estimate": float(d.mean()), "ci95": [float(np.percentile(boot, 2.5)), float(np.percentile(boot, 97.5))],
            "clusters": int(len(d)), "mean_a": float(per[arm_a].mean()), "mean_b": float(per[arm_b].mean()),
            "share_of_bootstrap_above_0": float((boot > 0).mean())}


def gee_check(df, outcome, arm_a, arm_b):
    import statsmodels.api as sm
    import statsmodels.formula.api as smf
    sub = df[df["arm"].isin([arm_a, arm_b])].dropna(subset=[outcome]).copy()
    sub["treat"] = (sub["arm"] == arm_a).astype(int)
    if sub[outcome].nunique() < 2 or sub["treat"].nunique() < 2:
        return {"note": "outcome or arm constant; model not fitted"}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            m = smf.gee(f"{outcome} ~ treat + C(model)", groups="qid", data=sub,
                        family=sm.families.Binomial(), cov_struct=sm.cov_struct.Exchangeable()).fit()
            lo, hi = m.conf_int().loc["treat"]
            return {"log_odds_treat": float(m.params["treat"]), "ci95": [float(lo), float(hi)],
                    "p_value": float(m.pvalues["treat"])}
        except Exception as e:  # noqa: BLE001
            return {"note": f"not fitted: {type(e).__name__}: {str(e)[:120]}"}


def fmt(x):
    return "–" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{x:.2f}"


def main():
    global RES
    stage = sys.argv[1]
    if len(sys.argv) > 2:  # alternative results folder (used for the fake-provider test)
        RES = pathlib.Path(sys.argv[2])
    df = load(stage)
    rng = np.random.default_rng(SEED)
    out = {"stage": stage, "trials": int(len(df)), "seed": SEED, "bootstrap_resamples": B,
           "answer_counts": df["answer"].value_counts().to_dict(),
           "cost_usd": {m: float(g["cost_micros"].fillna(0).sum() / 1e6) for m, g in df.groupby("model")}}
    out["by_model_arm"] = rate_table(df, ["model", "arm"]).to_dict(orient="records")
    out["by_arm"] = rate_table(df, ["arm"]).to_dict(orient="records")
    out["by_operator_arm"] = rate_table(df, ["operator", "arm"]).to_dict(orient="records")

    fa = df[df["arm"].isin(FAULT_ARMS)]
    out["silent_failure"] = {}
    for (model, arm), g in fa.groupby(["model", "arm"]):
        n_fm = int(g["fault_match"].sum())
        out["silent_failure"][f"{model}/{arm}"] = {
            "trials": int(len(g)), "fault_match": n_fm, "silent": int(g["silent"].sum()),
            "silent_over_trials": float(g["silent"].mean()),
            "silent_over_fault_match": float(g["silent"].sum() / n_fm) if n_fm else None}
    out["false_alarms"] = {f"{m}/{a}": float(g["d1"].mean()) for (m, a), g in
                           df[df["arm"].isin(FALSE_ALARM_ARMS)].groupby(["model", "arm"])}

    out["hypotheses"] = {}
    for name, (outcome, a, b) in list(HYPOTHESES.items()) + list(EXPLORATORY.items()):
        res = {"outcome": outcome, "arm_a": a, "arm_b": b, "pooled": paired_diff(df, outcome, a, b, rng=rng),
               "pooled_by_operator_clusters": paired_diff(df, outcome, a, b, cluster="operator", rng=rng),
               "gee_check": gee_check(df, outcome, a, b), "per_model": {}}
        for model, g in df.groupby("model"):
            res["per_model"][model] = paired_diff(g, outcome, a, b, rng=rng)
        res["status"] = "pre-registered" if name in HYPOTHESES else "exploratory (added after the pilot)"
        out["hypotheses"][name] = res

    (RES / f"{stage}-ANALYSIS.json").write_text(json.dumps(out, indent=2, default=float) + "\n")

    lines = [f"# {stage}: tables (generated by run/analyze.py)\n",
             f"Trials: {len(df)}. Answer counts: {out['answer_counts']}. Cost (USD): "
             + ", ".join(f"{m} {c:.2f}" for m, c in out["cost_usd"].items()) + "\n",
             "## Rates by model and arm\n",
             "| model | arm | n | correct | fault_match | other_wrong | failed | D1 | D2 | silent |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for r in out["by_model_arm"]:
        lines.append(f"| {r['model']} | {r['arm']} | {r['n']} | {fmt(r['correct'])} | {fmt(r['fault_match'])} | "
                     f"{fmt(r['other_wrong'])} | {fmt(r['failed'])} | {fmt(r['d1'])} | {fmt(r['d2'])} | {fmt(r['silent'])} |")
    lines += ["", "## Comparisons (paired by question; cluster bootstrap 95% CI). H = pre-registered, X = exploratory\n",
              "| id | outcome | arms | pooled estimate [95% CI] | per model |", "|---|---|---|---|---|"]
    for name, h in out["hypotheses"].items():
        p = h["pooled"]
        pooled = "–" if not p else f"{p['estimate']:+.2f} [{p['ci95'][0]:+.2f}, {p['ci95'][1]:+.2f}]"
        per = "; ".join(f"{m} {v['estimate']:+.2f}" for m, v in h["per_model"].items() if v)
        lines.append(f"| {name} | {h['outcome']} | {h['arm_a']} vs {h['arm_b']} | {pooled} | {per} |")
    (RES / f"{stage}-TABLES.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines[:3]))


if __name__ == "__main__":
    main()

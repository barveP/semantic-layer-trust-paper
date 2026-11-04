"""Figures for the wrong-layer study. Reads results/<stage>-trials.jsonl.

  figures.py <stage>  ->  results/figures/<stage>-outcomes.{png,svg}

Figure 1 ("follow vs flag"): for each model, one horizontal bar per arm, split into
correct | followed the fault silently | followed the fault but flagged the layer |
other wrong | no usable answer. In arms without a fault, a result that happens to equal the
faulty definition's result is drawn as "other wrong" (the tables keep it separate). Colours: reference categorical palette slots 1-4 in fixed
order (validated for adjacent pairs), neutral grey for "no usable answer".
"""
import json
import pathlib
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

RUN = pathlib.Path(__file__).resolve().parent
RES = RUN.parent / "results"
ORDER = ["C0", "C1", "C1a", "C1b", "E", "F1", "F2", "C1A", "F1A", "F2A", "C1N", "F1N", "F2N"]
MODELS = [("opus", "Claude Opus 5.5"), ("sol", "GPT-6.1 Sol"), ("haiku", "Claude Haiku 5.5")]
CATS = [("correct", "Correct", "#2a78d6"), ("silent", "Followed fault, silent", "#eb6834"),
        ("flagged", "Followed fault, flagged layer", "#1baf7a"), ("other", "Other wrong", "#eda100"),
        ("failed", "No usable answer", "#b4b3ad")]
INK, MUTED, SURFACE = "#0b0b0b", "#52514e", "#fcfcfb"
FAULT_ARMS = {"F1", "F2", "F1A", "F2A", "F1N", "F2N"}


def category(t):
    if t["answer"] == "correct":
        return "correct"
    if t["answer"] == "fault_match":
        if t["arm"] not in FAULT_ARMS:  # no fault shown: a coincidental match is just a wrong answer here
            return "other"
        return "flagged" if t.get("d1") else "silent"
    if t["answer"] == "other_wrong":
        return "other"
    return "failed"


def main():
    global RES
    stage = sys.argv[1]
    if len(sys.argv) > 2:  # alternative results folder (used for the fake-provider test)
        RES = pathlib.Path(sys.argv[2])
    trials = [json.loads(x) for x in (RES / f"{stage}-trials.jsonl").read_text().splitlines()]
    arms = [a for a in ORDER if any(t["arm"] == a for t in trials)]
    fig, axes = plt.subplots(1, 3, figsize=(11, 0.42 * len(arms) + 1.6), sharey=True, facecolor=SURFACE)
    for ax, (model, title) in zip(axes, MODELS):
        ax.set_facecolor(SURFACE)
        for y, arm in enumerate(arms):
            sub = [t for t in trials if t["model"] == model and t["arm"] == arm]
            left = 0.0
            for key, _, colour in CATS:
                share = sum(category(t) == key for t in sub) / len(sub) if sub else 0
                if share:
                    ax.barh(y, share, left=left, height=0.62, color=colour, edgecolor=SURFACE, linewidth=1.5)
                left += share
        ax.set_title(title, color=INK, fontsize=10, loc="left")
        ax.set_xlim(0, 1)
        ax.set_xticks([0, 0.5, 1])
        ax.set_xticklabels(["0%", "50%", "100%"], color=MUTED, fontsize=8)
        ax.invert_yaxis()
        for s in ("top", "right", "left"):
            ax.spines[s].set_visible(False)
        ax.spines["bottom"].set_color("#d6d5cf")
        ax.tick_params(axis="y", length=0)
        ax.grid(axis="x", color="#ebeae5", linewidth=0.6)
        ax.set_axisbelow(True)
    axes[0].set_yticks(range(len(arms)))
    axes[0].set_yticklabels(arms, color=INK, fontsize=9)
    handles = [plt.Rectangle((0, 0), 1, 1, color=c) for _, _, c in CATS]
    fig.legend(handles, [label for _, label, _ in CATS], loc="upper center", ncol=5, frameon=False,
               fontsize=8, labelcolor=INK, bbox_to_anchor=(0.5, 1.0))
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    out = RES / "figures"
    out.mkdir(parents=True, exist_ok=True)
    for ext in ("png", "svg"):
        fig.savefig(out / f"{stage}-outcomes.{ext}", dpi=200, facecolor=SURFACE)
    print(out / f"{stage}-outcomes.png")


if __name__ == "__main__":
    main()

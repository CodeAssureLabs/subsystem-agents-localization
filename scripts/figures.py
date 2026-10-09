"""Figures for the revised manuscript (vector PDF, sized for IEEE Access columns)."""
import json

import matplotlib
import matplotlib.pyplot as plt
import numpy as np

from common import HERE, METHOD_LABELS

OUT = HERE.parent / "figures"
OUT.mkdir(exist_ok=True)
R = json.load(open(HERE / "results.json"))
IR = json.load(open(HERE / "ir_results.json"))
IRN = json.load(open(HERE / "ir_results_new_repos.json"))

matplotlib.rcParams.update({
    "font.family": "serif", "font.size": 8, "axes.titlesize": 8.5, "axes.labelsize": 8,
    "legend.fontsize": 7, "xtick.labelsize": 7, "ytick.labelsize": 7, "axes.spines.top": False,
    "axes.spines.right": False, "axes.edgecolor": "#52514e", "axes.linewidth": 0.6, "pdf.fonttype": 42,
})

# Colour encodes method family; marker fill encodes model (filled = Haiku, hollow = Sonnet/other).
STYLE = {
    "plain_haiku": ("#eda100", "o", True),
    "plain_sonnet": ("#eda100", "o", False),
    "rlm_haiku": ("#4a3aa7", "s", True),
    "rlm_sonnet": ("#4a3aa7", "s", False),
    "ds_nospawn": ("#1baf7a", "D", True),
    "ds_adaptive": ("#2a78d6", "*", True),
    "codex": ("#eb6834", "^", False),
    # Published localization methods (one family colour, distinct markers), all Haiku 4.5.
    "rrl": ("#e87ba4", "v", True),
    "agentless": ("#e87ba4", "P", True),
    "cosil": ("#e87ba4", "X", True),
    "locagent": ("#e87ba4", "h", True),
}
ORDER = ["plain_haiku", "plain_sonnet", "rlm_haiku", "rlm_sonnet", "ds_nospawn", "ds_adaptive", "codex",
         "rrl", "agentless", "cosil", "locagent"]
WINDOWS = ["2020", "2025", "2026", "openlibrary", "qutebrowser"]
WTITLE = {"2020": "ansible 2020", "2025": "ansible 2025", "2026": "ansible 2026", "openlibrary": "openlibrary", "qutebrowser": "qutebrowser"}


def ir_env(name, w):
    return (IR if w in ("2020", "2025", "2026") else IRN)["SRC"][name][w]["envelope"]


def marker(ax, x, y, m, label=None, size=46):
    c, mk, filled = STYLE[m]
    ax.scatter([x], [y], s=size * (2.2 if mk == "*" else 1), marker=mk, facecolor=c if filled else "white",
               edgecolor=c, linewidth=1.3, zorder=5, label=label)


def iso_f1(ax):
    xs = np.linspace(0.01, 1, 200)
    for f in (0.2, 0.4, 0.6):
        y = f * xs / (2 * xs - f)
        ok = (y > 0) & (y <= 1)
        ax.plot(xs[ok], y[ok], color="#c3c2b7", lw=0.5, ls="--", zorder=0)
        ax.text(0.995, f * 0.995 / (2 * 0.995 - f) + 0.008, f"{f}", fontsize=6, color="#8a8984", ha="right", va="bottom")


def fig_pr():
    fig, axs = plt.subplots(2, 3, figsize=(7.16, 4.9), sharey=True, sharex=True)
    axes = axs.ravel()
    for ax, w in zip(axes, WINDOWS):
        iso_f1(ax)
        for name, col, ls, lab in [("bm25", "#52514e", "-", "BM25 (top-K)"), ("l2r", "#0b0b0b", ":", "L2R (top-K)")]:
            env = ir_env(name, w)
            ks = sorted(env, key=int)
            ax.plot([env[k]["R"] for k in ks], [env[k]["P"] for k in ks], color=col, ls=ls, lw=1.1, label=lab, zorder=2)
        for m in ORDER:
            v = R["by_window"][w][m]["SRC"]
            marker(ax, v["R"], v["P"], m, label=METHOD_LABELS[m])
        ax.set_title(f"{WTITLE[w]} ($G_{{SRC}}$)")
        ax.set_xlim(0, 1); ax.set_ylim(0, 0.8)
        ax.grid(color="#ececea", lw=0.4)
    for ax in axs[1]:
        ax.set_xlabel("Micro recall  (dashed: iso-F1)")
    for ax in axs[:, 0]:
        ax.set_ylabel("Micro precision")
    axes[-1].axis("off")
    h, l = axes[0].get_legend_handles_labels()
    axes[-1].legend(h, l, loc="center", frameon=False, fontsize=7, handletextpad=0.4)
    fig.tight_layout()
    fig.savefig(OUT / "pr_envelope.pdf", bbox_inches="tight")
    fig.savefig(OUT / "pr_envelope.png", dpi=220, bbox_inches="tight")


def fig_cost():
    fig, ax = plt.subplots(figsize=(3.45, 3.3))
    for m in ORDER:
        p = R["pooled_all"][m]["SRC"]
        toks = np.mean([R["by_window"][w][m]["SRC"]["tokens_per_inst_mean"] for w in WINDOWS])
        lo, hi = p["F1_boot"]
        c = STYLE[m][0]
        ax.plot([toks, toks], [lo, hi], color=c, lw=1.0, zorder=3)
        marker(ax, toks, p["F1"], m, label=METHOD_LABELS[m])
    bm = np.mean([(IR if w in ("2020", "2025", "2026") else IRN)["SRC"]["l2r"][w]["F1_transfer"] for w in WINDOWS])
    ax.axhline(bm, color="#0b0b0b", ls=":", lw=0.9)
    ax.text(1.3e3, bm + 0.012, "L2R baseline (no LLM), mean of windows", fontsize=6.5, color="#52514e")
    ax.set_xscale("log")
    ax.set_xlabel("Mean tokens per instance (log scale)")
    ax.set_ylabel("Pooled micro-F1, $G_{SRC}$ (105 issues)")
    ax.set_ylim(0, 0.6)
    ax.grid(color="#ececea", lw=0.4)
    ax.legend(loc="upper center", bbox_to_anchor=(0.45, -0.2), ncol=2, frameon=False, fontsize=6.2,
              handletextpad=0.3, columnspacing=0.8)
    fig.tight_layout()
    fig.savefig(OUT / "cost_f1.pdf", bbox_inches="tight")
    fig.savefig(OUT / "cost_f1.png", dpi=220, bbox_inches="tight")


def fig_forest():
    kinds = [("SRC", "$G_{SRC}$ (source files)"), ("PR_EXIST", "$G_{PR}^{exist}$ (all existing files)")]
    fig, axes = plt.subplots(1, 2, figsize=(7.16, 3.8), sharey=True)
    ys = {m: i for i, m in enumerate(reversed(ORDER))}
    offs = {"2020": 0.3, "2025": 0.15, "2026": 0.0, "openlibrary": -0.15, "qutebrowser": -0.3}
    wmark = {"2020": "o", "2025": "s", "2026": "^", "openlibrary": "D", "qutebrowser": "v"}
    for ax, (k, title) in zip(axes, kinds):
        for m in ORDER:
            c = STYLE[m][0]
            for w in WINDOWS:
                v = R["by_window"][w][m][k]
                lo, hi = v["F1_boot"]
                y = ys[m] + offs[w]
                ax.plot([lo, hi], [y, y], color=c, lw=0.9, alpha=0.8)
                ax.scatter([v["F1"]], [y], marker=wmark[w], s=16, color=c, zorder=4)
            p = R["pooled_all"][m][k]
            ax.scatter([p["F1"]], [ys[m]], marker="|", s=170, color="#0b0b0b", lw=1.6, zorder=5)
        ax.set_title(title)
        ax.set_xlabel("Micro-F1 (95% instance-bootstrap CI)")
        ax.set_xlim(0, 0.8)
        ax.grid(axis="x", color="#ececea", lw=0.4)
    axes[0].set_yticks(list(ys.values()))
    axes[0].set_yticklabels([METHOD_LABELS[m] for m in ys])
    from matplotlib.lines import Line2D
    h = [Line2D([], [], marker=wmark[w], ls="", color="#52514e", label=WTITLE[w]) for w in WINDOWS]
    h.append(Line2D([], [], marker="|", ls="", markersize=11, mew=1.6, color="#0b0b0b", label="Pooled (105 issues)"))
    fig.legend(handles=h, loc="lower center", ncol=6, frameon=False, bbox_to_anchor=(0.6, -0.03))
    fig.tight_layout(rect=(0, 0.07, 1, 1))
    fig.savefig(OUT / "forest.pdf", bbox_inches="tight")
    fig.savefig(OUT / "forest.png", dpi=220, bbox_inches="tight")


if __name__ == "__main__":
    fig_pr(); fig_cost(); fig_forest()
    print("figures written to", OUT)

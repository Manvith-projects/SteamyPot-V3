"""
=============================================================================
Pipeline Orchestrator -- ETA Predictor  (research-grade)
=============================================================================
Stages
------
1. Generate synthetic dataset            (dataset_generator.py)
2. Train & evaluate all models           (train_models.py)
3. Produce publication-ready figures     (generate_graphs.py)
4. Auto-fill LaTeX results into paper.tex
"""

import json, re
from pathlib import Path

# -- paths ---------------------------------------------------------------------
BASE = Path(__file__).parent
OUT  = BASE / "outputs"
TEX  = BASE / "paper.tex"
CHECKPOINT = OUT / ".checkpoint.json"


# -- checkpoint helpers --------------------------------------------------------
def _load_checkpoint():
    OUT.mkdir(parents=True, exist_ok=True)
    if CHECKPOINT.exists():
        with open(CHECKPOINT) as f:
            return set(json.load(f).get("completed", []))
    return set()

def _save_checkpoint(completed: set):
    with open(CHECKPOINT, "w") as f:
        json.dump({"completed": sorted(completed)}, f)

def _step_done(name, completed):
    if name in completed:
        print(f"\n[checkpoint] Skipping {name} (already completed)")
        return True
    return False

def _mark_done(name, completed):
    completed.add(name)
    _save_checkpoint(completed)


# -- stage helpers -------------------------------------------------------------
def step_generate():
    print("\n" + "=" * 70)
    print("STEP 1 -- Generating synthetic dataset ...")
    print("=" * 70)
    from dataset_generator import generate_dataset
    generate_dataset()


def step_train():
    print("\n" + "=" * 70)
    print("STEP 2 -- Training & evaluating models ...")
    print("=" * 70)
    from train_models import train_and_compare
    train_and_compare()


def step_graphs():
    print("\n" + "=" * 70)
    print("STEP 3 -- Generating research graphs ...")
    print("=" * 70)
    from generate_graphs import generate_all_graphs
    generate_all_graphs()


def step_update_latex():
    print("\n" + "=" * 70)
    print("STEP 4 -- Updating LaTeX paper with results ...")
    print("=" * 70)

    if not TEX.exists():
        print("[latex] paper.tex not found -- skipping.")
        return
    with open(OUT / "results.json") as f:
        res = json.load(f)

    cv = res["cv_results"]
    ho = res["holdout_results"]
    sig = res.get("significance", {})
    abl = res.get("ablation", {})
    lat = res.get("latency", {})
    best_name = res["best_model"]

    tex = TEX.read_text(encoding="utf-8")

    def _sub(tag, body):
        """Safe regex sub -- uses lambda to avoid backslash interpretation."""
        nonlocal tex
        pat = rf"%<<{tag}>>.*?%<</{tag}>>"
        repl = f"%<<{tag}>>\n{body}\n        %<</{tag}>>"
        tex = re.sub(pat, lambda _m: repl, tex, flags=re.DOTALL)

    # ---- CV results table body ----
    cv_rows = []
    for name in cv:
        d = cv[name]
        cv_rows.append(
            f"        {name} & "
            f"{d['MAE_mean']:.3f}$\\pm${d['MAE_std']:.3f} & "
            f"{d['RMSE_mean']:.3f}$\\pm${d['RMSE_std']:.3f} & "
            f"{d['R2_mean']:.3f}$\\pm${d['R2_std']:.3f} \\\\"
        )
    _sub("CV_ROWS", "\n".join(cv_rows))

    # ---- Holdout results table body ----
    ho_rows = []
    for name in ho:
        d = ho[name]
        ho_rows.append(
            f"        {name} & "
            f"{d['MAE']:.3f} & {d['RMSE']:.3f} & "
            f"{d['R2']:.3f} & {d['train_time_s']:.2f} \\\\"
        )
    _sub("HO_ROWS", "\n".join(ho_rows))

    # ---- Significance table body ----
    if sig and "tests" in sig:
        sig_rows = []
        ref = sig["reference"]
        for name, d in sig["tests"].items():
            pair_label = f"{ref} vs {name}"
            t = d["paired_t"]
            w = d["wilcoxon"]
            sig_rows.append(
                f"        {pair_label} & {t['statistic']:.3f} & {t['p_value']:.4f} & "
                f"{w['statistic']:.1f} & {w['p_value']:.4f} \\\\"
            )
        _sub("SIG_ROWS", "\n".join(sig_rows))

    # ---- Ablation table body ----
    if abl:
        abl_rows = []
        for label, d in abl.items():
            abl_rows.append(
                f"        {label} & {d['MAE']:.3f} & {d['RMSE']:.3f} & {d['R2']:.3f} \\\\"
            )
        _sub("ABL_ROWS", "\n".join(abl_rows))

    # ---- Latency table body ----
    if lat:
        lat_rows = []
        for name, d in lat.items():
            lat_rows.append(
                f"        {name} & {d['mean_ms']:.2f} & {d['std_ms']:.2f} & {d['p99_ms']:.2f} \\\\"
            )
        _sub("LAT_ROWS", "\n".join(lat_rows))

    # ---- Best model name ----
    tex = tex.replace("<<BEST_MODEL>>", best_name)

    TEX.write_text(tex, encoding="utf-8")
    print(f"[latex] Updated {TEX.name} with all experimental results.")


# -- main ----------------------------------------------------------------------
def main():
    done = _load_checkpoint()
    if done:
        print(f"[checkpoint] Resuming. Already completed: {sorted(done)}")

    steps = [
        ("generate", step_generate),
        ("train",    step_train),
        ("graphs",   step_graphs),
        ("latex",    step_update_latex),
    ]

    for name, fn in steps:
        if _step_done(name, done):
            continue
        try:
            fn()
            _mark_done(name, done)
        except Exception as exc:
            print(f"\n[ERROR] Step '{name}' failed: {exc}")
            print(f"[checkpoint] Progress saved. Re-run main.py to resume from '{name}'.")
            raise

    # Remove checkpoint on full success
    CHECKPOINT.unlink(missing_ok=True)

    print("\n" + "=" * 70)
    print("ALL STAGES COMPLETE")
    print("=" * 70)
    with open(OUT / "results.json") as f:
        res = json.load(f)
    cv = res["cv_results"]
    best = res["best_model"]
    bd = cv[best]
    print(f"\n  Best model:  {best}")
    print(f"  CV MAE:      {bd['MAE_mean']:.3f} +/- {bd['MAE_std']:.3f}")
    print(f"  CV RMSE:     {bd['RMSE_mean']:.3f} +/- {bd['RMSE_std']:.3f}")
    print(f"  CV R2:       {bd['R2_mean']:.3f} +/- {bd['R2_std']:.3f}")
    print(f"\n  Outputs -> {OUT.resolve()}")


if __name__ == "__main__":
    main()

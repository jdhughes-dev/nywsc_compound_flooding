"""Rebuild everything the manuscript is made of, from whatever is available.

There are three places a rebuild can start, and which one is possible depends on
what the person running it has:

  document   typeset the PDF from the figures already in figures/
  figures    redraw all seven figures and the graphical abstract, then typeset
  archives   recompute the six archives from results/ and logs/, then the above
  everything run the 46 coupled simulations first, then the above

The default is `figures`, because that is what someone who has cloned the
repository and nothing else can do: the archives under ../data/GP are committed
precisely so the figures rebuild without the simulation output, which is hundreds
of gigabytes and is not version controlled. `archives` is for someone who has re-run
the simulations and wants the summaries recomputed rather than trusted.

Running the simulations is not automated here beyond printing the commands. They
take about four days and 300 GB, they are the thing most likely to be interrupted,
and run_sweep.py already knows how to resume them. See README.md.

Usage
-----
    python rebuild_manuscript.py                 # figures + document
    python rebuild_manuscript.py --stage archives
    python rebuild_manuscript.py --check         # report what is available
    python rebuild_manuscript.py --all-grids     # also the medium/fine variants
"""
import argparse
import pathlib as pl
import subprocess
import sys
import time

HERE = pl.Path(__file__).resolve().parent
DOCS = HERE.parent
ROOT = DOCS.parents[1]
TEX = DOCS / "Hughesetal_ESM_LISSCoupling.tex"

# Recompute order matters only in that the archives must precede the figures that
# read them; within a stage the entries are independent.
ARCHIVES = [
    ("boundary_averaging_data.py", ["coarse"], "boundary_averaging.nc"),
    ("boundary_averaging_data.py", ["medium"], "boundary_averaging_medium.nc"),
    ("boundary_averaging_data.py", ["high"], "boundary_averaging_high.nc"),
    ("sewer_exchange_data.py", [], "sewer_exchange.nc"),
    ("coastal_exchange_data.py", [], "coastal_exchange.nc"),
    ("coupling_cost_data.py", [], "coupling_cost.nc"),
]

# Every figure the manuscript includes, with the arguments that produce it.
FIGURES = [
    ("make_coupling_sequence_figure.py", [], "coupling_sequence.pdf"),
    ("make_boundary_reduction_figure.py", [], "boundary_reduction.pdf"),
    ("make_coupling_region_figure.py", [], "coupling_region.pdf"),
    ("make_boundary_averaging_figure.py", ["coarse", "--no-refresh"],
     "boundary_averaging.pdf"),
    ("make_sewer_exchange_figure.py", ["--no-refresh"], "sewer_exchange.pdf"),
    ("make_coastal_exchange_figure.py", ["--no-refresh"], "coastal_exchange.pdf"),
    ("make_coupling_cost_figure.py", ["--no-refresh"], "coupling_cost.pdf"),
]

# Artwork the journal wants as a separate file and the document does not include.
# Kept out of FIGURES deliberately: export_submission() numbers FIGURES from the .aux,
# and anything not cited in the .tex has no number to be given. Drawn every time the
# figures stage runs, because it reads the same archives as Figures 3 and 7 and would
# otherwise be the one piece of artwork that could silently fall behind them.
SUBMISSION_ARTWORK = [
    ("make_graphical_abstract.py", ["--no-refresh"], "graphical_abstract.pdf"),
]

# Drawn for the medium and fine grids too. They support statements in the text but
# are not included in the document, so they are off by default.
EXTRA_FIGURES = [
    ("make_boundary_averaging_figure.py", ["medium", "--no-refresh"],
     "boundary_averaging_medium.pdf"),
    ("make_boundary_averaging_figure.py", ["high", "--no-refresh"],
     "boundary_averaging_high.pdf"),
]


def run(script, args, label):
    t0 = time.perf_counter()
    p = subprocess.run([sys.executable, "-u", str(HERE / script), *args],
                       cwd=str(HERE), capture_output=True, text=True)
    dt = time.perf_counter() - t0
    ok = p.returncode == 0
    print(f"  {'ok ' if ok else 'FAIL'}  {label:<34} {dt:6.1f} s")
    if not ok:
        tail = (p.stderr or p.stdout).strip().splitlines()[-6:]
        for line in tail:
            print(f"        {line}")
    return ok


def check():
    """Report what a rebuild could start from, without changing anything."""
    results = ROOT / "results" / "gp"
    logs = ROOT / "logs"
    n_runs = len(list(results.glob("gp_*"))) if results.is_dir() else 0
    n_logs = len(list(logs.glob("*.log"))) if logs.is_dir() else 0
    print(f"results/gp        {n_runs} scenario directories")
    print(f"logs/             {n_logs} run logs")
    print(f"archives          {sum((DOCS.parents[0] / 'data' / 'GP' / a[2]).is_file() for a in ARCHIVES)}"
          f" of {len(ARCHIVES)} present")
    print(f"figures           {sum((DOCS / 'figures' / f[2]).is_file() for f in FIGURES)}"
          f" of {len(FIGURES)} present")
    print(f"submission art    "
          f"{sum((DOCS / 'figures' / f[2]).is_file() for f in SUBMISSION_ARTWORK)}"
          f" of {len(SUBMISSION_ARTWORK)} present")

    sys.path.insert(0, str(HERE))
    for mod, label in (("boundary_averaging_data", "boundary averaging"),
                       ("sewer_exchange_data", "sewer exchange"),
                       ("coastal_exchange_data", "coastal exchange"),
                       ("coupling_cost_data", "coupling cost")):
        m = __import__(mod)
        try:
            gaps = (m.missing(grid="coarse") if mod == "boundary_averaging_data"
                    else m.missing())
        except Exception as exc:
            gaps = [f"could not check ({type(exc).__name__})"]
        print(f"  {label:<20} " + ("complete" if not gaps
                                   else f"{len(gaps)} missing: {gaps[:2]}"))
    print("\n`--stage archives` is only meaningful where the inputs are complete; "
          "where they are not,\nthe data modules fall back to the committed archive "
          "and the figures are unchanged.")


def export_submission():
    """Copy each figure to submission/Figure_N.pdf, numbered as the document does.

    The numbering is read from the .aux and the label-to-file mapping from the .tex,
    rather than from the order of FIGURES above. Those two orders are not the same
    and never were: LaTeX numbers by the order captions appear in the source, so
    boundary_averaging is Figure 3 while it is fourth in the list here, and the
    sewer and coastal figures are likewise swapped. Numbering by list position would
    mislabel four of the seven.
    """
    import re
    import shutil

    aux = DOCS / f"{TEX.stem}.aux"
    if not aux.is_file():
        print("  no .aux -- typeset the document first")
        return False
    numbers = {m.group(1): int(m.group(2)) for m in
               re.finditer(r"newlabel\{(fig:[^}]+)\}\{\{(\d+)\}",
                           aux.read_text(errors="replace"))}

    tex = TEX.read_bytes().decode("utf-8-sig")
    mapping = {}
    for block in re.findall(r"begin\{figure\}.*?end\{figure\}", tex, re.S):
        f = re.search(r"widefig\{figures/([^}]+)\}", block)
        lab = re.search(r"label\{(fig:[^}]+)\}", block)
        if f and lab:
            mapping[lab.group(1)] = f.group(1)

    out_dir = DOCS / "submission"
    out_dir.mkdir(exist_ok=True)
    seen, ok = {}, True
    for label, fname in mapping.items():
        n = numbers.get(label)
        src = DOCS / "figures" / fname
        if n is None or not src.is_file():
            print(f"  FAIL  {label}: number={n} file={src.name} present={src.is_file()}")
            ok = False
            continue
        dst = out_dir / f"Figure_{n}.pdf"
        shutil.copy2(src, dst)
        seen[n] = fname
    # A gap or a duplicate means a figure was renumbered without this noticing.
    expected = set(range(1, len(mapping) + 1))
    if set(seen) != expected:
        print(f"  FAIL  numbering is not 1..{len(mapping)}: got {sorted(seen)}")
        ok = False
    for n in sorted(seen):
        print(f"  ok   Figure_{n}.pdf{'':<21} from {seen[n]}")

    # The graphical abstract is required and is not a numbered figure, so it is copied
    # after the numbering check rather than through it. The name carries the words the
    # journal uses, because the upload form identifies items by filename.
    shipped = [out_dir / f"Figure_{n}.pdf" for n in sorted(seen)]
    ga_src = DOCS / "figures" / "graphical_abstract.pdf"
    if ga_src.is_file():
        ga_dst = out_dir / "Graphical_Abstract.pdf"
        shutil.copy2(ga_src, ga_dst)
        shipped.append(ga_dst)
        print(f"  ok   Graphical_Abstract.pdf{'':<11} from {ga_src.name}")
    else:
        print("  FAIL  graphical_abstract.pdf is missing -- run the figures stage")
        ok = False

    # The journal requires vector art with fonts embedded. The scripts set
    # pdf.fonttype 42 through flopy's style, so this should always pass; it is
    # checked rather than assumed because a figure that fails is rejected at
    # submission rather than at build time.
    try:
        for path in shipped:
            out = subprocess.run(["pdffonts", str(path)],
                                 capture_output=True, text=True)
            rows = out.stdout.strip().splitlines()[2:]
            if any(r.split()[-4] != "yes" for r in rows if r.split()):
                print(f"  FAIL  {path.name} has a font that is not embedded")
                ok = False
    except FileNotFoundError:
        print("  (pdffonts not available; embedding not verified)")

    print(f"  -> {out_dir}")
    return ok


def typeset():
    print("document")
    t0 = time.perf_counter()
    p = subprocess.run(["latexmk", "-pdf", "-interaction=nonstopmode",
                        "-halt-on-error", TEX.name],
                       cwd=str(DOCS), capture_output=True, text=True)
    dt = time.perf_counter() - t0
    log = DOCS / f"{TEX.stem}.log"
    text = log.read_text(errors="replace") if log.is_file() else ""
    bad = sum(1 for l in text.splitlines()
              if l.lower().startswith(("! ", "overfull", "underfull"))
              or "undefined reference" in l.lower()
              or "undefined citation" in l.lower())
    ok = p.returncode == 0
    print(f"  {'ok ' if ok else 'FAIL'}  {TEX.stem}.pdf{'':<21} {dt:6.1f} s"
          f"   {bad} log warnings")
    if not ok:
        for line in [l for l in text.splitlines() if l.startswith("! ")][:5]:
            print(f"        {line}")
    return ok


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--stage", default="figures",
                   choices=("document", "figures", "archives", "everything"))
    p.add_argument("--all-grids", action="store_true",
                   help="also draw the medium and fine boundary-averaging figures, "
                        "which support the text but are not included in it")
    p.add_argument("--check", action="store_true",
                   help="report what is available to rebuild from, and stop")
    p.add_argument("--submission", action="store_true",
                   help="also write submission/Figure_N.pdf, numbered as the "
                        "typeset document numbers them, which the journal wants as "
                        "separate files")
    args = p.parse_args()

    if args.check:
        check()
        return 0

    if args.stage == "everything":
        print("The 46 coupled simulations are not run from here. They take about "
              "four days\nand 300 GB, and run_sweep.py resumes them after an "
              "interruption. The commands\nare in README.md. Re-run this with "
              "--stage archives once they are complete.\n")
        return 1

    ok = True
    if args.stage == "archives":
        print("archives  (recomputed from results/ and logs/ where complete)")
        for script, a, out in ARCHIVES:
            ok &= run(script, a, out)
        print()

    if args.stage in ("archives", "figures"):
        print("figures")
        todo = FIGURES + SUBMISSION_ARTWORK + (EXTRA_FIGURES if args.all_grids else [])
        for script, a, out in todo:
            ok &= run(script, a, out)
        print()

    ok &= typeset()

    # After typesetting, because the numbering comes out of the .aux the run just
    # wrote. Exporting from a stale .aux would number against the previous document.
    if args.submission:
        print("\nsubmission figures")
        ok &= export_submission()

    print("\n" + ("everything rebuilt" if ok else "SOMETHING FAILED - see above"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

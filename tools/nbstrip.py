#!/usr/bin/env python
"""Strip outputs and volatile metadata from Jupyter notebooks.

Used as a git *clean* filter, so notebooks are stored in git without their
outputs while your working copy keeps the rendered figures. Nothing is removed
from what you see in Jupyter -- only from what git records.

Install the filter once per clone (it lives in .git/config, which is not
tracked):

    python tools/nbstrip.py --install

Manual use:

    python tools/nbstrip.py --check  notebooks-GP/*.ipynb   # what would change
    python tools/nbstrip.py --inplace notebooks-GP/*.ipynb  # rewrite the files
    python tools/nbstrip.py < in.ipynb > out.ipynb          # filter mode

Written to be dependency-free (no nbformat/nbstripout) so it works in any env
that can run python, including a bare git hook.
"""

import argparse
import json
import pathlib
import subprocess
import sys

# Cell-level metadata that changes on every execution and carries no meaning.
VOLATILE_CELL_METADATA = ("execution", "collapsed", "scrolled", "ExecuteTime")
# Notebook-level metadata that embeds widget state (can be megabytes).
VOLATILE_NB_METADATA = ("widgets",)


def strip(nb):
    """Strip a notebook dict in place. Returns True if anything changed."""
    changed = False

    for key in VOLATILE_NB_METADATA:
        if key in nb.get("metadata", {}):
            del nb["metadata"][key]
            changed = True

    for cell in nb.get("cells", []):
        if cell.get("cell_type") == "code":
            if cell.get("outputs"):
                cell["outputs"] = []
                changed = True
            elif "outputs" not in cell:
                # a code cell must still carry the key to stay valid nbformat
                cell["outputs"] = []
                changed = True
            if cell.get("execution_count") is not None:
                cell["execution_count"] = None
                changed = True

        meta = cell.get("metadata")
        if isinstance(meta, dict):
            for key in VOLATILE_CELL_METADATA:
                if key in meta:
                    del meta[key]
                    changed = True

    return changed


def dumps(nb, trailing_newline):
    """Serialize the way Jupyter does, so stripping alone creates no diff."""
    text = json.dumps(nb, indent=1, ensure_ascii=False, sort_keys=False)
    # json.dumps leaves trailing spaces on lines that open a container
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    return text + ("\n" if trailing_newline else "")


def process_text(text):
    nb = json.loads(text)
    changed = strip(nb)
    return dumps(nb, text.endswith("\n")), changed


def install():
    """Register the clean filter in this clone's .git/config."""
    root = pathlib.Path(__file__).resolve().parent.parent
    script = pathlib.Path(__file__).resolve().relative_to(root).as_posix()
    pairs = [
        # %f is the path git is filtering; quoted for paths containing spaces
        ("filter.nbstrip.clean", f'python "{script}"'),
        ("filter.nbstrip.smudge", "cat"),
    ]
    for key, value in pairs:
        subprocess.run(["git", "config", key, value], cwd=root, check=True)
        print(f"  git config {key} = {value}")
    print("\nnbstrip filter installed for this clone.")
    print("It applies to paths matching 'filter=nbstrip' in .gitattributes.")
    print("Uninstall with: git config --remove-section filter.nbstrip")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="*", type=pathlib.Path)
    ap.add_argument("--inplace", action="store_true", help="rewrite the files")
    ap.add_argument("--check", action="store_true",
                    help="report which files carry output; exit 1 if any do")
    ap.add_argument("--install", action="store_true",
                    help="register the git clean filter in this clone")
    args = ap.parse_args(argv)

    if args.install:
        return install()

    # filter mode: stdin -> stdout, byte-exact passthrough on any failure
    if not args.paths:
        raw = sys.stdin.buffer.read()
        try:
            text, _ = process_text(raw.decode("utf-8"))
            sys.stdout.buffer.write(text.encode("utf-8"))
        except Exception:
            # never destroy content because a notebook failed to parse
            sys.stdout.buffer.write(raw)
        return 0

    dirty = []
    for path in args.paths:
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError as exc:
            print(f"  skip  {path} ({exc})", file=sys.stderr)
            continue
        try:
            text, changed = process_text(raw)
        except json.JSONDecodeError as exc:
            print(f"  skip  {path} (not valid JSON: {exc})", file=sys.stderr)
            continue

        if changed:
            dirty.append(path)
            saved = len(raw) - len(text)
            if args.inplace:
                path.write_text(text, encoding="utf-8", newline="")
                print(f"  stripped  {path}  (-{saved:,} bytes)")
            else:
                print(f"  would strip  {path}  (-{saved:,} bytes)")
        elif not args.check:
            print(f"  clean     {path}")

    if args.check and dirty:
        print(f"\n{len(dirty)} notebook(s) carry output.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

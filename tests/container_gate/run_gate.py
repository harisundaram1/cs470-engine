#!/usr/bin/env python3
"""Execute the semantic gate notebook through a REAL kernel and report.

    python3 tests/container_gate/run_gate.py                 # local kernel (pre-image)
    python3 tests/container_gate/run_gate.py --image TAG     # print the docker invocation

LOCAL mode runs `gate.ipynb` via nbconvert's ExecutePreprocessor here — a real
ZMQInteractiveShell, so `apply_default_style()` fires retina exactly as it does in
the container. This validates the GATE LOGIC before any image exists (it does NOT
substitute for the in-container run: the container carries a different matplotlib,
which is why the gate prints its version — gate rule 7).

The in-container run (once the v0.11.1 image is built — a LATER pass, this pass
tags/deploys nothing) is a straight docker invocation of the SAME notebook; the
entrypoint override is mandatory or the image launches JupyterLab and "passes":

    docker run --rm --platform linux/amd64 -v "$PWD":/probe \
      --entrypoint jupyter cs470-workspace:<TAG> \
      nbconvert --to notebook --execute --output /probe/out.ipynb /probe/gate.ipynb
"""
import pathlib
import sys

import nbformat
from nbconvert.preprocessors import ExecutePreprocessor

HERE = pathlib.Path(__file__).resolve().parent
GATE = HERE / "gate.ipynb"

DOCKER_INVOCATION = (
    'docker run --rm --platform linux/amd64 -v "$PWD":/probe \\\n'
    "  --entrypoint jupyter cs470-workspace:{tag} \\\n"
    "  nbconvert --to notebook --execute --output /probe/out.ipynb /probe/gate.ipynb")


def run_local():
    if not GATE.exists():
        import build_gate
        build_gate.build()
    nb = nbformat.read(GATE, as_version=4)
    ep = ExecutePreprocessor(timeout=300, kernel_name="python3")
    try:
        ep.preprocess(nb, {"metadata": {"path": str(HERE)}})
    except Exception as exc:  # a failed assert in any cell surfaces here
        print("GATE FAILED (a cell raised):\n", exc)
        return 1
    # Echo the notebook's stream output (retina/version prints + OK lines).
    for cell in nb.cells:
        for out in cell.get("outputs", []):
            if out.get("output_type") == "stream":
                sys.stdout.write(out["text"])
            elif out.get("output_type") == "error":
                print("GATE FAILED:", "\n".join(out.get("traceback", [])))
                return 1
    print("\nGATE GREEN (local kernel). Run in-container against the v0.11.1 image "
          "before deploy.")
    return 0


def main(argv):
    if "--image" in argv:
        tag = argv[argv.index("--image") + 1]
        print("In-container invocation (run against the built v0.11.1 image):\n")
        print(DOCKER_INVOCATION.format(tag=tag))
        return 0
    return run_local()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

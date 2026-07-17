#!/usr/bin/env python3
"""Runs the semantic gate notebook LOCALLY (a real ZMQ kernel via nbconvert) and
asserts it passes — so the gate's LOGIC is CI-checked before any image exists.

This is NOT the in-container run (that needs the built v0.11.1 image and is a later
pass). It proves: the apply_default_style() precondition fires retina under a real
kernel; Tier A value-level assertions pass on the good figures; the anti-clamp and
frozen-ellipse RED CASES catch their bugs. The container run reuses the SAME
notebook (see tests/container_gate/run_gate.py --image).

Run: ``python3 tests/test_container_gate.py`` or via pytest.
"""
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
RUN_GATE = HERE / "container_gate" / "run_gate.py"


def test_semantic_gate_passes_locally():
    proc = subprocess.run([sys.executable, str(RUN_GATE)],
                          capture_output=True, text=True, timeout=420)
    assert proc.returncode == 0, (
        f"container gate failed (local kernel):\n{proc.stdout}\n{proc.stderr}")
    # the load-bearing precondition must be observable in the output
    assert "retina fired" in proc.stdout, proc.stdout
    assert "GATE PASSED" in proc.stdout, proc.stdout


if __name__ == "__main__":
    test_semantic_gate_passes_locally()
    print("  ok  test_semantic_gate_passes_locally")

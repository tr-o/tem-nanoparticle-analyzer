"""Explicit entry points, without claiming unvalidated models are production-ready."""
from __future__ import annotations

import argparse
import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PIPELINES = ROOT / "experiments"


def status() -> int:
    for label, file in [
        ("Synthetic example", ROOT / "run_demo.py"),
        ("Brightfield RF model", ROOT / "trained_rf.joblib"),
        ("DM3 I/O", PIPELINES / "v8/dm_io.py"),
        ("HRTEM exploratory pipeline", PIPELINES / "v8/hrtem_texture.py"),
        ("TEM/SEM boundary benchmark", PIPELINES / "v15/data_scale_benchmark.py"),
    ]:
        print(f"{'OK' if file.is_file() else 'MISSING'}: {label} — {file.relative_to(ROOT)}")
    for name in ("numpy", "cv2", "skimage", "sklearn", "rsciio", "gradio"):
        print(f"{name}: {'installed' if importlib.util.find_spec(name) else 'not installed (optional for some workflows)'}")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m tem_analyzer",
        description="Research-only TEM nanoparticle data pipelines. No certified particle-size precision.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("doctor", help="Show data files and available dependencies.")
    sub.add_parser("demo", help="Run the synthetic TEM 16+4 training/evaluation example.")
    sub.add_parser("gui", help="Run the experimental DM3/DM4 browser GUI.")
    inspect = sub.add_parser("dm-inspect", help="Inspect DM3/DM4 datasets and calibration.")
    inspect.add_argument("file")
    inspect.add_argument("--out", default="inspection.json")
    analyse = sub.add_parser("dm-analyze", help="Run an explicit research-only image analysis path.")
    analyse.add_argument("file")
    analyse.add_argument("--method", choices=("hrtem", "brightfield"), required=True)
    analyse.add_argument("--out", required=True)
    analyse.add_argument("--dataset-index", type=int, default=0)
    args = parser.parse_args(argv)
    if args.cmd == "doctor":
        return status()
    if args.cmd == "demo":
        command = [sys.executable, str(ROOT / "run_demo.py")]
    elif args.cmd == "gui":
        command = [sys.executable, str(PIPELINES / "v8/app_dm.py")]
    elif args.cmd == "dm-inspect":
        command = [sys.executable, str(PIPELINES / "v8/inspect_dm.py"),
                   args.file, "--out", args.out]
    else:
        script = ("hrtem_texture.py" if args.method == "hrtem" else "analyze_dm.py")
        command = [sys.executable, str(PIPELINES / "v8" / script), "--image", args.file,
                   "--output", args.out, "--dataset-index", str(args.dataset_index)]
        if args.method == "brightfield":
            command.extend(["--model", str(ROOT / "trained_rf.joblib")])
    return subprocess.call(command, cwd=str(ROOT))


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Export YOLO11n to CoreML for the gnome.

The weights are AGPL-3.0 (Ultralytics), which is fine for this private project.

Run this through a 3.11 virtual environment, not the system Python:

    uv venv --python /opt/homebrew/bin/python3.11 .venv-model
    .venv-model/bin/pip install -r tools/requirements-model.txt
    .venv-model/bin/python tools/export_model.py
"""

import argparse
import shutil
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DESTINATION = REPO / "ios" / "DwarfApp" / "App" / "Models"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--weights", default="yolo11n.pt",
                        help="downloaded on first run if absent")
    parser.add_argument("--imgsz", type=int, default=640,
                        help="640 is the M0 target; 416 and 320 are the fallbacks if the "
                             "6s cannot sustain three inferences a second")
    parser.add_argument("--half", action="store_true",
                        help="FP16 weights. Smaller and usually faster on the A9's GPU, "
                             "which has no Neural Engine to fall back on. Try this first "
                             "if M0 misses its target before dropping imgsz")
    args = parser.parse_args()

    from ultralytics import YOLO

    model = YOLO(args.weights)
    # nms=True embeds Apple's NonMaximumSuppression stage in the model, so the app gets
    # boxes rather than a raw prediction tensor it would have to sort out itself on the
    # phone's CPU.
    exported = model.export(format="coreml", imgsz=args.imgsz, nms=True, half=args.half)

    DESTINATION.mkdir(parents=True, exist_ok=True)
    target = DESTINATION / "yolo11n.mlpackage"
    if target.exists():
        shutil.rmtree(target)
    shutil.move(str(exported), str(target))

    print(f"wrote {target}")
    print("input size:", args.imgsz, "half:", args.half)


if __name__ == "__main__":
    main()

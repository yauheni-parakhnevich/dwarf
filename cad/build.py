#!/usr/bin/env python
"""Build the printed parts. Stages: mech, shell, assemble, preview. No argument runs all."""
import os
import subprocess
import sys
from pathlib import Path

CAD = Path(__file__).resolve().parent
sys.path.insert(0, str(CAD))
BLENDER = os.environ.get("BLENDER", "/Applications/Blender.app/Contents/MacOS/Blender")


def mech():
    import mech  # noqa: F401  (registers builders)
    import mech.turntable, mech.torso, mech.head, mech.base  # noqa: E401,F401
    from mech.common import export
    from mech import ALL
    for name, builder in ALL:
        print(f"mech  {name}")
        export(builder(), name)


def blender(script):
    subprocess.run([BLENDER, "-b", "--python", str(CAD / "shell" / script)], check=True)


def shell():
    for script in ("body.py", "head.py", "beard.py"):
        print(f"shell {script}")
        blender(script)


def assemble():
    import assemble as a
    a.main()


def preview():
    blender("preview.py")


STAGES = {"mech": mech, "shell": shell, "assemble": assemble, "preview": preview}

if __name__ == "__main__":
    names = sys.argv[1:] or list(STAGES)
    for n in names:
        STAGES[n]()

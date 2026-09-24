#!/usr/bin/env python
"""Build the printed parts.

Stages: mech, statue, shell, assemble, preview, scene. No argument runs all of them, in that
order. `shell` is a stub the statue stage replaced; it is kept so the list still reads as the
pipeline it was.
"""
import os
import subprocess
import sys
import time
from pathlib import Path

CAD = Path(__file__).resolve().parent
sys.path.insert(0, str(CAD))
BLENDER = os.environ.get("BLENDER", "/Applications/Blender.app/Contents/MacOS/Blender")
OUT = CAD / "out"


def mech():
    import mech  # noqa: F401  (registers builders)
    import mech.turntable, mech.torso, mech.head, mech.base  # noqa: E401,F401
    from build123d import export_step, export_stl
    from mech.common import assembly, export, STEP, STL
    from mech import ALL
    built = {}
    for spec in ALL:                       # export() writes the print frame, not the assembly
        print(f"mech  {spec.name}")
        built[spec.name] = spec.build()
        export(built[spec.name], spec.name)
    print("mech  mechanism_assembly")
    whole = assembly(built)
    if not export_step(whole, str(STEP / "mechanism_assembly.step")):
        raise RuntimeError("STEP export failed: mechanism_assembly")
    # and as a mesh, because the preview renders in Blender and Blender cannot read STEP
    if not export_stl(whole, str(STL / "mechanism_assembly.stl"), tolerance=0.05, angular_tolerance=0.1):
        raise RuntimeError("STL export failed: mechanism_assembly")


def blender(script, wants=(), fresh_in=None):
    """Run a Blender script and prove it did something.

    Blender exits 0 when a `--python` script raises: it prints the traceback and quits happily.
    Nothing downstream would notice - assemble would read the last good build's meshes, the
    tests would pass on them, and the only clue would be a traceback scrolled off the top of
    the log. So every file the script owns is deleted first and then checked for, by mtime as
    well as by name, and the stage raises if anything is missing or stale.

    `wants` are files that must all be rewritten; `fresh_in` is a (directory, pattern) pair
    where at least one file must be.
    """
    t0 = time.time()
    for f in wants:
        f.unlink(missing_ok=True)
    subprocess.run([BLENDER, "-b", "--python", str(CAD / "shell" / script)], check=True)
    missing = [f.name for f in wants if not (f.exists() and f.stat().st_mtime >= t0)]
    if missing:
        raise RuntimeError(f"{script} exited 0 but left no fresh {', '.join(missing)}; "
                           f"Blender does not fail on a script's exception - read its traceback above")
    if fresh_in is not None:
        where, pattern = fresh_in
        if not any(f.stat().st_mtime >= t0 for f in where.glob(pattern)):
            raise RuntimeError(f"{script} exited 0 but wrote no fresh {pattern} in {where}; "
                               f"Blender does not fail on a script's exception")


def statue():
    """The statue becomes the shell: frame, hollow, features, raw sections, previews."""
    import statue as s
    s.main()


def shell():
    """Nothing. The sculpted shell was replaced by the statue.

    Four Blender scripts once carved the gnome out of revolves and relief, before there was a
    statue to print. They are gone: the skin comes from `in/gnome_ai.glb` through the `statue`
    stage, nothing imported them, and running them would only have overwritten `out/raw` with
    a shell nothing reads. Their history is in the log if the swell functions are ever wanted
    again. The stage stays so the pipeline still names the step the statue took over.
    """
    print("shell skipped: the sections come from the statue stage (build.py statue)")


def assemble():
    import assemble as a
    a.main()


def preview():
    blender("preview.py", fresh_in=(OUT / "preview", "*.png"))


def scene():
    """Write out/placements.json from the registry, then build out/gnome.blend: every section and
    part as its own object, in collections, in assembled position. Open it in Blender to inspect."""
    import json
    import mech.turntable, mech.torso, mech.head, mech.base  # noqa: E401,F401
    from mech import ALL, INTERFACES
    interface = {n: sec for sec, names in INTERFACES.items() for n in names}
    placements = {}
    for spec in ALL:
        t = spec.placement.wrapped.Transformation()
        rows = [[t.Value(r, c) for c in range(1, 5)] for r in range(1, 4)] + [[0, 0, 0, 1]]
        placements[spec.name] = {"matrix": rows, "section": interface.get(spec.name)}
    (OUT / "placements.json").write_text(json.dumps(placements, indent=1))
    blender("scene.py", wants=[OUT / "gnome.blend"])


STAGES = {"mech": mech, "statue": statue, "shell": shell, "assemble": assemble, "preview": preview, "scene": scene}

if __name__ == "__main__":
    names = sys.argv[1:] or list(STAGES)
    unknown = [n for n in names if n not in STAGES]
    if unknown:
        sys.exit(f"unknown stage {unknown}; stages are {', '.join(STAGES)}")
    for n in names:
        STAGES[n]()

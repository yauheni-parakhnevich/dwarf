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
    import mech; mech.load_all()
    from build123d import export_step, export_stl
    from mech.common import assembly, export, STEP, STL
    from mech import ALL
    built = {}
    for spec in ALL:                       # export() writes the print frame, not the assembly
        print(f"mech  {spec.name}")
        built[spec.name] = spec.build()
        export(built[spec.name], spec.name)
    placements()
    bought()
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


def placements():
    """out/placements.json from the registry: where each part's print frame lands, which shell
    section an interface part joins, and how it moves - what the scene, the previews and the pose
    tests read rather than keeping their own copy."""
    import json
    import mech; mech.load_all()
    from mech import ALL, INTERFACES, LINKAGE, NODS, PANS
    interface = {n: sec for sec, names in INTERFACES.items() for n in names}
    out = {}
    for spec in ALL:
        t = spec.placement.wrapped.Transformation()
        rows = [[t.Value(r, c) for c in range(1, 5)] for r in range(1, 4)] + [[0, 0, 0, 1]]
        moves = ("nods" if spec.name in NODS else "pans" if spec.name in PANS
                 else spec.name if spec.name in LINKAGE else "fixed")
        out[spec.name] = {"matrix": rows, "section": interface.get(spec.name), "moves": moves}
    (OUT / "placements.json").write_text(json.dumps(out, indent=1))


POSES = ((0.0, 0.0), (65.0, 0.0), (0.0, -15.0), (65.0, -15.0))    # the ones the previews show


def bought():
    """The bought parts as envelopes, to out/stl/bought/, and out/bought.json saying how each
    moves - so Blender, which has no build123d, can draw them. The tube bends with the nod, so it
    is written once per pose in POSES (and at rest), named tube_<pan>_<nod>."""
    import json
    from build123d import export_stl
    import mech; mech.load_all()
    from mech import nod as N
    from mech.common import box, cyl_z, phone_body, servo_body
    import params as P
    where = OUT / "stl" / "bought"
    where.mkdir(parents=True, exist_ok=True)
    shapes = {n: (s, how) for n, (s, how) in N.nod_bought().items()}
    shapes["pan_servo"] = (servo_body(P.DS3218, (P.PAN_SERVO_XY[0], P.PAN_SERVO_XY[1], P.Z_PAN_SHAFT_FACE),
                                      axis="-z"), "fixed")
    fx, fy, fh, z = P.FAN_XY[0], P.FAN_XY[1], P.FAN / 2, P.Z_DECK - P.DECK_T
    shapes["fan"] = (box(fx - fh, fx + fh, fy - fh, fy + fh, z - P.FAN_T, z), "fixed")
    shapes["bearing"] = (cyl_z(P.BEARING_OD / 2, P.Z_BEARING, P.Z_BEARING + P.BEARING_B)
                         - cyl_z(P.BEARING_ID / 2, P.Z_BEARING - 1, P.Z_BEARING + P.BEARING_B + 1), "fixed")
    shapes["phone"] = (phone_body(), "fixed")
    for pan, nod in POSES:
        shapes[f"tube_{pan:+.0f}_{nod:+.0f}"] = (N.tube_route(pan, nod), f"pose {pan} {nod}")
    manifest = {}
    for name, (shape, how) in shapes.items():
        export_stl(shape, str(where / f"{name}.stl"), tolerance=0.05, angular_tolerance=0.1)
        manifest[name] = how
    (OUT / "bought.json").write_text(json.dumps(manifest, indent=1))


def scene():
    """Build out/gnome.blend: every section and part as its own object, in collections, in
    assembled position, posed by the POSE environment variable ("pan,nod"). Open it in Blender."""
    placements()
    blender("scene.py", wants=[OUT / "gnome.blend"])


STAGES = {"mech": mech, "statue": statue, "shell": shell, "assemble": assemble, "preview": preview, "scene": scene}

if __name__ == "__main__":
    names = sys.argv[1:] or list(STAGES)
    unknown = [n for n in names if n not in STAGES]
    if unknown:
        sys.exit(f"unknown stage {unknown}; stages are {', '.join(STAGES)}")
    for n in names:
        STAGES[n]()

"""Build cad/out/gnome.blend: every printable section and mechanism part as its own object,
in collections, in assembled position and in a pose. Run by build.py's `scene` stage or by hand:
    POSE=65,-15 /Applications/Blender.app/Contents/MacOS/Blender -b --python cad/shell/scene.py
Then open cad/out/gnome.blend in Blender.

How each part moves is not decided here: out/placements.json (written by the mech stage) says
it for the printed parts - "fixed", "pans", "nods", or the linkage's own name - and
out/bought.json for the bought parts' envelopes in out/stl/bought/. The shell's beard, head and hat
nod. A pose is a pan about Z and then a nod about Y, both about C = (0, 0, Z_NOD); the nod is the
firmware's sign, nose up positive.
"""
import json
import math
import os
import sys
from pathlib import Path

import bpy
from mathutils import Matrix, Vector

CAD = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CAD))
import params as P  # noqa: E402

STL = CAD / "out" / "stl"
SECTIONS = tuple(P.PRINTED_SECTIONS)         # the statue's sections, from params
UNIT = ("beard_left", "beard_right", "head", "hat")             # glued into the turning unit
placements = json.load(open(CAD / "out" / "placements.json"))
bought = json.load(open(CAD / "out" / "bought.json"))
PAN, NOD = (float(x) for x in os.environ.get("POSE", "0,0").split(","))


def motion(how):
    """The world matrix that carries a part that moves `how` to the pose."""
    c = Vector((0.0, 0.0, P.Z_NOD))
    pan = Matrix.Rotation(math.radians(PAN), 4, "Z")
    if how == "nods":
        return (Matrix.Translation(c) @ pan @ Matrix.Rotation(math.radians(-NOD), 4, "Y")
                @ Matrix.Translation(-c))
    if how == "pans":
        return pan
    if how == "servo_crank":
        s = Vector((P.PAN_SERVO_XY[0], P.PAN_SERVO_XY[1], 0.0))
        return Matrix.Translation(s) @ pan @ Matrix.Translation(-s)
    if how == "pan_link":
        rest, _ = P.crank_pins(0)
        pin, _ = P.crank_pins(PAN)
        return Matrix.Translation((pin[0] - rest[0], pin[1] - rest[1], 0.0))
    return Matrix.Identity(4)


bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
sc.unit_settings.system = "METRIC"
sc.unit_settings.scale_length = 0.001


def collection(name, parent=None):
    col = bpy.data.collections.new(name)
    (parent or sc.collection).children.link(col)
    return col


def load(path, name, col, matrix=None, color=(0.8, 0.8, 0.8, 1.0), wire=False):
    bpy.ops.wm.stl_import(filepath=str(path))
    ob = bpy.context.selected_objects[0]
    ob.name = name
    for c in ob.users_collection:
        c.objects.unlink(ob)
    col.objects.link(ob)
    if matrix is not None:
        ob.matrix_world = matrix
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = color
    ob.data.materials.append(mat)
    if wire:
        ob.display_type = "WIRE"
    return ob


shell = collection("Shell")
mech = collection("Mechanism")
groups = {
    "fixed": collection("fixed", mech),
    "pans": collection("pans with the plate", mech),
    "nods": collection("pans and nods with the head", mech),
    "linkage": collection("pan linkage", mech),
    "interface": collection("interface (printed with the shell)", mech),
}
env = collection("Bought parts (envelopes)")

# The turning unit is tinted apart from the fixed shell, because which is which is the thing to see.
for n in SECTIONS:
    if (STL / f"{n}.stl").exists():
        load(STL / f"{n}.stl", f"shell:{n}", shell, matrix=motion("nods" if n in UNIT else "fixed"),
             color=(0.9, 0.55, 0.45, 1) if n in UNIT else (0.55, 0.6, 0.75, 1))

for name, info in placements.items():
    p = STL / f"{name}.stl"
    if not p.exists():
        continue
    how = info.get("moves", "fixed")
    col = (groups["interface"] if info["section"] else
           groups["linkage"] if how in ("servo_crank", "pan_link") else groups[how])
    m = motion(how) @ Matrix(info["matrix"])
    load(p, f"mech:{name}", col, matrix=m, color=(0.75, 0.75, 0.8, 1))
    if name == "stop_pin":
        load(p, "mech:stop_pin_mirrored", col, matrix=Matrix.Scale(-1, 4, (0, 1, 0)) @ m,
             color=(0.75, 0.75, 0.8, 1))

tube = f"tube_{PAN:+.0f}_{NOD:+.0f}"
if tube not in bought:
    print(f"scene: no tube written for pose {PAN}, {NOD}; drawing it at rest")
    tube = "tube_+0_+0"
for name, how in bought.items():
    if name.startswith("tube_") and name != tube:
        continue
    colour = {"nod_servo": (0.9, 0.6, 0.2, 1), "pan_servo": (0.9, 0.6, 0.2, 1),
              "phone": (0.1, 0.1, 0.1, 1)}.get(name, (0.6, 0.6, 0.65, 1))
    m = Matrix.Identity(4) if name.startswith("tube_") else motion(how)
    load(STL / "bought" / f"{name}.stl", "tube" if name.startswith("tube_") else name, env,
         matrix=m, color=(0.2, 0.5, 0.9, 1) if name.startswith("tube_") else colour,
         wire=name in ("phone",))


def box(name, x0, x1, y0, y1, z0, z1, color):
    bpy.ops.mesh.primitive_cube_add(size=1, location=((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2))
    ob = bpy.context.object
    ob.scale = (x1 - x0, y1 - y0, z1 - z0)
    ob.name = name
    for c in ob.users_collection:
        c.objects.unlink(ob)
    env.objects.link(ob)
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = color
    ob.data.materials.append(mat)
    ob.display_type = "WIRE"


def legs():
    """The trouser legs the statue stage measured, as mech.torso.measured_legs reads them (read
    here because this runs inside Blender, which has no build123d)."""
    m = json.load(open(CAD / "out" / "statue" / "features.json"))["legs"]
    return tuple(m["left"][:2]), tuple(m["right"][:2])


L, W, H = P.BOTTLE
cx, cy = P.BOTTLE_XY
box("bottle", cx - L / 2, cx + L / 2, cy - W / 2, cy + W / 2, P.BOTTLE_Z0, P.BOTTLE_Z0 + H,
    (0.3, 0.5, 0.9, 1))
left, right = legs()
for name, (L, W, H), (cx, cy), z0 in (("pump", P.PUMP, left, P.PUMP_Z0),
                                      ("valve", P.VALVE, right, P.VALVE_Z0)):
    box(name, cx - L / 2, cx + L / 2, cy - W / 2, cy + W / 2, z0, z0 + H, (0.3, 0.7, 0.4, 1))

# viewport: solid shading with object colours
sc.render.engine = "BLENDER_WORKBENCH"
sc.display.shading.color_type = "MATERIAL"
out = CAD / "out" / "gnome.blend"
bpy.ops.wm.save_as_mainfile(filepath=str(out))
print("saved", out, len(bpy.data.objects), "objects", f"at pan {PAN:+.0f}, nod {NOD:+.0f}")

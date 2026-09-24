"""Build cad/out/gnome.blend: every printable section and mechanism part as its own object,
in collections, in assembled position. Run by build.py's `scene` stage or by hand:
    /Applications/Blender.app/Contents/MacOS/Blender -b --python cad/shell/scene.py
Then open cad/out/gnome.blend in Blender.
"""
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Matrix

CAD = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CAD))
import params as P  # noqa: E402

STL = CAD / "out" / "stl"
SECTIONS = tuple(P.SECTIONS_STATUE)         # the statue's sections, from params
placements = json.load(open(CAD / "out" / "placements.json"))

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
sc.unit_settings.system = "METRIC"
sc.unit_settings.scale_length = 0.001


def collection(name, parent=None):
    col = bpy.data.collections.new(name)
    (parent or sc.collection).children.link(col)
    return col


def load(path, name, col, matrix=None, color=(0.8, 0.8, 0.8, 1.0)):
    bpy.ops.wm.stl_import(filepath=str(path))
    ob = bpy.context.selected_objects[0]
    ob.name = name
    for c in ob.users_collection:
        c.objects.unlink(ob)
    col.objects.link(ob)
    if matrix is not None:
        ob.matrix_world = Matrix(matrix)
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = color
    ob.data.materials.append(mat)
    return ob


shell = collection("Shell")
mech = collection("Mechanism")
groups = {
    "turns with the head": collection("turns with the head", mech),
    "nods with the head": collection("nods with the head", mech),
    "fixed": collection("fixed", mech),
    "interface (printed with the shell)": collection("interface (printed with the shell)", mech),
}
NODS = {"nozzle_arm"}                       # only the nozzle tilts now; the head is one shell
TURNS = {"plate", "shaft", "neck_shroud", "tilt_bracket", "servo_crank", "pan_link"}

# The bell is tinted apart from the fixed shell, because which is which is the thing to see.
BELL = ("beard", "head", "hat")
for n in SECTIONS:
    if (STL / f"{n}.stl").exists():
        load(STL / f"{n}.stl", f"shell:{n}", shell,
             color=(0.9, 0.55, 0.45, 1) if n in BELL else (0.55, 0.6, 0.75, 1))

for name, info in placements.items():
    p = STL / f"{name}.stl"
    if not p.exists():
        continue
    if info["section"]:
        col = groups["interface (printed with the shell)"]
    elif name in NODS:
        col = groups["nods with the head"]
    elif name in TURNS:
        col = groups["turns with the head"]
    else:
        col = groups["fixed"]
    load(p, f"mech:{name}", col, matrix=info["matrix"], color=(0.75, 0.75, 0.8, 1))
    if name == "stop_pin":
        m = Matrix(info["matrix"])
        mirror = Matrix.Scale(-1, 4, (0, 1, 0))
        load(p, "mech:stop_pin_mirrored", col, matrix=mirror @ m, color=(0.75, 0.75, 0.8, 1))

# bought-part envelopes, so the cavities read
env = collection("Bought parts (envelopes)")


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
    """The trouser legs the statue stage measured, as mech.torso.measured_legs reads them.

    It is read here rather than imported because this file runs inside Blender, which has no
    build123d - and the parameters' LEG_LEFT_XY is 41 mm from where the mesh puts the leg, so
    drawing the pump there would draw it somewhere it does not go.
    """
    try:
        m = json.load(open(CAD / "out" / "statue" / "features.json"))["legs"]
        return tuple(m["left"][:2]), tuple(m["right"][:2])
    except (OSError, KeyError, ValueError):
        return P.LEG_LEFT_XY, P.LEG_RIGHT_XY


L, W, H = P.BOTTLE
cx, cy = P.BOTTLE_XY
box("bottle", cx - L / 2, cx + L / 2, cy - W / 2, cy + W / 2, P.BOTTLE_Z0, P.BOTTLE_Z0 + H,
    (0.3, 0.5, 0.9, 1))
left, right = legs()
for name, (L, W, H), (cx, cy), z0 in (("pump", P.PUMP, left, P.PUMP_Z0),
                                      ("valve", P.VALVE, right, P.VALVE_Z0)):
    box(name, cx - L / 2, cx + L / 2, cy - W / 2, cy + W / 2, z0, z0 + H, (0.3, 0.7, 0.4, 1))
box("phone", P.PHONE_FRONT_X, P.PHONE_BACK_X, P.PHONE_Y_OFFSET - P.PHONE_W / 2, P.PHONE_Y_OFFSET + P.PHONE_W / 2,
    P.PHONE_BOTTOM_Z, P.PHONE_BOTTOM_Z + P.PHONE_L, (0.1, 0.1, 0.1, 1))
Ls, Ws, Hs = P.DS3218["body"]
sx, sy = P.PAN_SERVO_XY
box("pan servo", sx - P.DS3218["shaft_off"], sx + Ls - P.DS3218["shaft_off"], sy - Ws / 2, sy + Ws / 2,
    P.Z_PAN_SHAFT_FACE, P.Z_PAN_SHAFT_FACE + Hs, (0.9, 0.6, 0.2, 1))
# the tilt servo is a micro one on the tilt bracket now, not an MG996R in the head: shaft along
# +Y at the nozzle's pivot, body running out to -Y and hanging downward. This is what
# mech.turntable._tilt_servo draws, by way of mech.common.servo_body's "y" with up=False.
Ls, Ws, Hs = P.MG92B["body"]
off = P.MG92B["shaft_off"]
sx, sy, sz = P.NOZZLE_PIVOT[0], -8.0, P.NOZZLE_PIVOT[2]          # SERVO_SHAFT_Y in mech.turntable
box("tilt servo", sx - Ws / 2, sx + Ws / 2, sy - Hs, sy, sz - (Ls - off), sz + off,
    (0.9, 0.6, 0.2, 1))
box("bearing", -P.BEARING_SQ / 2, P.BEARING_SQ / 2, -P.BEARING_SQ / 2, P.BEARING_SQ / 2, P.Z_DECK, P.Z_DECK + P.BEARING_T, (0.6, 0.6, 0.6, 1))

# viewport: solid shading with object colours
sc.render.engine = "BLENDER_WORKBENCH"
sc.display.shading.color_type = "MATERIAL"
out = CAD / "out" / "gnome.blend"
bpy.ops.wm.save_as_mainfile(filepath=str(out))
print("saved", out, len(bpy.data.objects), "objects")

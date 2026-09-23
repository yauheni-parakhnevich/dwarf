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
SECTIONS = ("base", "torso", "belly", "head_back", "face", "hat")
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
NODS = {"coupler", "ear_boss", "tilt_cradle", "cradle_rails", "face_stop", "head_lip", "nozzle_holder", "nozzle_bosses"}
TURNS = {"plate", "shaft", "yoke", "neck_shroud", "servo_crank", "pan_link"}

tint = {"base": (0.55, 0.6, 0.75, 1), "torso": (0.55, 0.6, 0.75, 1), "belly": (0.6, 0.7, 0.8, 1),
        "head_back": (0.9, 0.75, 0.65, 1), "face": (0.9, 0.75, 0.65, 1),
        "hat": (0.8, 0.3, 0.3, 1)}
for n in SECTIONS:
    if (STL / f"{n}.stl").exists():
        load(STL / f"{n}.stl", f"shell:{n}", shell, color=tint[n])

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


L, W, H = P.CANISTER
cx, cy = P.CANISTER_XY
box("canister", cx - L / 2, cx + L / 2, cy - W / 2, cy + W / 2, P.CANISTER_Z0, P.CANISTER_Z0 + H, (0.3, 0.5, 0.9, 1))
L, W, H = P.PUMP
cx, cy = P.PUMP_XY
box("pump", cx - L / 2, cx + L / 2, cy - W / 2, cy + W / 2, P.PUMP_Z0, P.PUMP_Z0 + H, (0.3, 0.7, 0.4, 1))
L, W, H = P.VALVE
cx, cy = P.VALVE_XY
box("valve", cx - L / 2, cx + L / 2, cy - W / 2, cy + W / 2, P.PUMP_Z0, P.PUMP_Z0 + H, (0.3, 0.7, 0.4, 1))
box("phone", P.PHONE_FRONT_X, P.PHONE_BACK_X, P.PHONE_Y_OFFSET - P.PHONE_W / 2, P.PHONE_Y_OFFSET + P.PHONE_W / 2,
    P.PHONE_BOTTOM_Z, P.PHONE_BOTTOM_Z + P.PHONE_L, (0.1, 0.1, 0.1, 1))
Ls, Ws, Hs = P.DS3218["body"]
sx, sy = P.PAN_SERVO_XY
box("pan servo", sx - P.DS3218["shaft_off"], sx + Ls - P.DS3218["shaft_off"], sy - Ws / 2, sy + Ws / 2,
    P.Z_PAN_SHAFT_FACE, P.Z_PAN_SHAFT_FACE + Hs, (0.9, 0.6, 0.2, 1))
Ls, Ws, Hs = P.MG996R["body"]
box("tilt servo", -Ws / 2, Ws / 2, P.TILT_SERVO_SHAFT_Y - Hs, P.TILT_SERVO_SHAFT_Y,
    P.Z_HEAD - P.MG996R["shaft_off"], P.Z_HEAD + Ls - P.MG996R["shaft_off"], (0.9, 0.6, 0.2, 1))
box("bearing", -P.BEARING_SQ / 2, P.BEARING_SQ / 2, -P.BEARING_SQ / 2, P.BEARING_SQ / 2, P.Z_DECK, P.Z_DECK + P.BEARING_T, (0.6, 0.6, 0.6, 1))

# viewport: solid shading with object colours, clip far enough
for area in bpy.context.screen.areas if bpy.context.screen else []:
    pass
sc.render.engine = "BLENDER_WORKBENCH"
sc.display.shading.color_type = "MATERIAL"
out = CAD / "out" / "gnome.blend"
bpy.ops.wm.save_as_mainfile(filepath=str(out))
print("saved", out, len(bpy.data.objects), "objects")

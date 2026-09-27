"""Render the statue, its sections, and the parting as it moves. Blender only; `statue.py` drives it.

Three questions and then a fourth. Does the skin still look like the gnome the image-to-3D made
(front, side, iso, off `outer.stl`)? Where does every cut fall (`preview_sections`, the raw
sections in their own colours, pulled apart along the axis)? And is there a cavity in there at
all (`preview_cut`, the shell bisected at y = 0)? The cut is a bmesh bisect, not a boolean, so
the walls show as open edges - which is what a section drawing looks like anyway.

The fourth is the parting, and it is the only one that has to be looked at in motion: the
`parting_*.png` set in `out/preview/` puts the turning unit - beard, head, hat - in a colour
over the fixed coat in clay, and turns it about C = (0, 0, Z_NOD) through pan and nod. What to
look for is the bib the pan uncovers, the beard's outline against it, the collar seam round the
nape, and, at nose-down, how close the beard's trimmed bottom edge comes to the coat.
"""
import math
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Matrix, Vector

CAD = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CAD))
import params as P  # noqa: E402

OUT = CAD / "out" / "statue"
RAW = OUT / "raw"
PNG = CAD / "out" / "preview"
SIZE = 900
CLAY = (0.62, 0.60, 0.57)
COLOURS = {
    "base_left": (0.45, 0.47, 0.52), "base_right": (0.34, 0.36, 0.40),
    "hand_left": (0.83, 0.66, 0.36), "hand_right": (0.72, 0.56, 0.30),
    "torso": (0.66, 0.30, 0.26), "collar": (0.58, 0.40, 0.30), "panel_left": (0.40, 0.58, 0.40), "panel_right": (0.30, 0.48, 0.33),
    "beard": (0.78, 0.78, 0.80), "head": (0.80, 0.62, 0.52), "hat": (0.30, 0.45, 0.62),
}
MOVING = {"beard": (0.80, 0.42, 0.32), "head": (0.82, 0.50, 0.40), "hat": (0.62, 0.30, 0.26)}
LIFT = {"base_left": 0, "base_right": 0, "hand_left": 20, "hand_right": 20,
        "torso": 45, "collar": 65, "panel_left": 45, "panel_right": 45,
        "beard": 85, "head": 115, "hat": 145}
SPREAD = {"hand_left": 40.0, "hand_right": -40.0, "panel_left": 55.0, "panel_right": -55.0}


def mat(name, rgb, rough=0.75):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*rgb, 1.0)
    b.inputs["Roughness"].default_value = rough
    return m


def scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.engine = "BLENDER_EEVEE"
    sc.render.resolution_x = sc.render.resolution_y = SIZE
    sc.eevee.taa_render_samples = 48
    sc.eevee.use_raytracing = True
    sc.world = bpy.data.worlds.new("w")
    sc.world.use_nodes = True
    sc.world.node_tree.nodes["Background"].inputs[0].default_value = (0.09, 0.10, 0.12, 1.0)
    sc.world.node_tree.nodes["Background"].inputs[1].default_value = 1.6
    for energy, rot in ((4.0, (54.0, 0.0, -52.0)), (1.2, (70.0, 0.0, 150.0))):
        light = bpy.data.lights.new("sun", "SUN")
        light.energy = energy
        light.angle = math.radians(6.0)
        ob = bpy.data.objects.new("sun", light)
        sc.collection.objects.link(ob)
        ob.rotation_euler = tuple(math.radians(a) for a in rot)
    cam = bpy.data.cameras.new("c")
    cam.type = "ORTHO"
    cam.clip_start, cam.clip_end = 1.0, 8000.0
    co = bpy.data.objects.new("c", cam)
    sc.collection.objects.link(co)
    sc.camera = co
    return sc, co


def load(path, rgb, name=None):
    bpy.ops.wm.stl_import(filepath=str(path))
    ob = bpy.context.object
    ob.data.materials.append(mat(name or path.stem, rgb))
    ob.data.polygons.foreach_set("use_smooth", [True] * len(ob.data.polygons))
    return ob


def halve(ob):
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:], dist=0.0,
                           plane_co=(0.0, 0.0, 0.0), plane_no=(0.0, 1.0, 0.0),
                           clear_inner=True, clear_outer=False)
    bm.to_mesh(ob.data)
    bm.free()
    return ob


def bounds(objects):
    pts = [ob.matrix_world @ Vector(c) for ob in objects for c in ob.bound_box]
    lo = [min(p[i] for p in pts) for i in range(3)]
    hi = [max(p[i] for p in pts) for i in range(3)]
    return [(a + b) / 2 for a, b in zip(lo, hi)], max(b - a for a, b in zip(lo, hi))


def offset(rx, rz):
    a, b = math.radians(rx), math.radians(rz)
    return (math.sin(a) * math.sin(b), -math.sin(a) * math.cos(b), math.cos(a))


def shoot(sc, co, name, objects, rx, rz, pad=1.12):
    centre, span = bounds(objects)
    co.data.ortho_scale = span * pad
    co.location = [c + o * 2500.0 for c, o in zip(centre, offset(rx, rz))]
    co.rotation_euler = (math.radians(rx), 0.0, math.radians(rz))
    sc.render.filepath = str(OUT / f"preview_{name}.png")
    bpy.ops.render.render(write_still=True)
    print(f"preview {name}")


OUT.mkdir(parents=True, exist_ok=True)
for view, (rx, rz) in {"front": (90.0, 90.0), "side": (90.0, 0.0), "iso": (75.0, 45.0)}.items():
    sc, co = scene()
    ob = load(OUT / "outer.stl", CLAY)
    shoot(sc, co, view, [ob], rx, rz)

sc, co = scene()
obs = []
for name, rgb in COLOURS.items():
    ob = load(RAW / f"{name}.stl", rgb)
    ob.location = (0.0, SPREAD.get(name, 0.0), float(LIFT[name]))
    obs.append(ob)
shoot(sc, co, "sections", obs, 75.0, 45.0, pad=1.2)

sc, co = scene()
ob = halve(load(OUT / "shell.stl", CLAY))
shoot(sc, co, "cut", [ob], 90.0, 0.0)

# the turning unit alone, front and three-quarter
for view, (rx, rz) in {"bell": (80.0, 90.0), "bell_iso": (75.0, 50.0)}.items():
    sc, co = scene()
    obs = [load(RAW / f"{n}.stl", COLOURS[n]) for n in ("beard", "head", "hat")]
    shoot(sc, co, view, obs, rx, rz)

# the statue as it stands: the fixed shell in clay, the turning unit in a colour, so the seams read
sc, co = scene()
obs = [load(RAW / f"{n}.stl", CLAY if n not in MOVING else (0.72, 0.42, 0.34))
       for n in COLOURS]
shoot(sc, co, "assembled", obs, 80.0, 70.0)


# --- the parting, in motion ------------------------------------------------------------------

def pose(objects, pan, nod):
    """Pan about Z and nod about Y, both about C = (0, 0, Z_NOD). Positive nod is nose up, which
    about +Y is negative, because the nose is on +X - the same convention `statue.turned` uses."""
    c = Vector((0.0, 0.0, P.Z_NOD))
    m = (Matrix.Translation(c) @ Matrix.Rotation(math.radians(pan), 4, "Z")
         @ Matrix.Rotation(math.radians(-nod), 4, "Y") @ Matrix.Translation(-c))
    for ob in objects:
        ob.matrix_world = m @ ob.matrix_world


def parting(name, pan, nod, views, halve_fixed=False, centre=None, span=None, pad=1.08):
    for view, (rx, rz) in views.items():
        sc, co = scene()
        fixed = [load(RAW / f"{n}.stl", CLAY) for n in COLOURS if n not in MOVING]
        if halve_fixed:
            for ob in fixed:
                halve(ob)
        unit = [load(RAW / f"{n}.stl", MOVING[n]) for n in MOVING]
        pose(unit, pan, nod)
        cam = centre if centre is not None else (0.0, 0.0, P.Z_TOP / 2)
        wide = span if span is not None else P.Z_TOP * 1.02
        co.data.ortho_scale = wide * pad
        co.location = [a + b * 2500.0 for a, b in zip(cam, offset(rx, rz))]
        co.rotation_euler = (math.radians(rx), 0.0, math.radians(rz))
        PNG.mkdir(parents=True, exist_ok=True)
        sc.render.filepath = str(PNG / f"parting_{name}_{view}.png")
        bpy.ops.render.render(write_still=True)
        print(f"preview parting_{name}_{view}")


VIEWS = {"front": (90.0, 90.0), "side": (90.0, 0.0), "quarter": (78.0, 50.0)}
for name, (pan, nod) in {"rest": (0.0, 0.0), "pan65": (65.0, 0.0), "noddown15": (0.0, -15.0),
                         "nodup5": (0.0, 5.0), "pan65_noddown15": (65.0, -15.0)}.items():
    parting(name, pan, nod, VIEWS)
# the bib, the beard's edge and the shoulder, close up, with the head turned and nodded down
parting("closeup", 65.0, -15.0, {"quarter": (74.0, 34.0), "back": (74.0, 215.0)},
        centre=(0.0, 0.0, 352.0), span=250.0)
# and at rest, from the front-right at the beard's height: the pose the statue spends its life in
parting("closeup", 0.0, 0.0, {"rest": (88.0, 55.0)}, centre=(0.0, 0.0, 345.0), span=230.0)
# and the cutaway at rest, in the existing style: the coat halved at y = 0, the unit whole over it
parting("cutaway", 0.0, 0.0, {"side": (90.0, 0.0)}, halve_fixed=True,
        centre=(0.0, 0.0, 380.0), span=420.0)

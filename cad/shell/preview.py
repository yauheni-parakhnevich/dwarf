"""Render the gnome, each printable section, the mechanism, and a cutaway of the lot.

Blender only: `build.py preview`, or Blender -b --python preview.py. Nothing here judges
anything - the tests do that - but nothing else in the build shows what the thing looks like,
and the sculpt is the one part of this project that only an eye can check.

Everything is loaded from out/stl, which means the previews show what the slicer will be
handed: sections after their booleans, the mechanism after its placement. The cutaway is cut
with bmesh's bisect rather than a boolean, so the walls show open edges where the plane passed
- which is what a section drawing looks like anyway, and it costs nothing.
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

STL = CAD / "out" / "stl"
PNG = CAD / "out" / "preview"
SECTIONS = tuple(P.PRINTED_SECTIONS)          # the statue's sections, from params
MECH = "mechanism_assembly"
SIZE = 900
CLAY = (0.62, 0.60, 0.57)
STEEL = (0.32, 0.34, 0.38)


def _mat(name, rgb, rough=0.8):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*rgb, 1.0)
    b.inputs["Roughness"].default_value = rough
    return m


def scene():
    """A fresh scene with a sun, a fill and an orthographic camera, ready to be aimed."""
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


def load(name, mat):
    bpy.ops.wm.stl_import(filepath=str(STL / f"{name}.stl"))
    ob = bpy.context.object
    ob.data.materials.append(mat)
    ob.data.polygons.foreach_set("use_smooth", [True] * len(ob.data.polygons))
    return ob


def halve(ob, keep_plus_y=True, world=False):
    """Cut the object at y = 0 and throw one half away. No boolean: bisect and clear. With world,
    the object's own transform is applied first, so the cut is at the world's y = 0."""
    if world:
        ob.data.transform(ob.matrix_world)
        ob.matrix_world = Matrix.Identity(4)
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:], dist=0.0,
                           plane_co=(0.0, 0.0, 0.0), plane_no=(0.0, 1.0, 0.0),
                           clear_inner=keep_plus_y, clear_outer=not keep_plus_y)
    bm.to_mesh(ob.data)
    bm.free()
    return ob


def bounds(objects):
    """(centre, the largest extent) of everything passed, in world coordinates."""
    pts = [ob.matrix_world @ Vector(c) for ob in objects for c in ob.bound_box]
    lo = [min(p[i] for p in pts) for i in range(3)]
    hi = [max(p[i] for p in pts) for i in range(3)]
    return [(a + b) / 2 for a, b in zip(lo, hi)], max(b - a for a, b in zip(lo, hi))


# (tilt from straight down, turn about Z). The iso stands fifteen degrees above the horizon,
# which is about where a gnome is looked at from and low enough to see its face under the brim.
VIEWS = {"front": (90.0, 90.0), "side": (90.0, 0.0), "iso": (75.0, 45.0)}


def _offset(rx, rz):
    """Where a camera with that rotation has to stand to look at the origin."""
    a, b = math.radians(rx), math.radians(rz)
    return (math.sin(a) * math.sin(b), -math.sin(a) * math.cos(b), math.cos(a))


def shoot(sc, co, name, objects, views=VIEWS, pad=1.15):
    PNG.mkdir(parents=True, exist_ok=True)
    centre, span = bounds(objects)
    for view, (rx, rz) in views.items():
        co.data.ortho_scale = span * pad
        co.location = [c + o * 2500.0 for c, o in zip(centre, _offset(rx, rz))]
        co.rotation_euler = (math.radians(rx), 0.0, math.radians(rz))
        sc.render.filepath = str(PNG / f"{name}_{view}.png")
        bpy.ops.render.render(write_still=True)
        print(f"preview {name}_{view}")


# --- posed: the machine as it moves ------------------------------------------------------------
# How each part moves is read, not decided here: out/placements.json for the printed parts and
# out/bought.json for the bought envelopes (both written by the mech stage), as scene.py does.
import json  # noqa: E402
from mathutils import Matrix  # noqa: E402

PLACEMENTS = CAD / "out" / "placements.json"
BOUGHT = CAD / "out" / "bought.json"
PINK = (0.72, 0.42, 0.34)          # what moves: the turning unit, as in the statue's own previews
BRASS = (0.72, 0.55, 0.25)
BLUE = (0.2, 0.45, 0.85)
ORANGE = (0.85, 0.5, 0.2)
POSES = {"rest": (0.0, 0.0), "pan65": (65.0, 0.0), "nod-15": (0.0, -15.0), "pan65_nod-15": (65.0, -15.0)}
QUARTER = {"quarter": (78.0, 50.0)}


def motion(how, pan, nod):
    c = Vector((0.0, 0.0, P.Z_NOD))
    rz = Matrix.Rotation(math.radians(pan), 4, "Z")
    if how == "nods":
        return Matrix.Translation(c) @ rz @ Matrix.Rotation(math.radians(-nod), 4, "Y") @ Matrix.Translation(-c)
    if how == "pans":
        return rz
    if how == "servo_crank":
        s = Vector((P.PAN_SERVO_XY[0], P.PAN_SERVO_XY[1], 0.0))
        return Matrix.Translation(s) @ rz @ Matrix.Translation(-s)
    if how == "pan_link":
        rest, _ = P.crank_pins(0)
        pin, _ = P.crank_pins(pan)
        return Matrix.Translation((pin[0] - rest[0], pin[1] - rest[1], 0.0))
    return Matrix.Identity(4)


def load_at(path, mat, matrix):
    bpy.ops.wm.stl_import(filepath=str(path))
    ob = bpy.context.object
    ob.data.materials.append(mat)
    ob.data.polygons.foreach_set("use_smooth", [True] * len(ob.data.polygons))
    ob.matrix_world = matrix
    return ob


def machine(pan, nod, shell=True, cut=False):
    """Everything at a pose: the shell (fixed in clay, the turning unit in pink), the printed
    mechanism in steel, the bought parts in their own colours, the tube in blue. With cut, every
    object is halved at y = 0 and the +Y half kept - the section drawing."""
    clay, pink, steel = _mat("clay", CLAY), _mat("pink", PINK), _mat("steel", STEEL, rough=0.45)
    bought_mats = {"nozzle": _mat("brass", BRASS, 0.35), "nod_servo": _mat("servo", ORANGE),
                   "pan_servo": _mat("servo2", ORANGE), "fan": _mat("fan", (0.25, 0.25, 0.28))}
    obs = []
    if shell:
        for n in SECTIONS:
            moves = n in P.TURNING_SECTIONS
            obs.append(load_at(STL / f"{n}.stl", pink if moves else clay, motion("nods" if moves else "fixed", pan, nod)))
    places = json.load(open(PLACEMENTS))
    for name, info in places.items():
        if info["section"] or not (STL / f"{name}.stl").exists():
            continue
        m = motion(info.get("moves", "fixed"), pan, nod) @ Matrix(info["matrix"])
        obs.append(load_at(STL / f"{name}.stl", steel, m))
        if name == "stop_pin":
            obs.append(load_at(STL / f"{name}.stl", steel, Matrix.Scale(-1, 4, (0, 1, 0)) @ m))
    tube = f"tube_{pan:+.0f}_{nod:+.0f}"
    for name, how in json.load(open(BOUGHT)).items():
        if name.startswith("tube_"):
            if name == tube:
                obs.append(load_at(STL / "bought" / f"{name}.stl", _mat("tube", BLUE, 0.5), Matrix.Identity(4)))
            continue
        if name == "phone" and not cut:
            continue
        obs.append(load_at(STL / "bought" / f"{name}.stl", bought_mats.get(name, _mat(name, (0.5, 0.5, 0.55))),
                           motion(how, pan, nod)))
    if cut:
        obs = [halve(ob, world=True) for ob in obs]
    return obs


def posed_gnome():
    """The whole gnome, shell on, front and three-quarter, at rest, turned, nodded and both."""
    for name, (pan, nod) in POSES.items():
        sc, co = scene()
        obs = machine(pan, nod)
        frame(sc, co, f"pose_{name}", {"front": VIEWS["front"], **QUARTER},
              centre=(0.0, 0.0, P.Z_TOP / 2), span=P.Z_TOP * 1.04)


def posed_mechanism():
    """The mechanism alone, shell off, from the front, the side and three-quarter."""
    for name in ("rest", "nod-15"):
        pan, nod = POSES[name]
        sc, co = scene()
        obs = machine(pan, nod, shell=False)
        frame(sc, co, f"pose_mech_{name}", {"front": VIEWS["front"], "side": VIEWS["side"], **QUARTER},
              centre=(0.0, 0.0, 375.0), span=270.0)


def posed_cutaway():
    """Halved at y = 0: pin, stem, spider, bearing, deck, nozzle and tube in their places."""
    for name in ("rest", "nod-15"):
        pan, nod = POSES[name]
        sc, co = scene()
        machine(pan, nod, cut=True)
        frame(sc, co, f"pose_cutaway_{name}", {"side": (90.0, 0.0)}, centre=(15.0, 0.0, 395.0), span=240.0)


def frame(sc, co, name, views, centre, span):
    PNG.mkdir(parents=True, exist_ok=True)
    for view, (rx, rz) in views.items():
        co.data.ortho_scale = span
        co.location = [c + o * 2500.0 for c, o in zip(centre, _offset(rx, rz))]
        co.rotation_euler = (math.radians(rx), 0.0, math.radians(rz))
        sc.render.filepath = str(PNG / f"{name}_{view}.png")
        bpy.ops.render.render(write_still=True)
        print(f"preview {name}_{view}")


def sections():
    for n in SECTIONS:
        sc, co = scene()
        ob = load(n, _mat("clay", CLAY))
        shoot(sc, co, n, [ob], pad=1.25)


if __name__ == "__main__":
    for old in PNG.glob("*.png"):
        if not old.name.startswith("parting_"):      # the statue stage's own, kept
            old.unlink()
    posed_gnome()
    posed_mechanism()
    posed_cutaway()
    sections()

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
from mathutils import Vector

CAD = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CAD))
import params as P  # noqa: E402

STL = CAD / "out" / "stl"
PNG = CAD / "out" / "preview"
SECTIONS = tuple(P.SECTIONS_STATUE)          # the statue's sections, from params
MECH = "mechanism_assembly"
# Halved for the cutaway: the fixed shell. The bell is left whole over it, so the picture shows
# what turns and what does not as well as what is inside.
CUTAWAY = ("base_left", "base_right", "hand_left", "hand_right", "torso", "panel_left", "panel_right")
BELL = ("beard", "head", "hat")
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


def halve(ob, keep_plus_y=True):
    """Cut the object at y = 0 and throw one half away. No boolean: bisect and clear."""
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


def gnome():
    sc, co = scene()
    clay = _mat("clay", CLAY)
    obs = [load(n, clay) for n in SECTIONS]
    shoot(sc, co, "gnome", obs)


def sections():
    for n in SECTIONS:
        sc, co = scene()
        ob = load(n, _mat("clay", CLAY))
        shoot(sc, co, n, [ob], pad=1.25)


def mechanism():
    sc, co = scene()
    ob = load(MECH, _mat("steel", STEEL, rough=0.45))
    shoot(sc, co, "mechanism", [ob])


def cutaway():
    """The gnome with its right half gone, over the mechanism inside."""
    sc, co = scene()
    clay = _mat("clay", CLAY)
    steel = _mat("steel", STEEL, rough=0.45)
    obs = [halve(load(n, clay)) for n in CUTAWAY]
    obs += [load(n, clay) for n in BELL]
    obs.append(load(MECH, steel))
    shoot(sc, co, "cutaway", obs, views={"iso": VIEWS["iso"], "side": VIEWS["side"]})


if __name__ == "__main__":
    gnome()
    sections()
    mechanism()
    cutaway()

"""Wall the statue inward. Blender's Python only; `statue.py` drives it.

SOLIDIFY with offset -1 grows the wall inward from the skin, so the outside stays exactly the
statue the renders were judged on. Two thicknesses come out of it: WALL, which is the shell,
and WALL - GROW, whose inside is what `cavity_grown` is cut from - the volume an interface part
may reach into so its bosses end inside the wall instead of hovering a clearance away from it.
"""
import sys
from pathlib import Path

import bpy

CAD = Path(__file__).resolve().parents[1]
if str(CAD) not in sys.path:
    sys.path.insert(0, str(CAD))
import params as P  # noqa: E402

OUT = CAD / "out" / "statue"
GROW = 1.2


def wall(thickness, name):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.wm.stl_import(filepath=str(OUT / "outer.stl"))
    ob = bpy.context.selected_objects[0]
    s = ob.modifiers.new("solid", "SOLIDIFY")
    s.thickness = thickness
    s.offset = -1
    s.use_even_offset = True
    s.use_quality_normals = True
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.modifier_apply(modifier="solid")
    bpy.ops.object.select_all(action="DESELECT")
    ob.select_set(True)
    bpy.ops.wm.stl_export(filepath=str(OUT / f"{name}.stl"), export_selected_objects=True)
    print(f"statue {name}: wall {thickness} mm, {len(ob.data.polygons)} faces")


wall(P.WALL, "wall_full")
wall(P.WALL - GROW, "wall_thin")

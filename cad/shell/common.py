"""Blender-side helpers for the sculpted shell. Runs inside Blender's Python only.

A section is built from closed primitives, joined and voxel-remeshed into one solid — the
remesh is the only union Blender is trusted with, its exact boolean having been measured to
leave non-manifold meshes — and then walled by SOLIDIFY, which grows the wall inward from the
skin so the outside keeps the radii `params` promises the mechanism.

The order is not free. Voxel remesh turns an open sheet into a thin closed slab, and solidify
on such a slab collapses: a probe of the base's cup came back spanning z -495648 to 40820.
Solidify on the sheet itself walls it exactly and closes its free edges into a rim. So every
primitive that goes into a remesh is closed, and `cut_z` opens the section's ends after it.
"""
import math
import sys
from pathlib import Path

import bmesh
import bpy

CAD = Path(__file__).resolve().parents[1]
if str(CAD) not in sys.path:
    sys.path.insert(0, str(CAD))
import params as P  # noqa: E402

RAW = CAD / "out" / "raw"
TOL = 1e-3


def fresh_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.unit_settings.system = "METRIC"
    sc.unit_settings.scale_length = 0.001
    return sc


def _link(name, bm):
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def _ring(bm, r, z, segments, dx=0.0, swell=None):
    """One row of a revolve: a circle of verts, or a single vertex where the radius is zero."""
    if r <= 0:
        return [bm.verts.new((dx, 0.0, z))]
    out = []
    for i in range(segments):
        th = 2 * math.pi * i / segments
        rr = max(r + (swell(th, z) if swell else 0.0), 0.1)
        out.append(bm.verts.new((dx + rr * math.cos(th), rr * math.sin(th), z)))
    return out


def _bridge(bm, rows, segments):
    for a, b in zip(rows, rows[1:]):
        for i in range(segments):
            j = (i + 1) % segments
            if len(a) == 1:
                bm.faces.new((a[0], b[i], b[j]))
            elif len(b) == 1:
                bm.faces.new((a[i], b[0], a[j]))
            else:
                bm.faces.new((a[i], a[j], b[j], b[i]))


def revolve(name, profile, segments=96, lean=None, swell=None):
    """Surface of revolution of (r, z) points, no longer quite a revolution. r == 0 closes that end.

    `lean(z)` returns an X offset applied to each ring, for a hat that bends forward.
    `swell(theta, z)` returns a radius offset, in millimetres, applied to that one vertex: the
    coat's folds, the hem's scallop and a belly fuller in front than behind are all this one
    function. theta runs anticlockwise from +X, the way the gnome faces.

    A swell only bites where there are rows to carry it, so pass a profile through `sampled`
    first if the shape has to change between the profile's own points.

    Open ends (r > 0 at either extreme) stay open; solidify closes them into a rim.
    """
    bm = bmesh.new()
    rows = [_ring(bm, r, z, segments, lean(z) if lean else 0.0, swell) for r, z in profile]
    _bridge(bm, rows, segments)
    return _link(name, bm)


def sampled(profile, step=3.0):
    """The profile with rows inserted so no two are more than `step` apart.

    Points that share a z (the profile's own steps) stay as they are: a step must keep its
    two rows, or it stops being a step.
    """
    out = []
    for (r0, z0), (r1, z1) in zip(profile, profile[1:]):
        out.append((r0, z0))
        n = int(abs(z1 - z0) / step)
        out += [(r0 + (r1 - r0) * i / n, z0 + (z1 - z0) * i / n) for i in range(1, n)]
    out.append(profile[-1])
    return out


def sphere(name, r, loc, segments=48):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=r, location=loc, segments=segments, ring_count=segments // 2)
    ob = bpy.context.object
    ob.name = name
    return ob


def ellipsoid(name, radii, loc, rot=(0, 0, 0)):
    ob = sphere(name, 1.0, loc)
    ob.scale = radii
    ob.rotation_euler = tuple(math.radians(a) for a in rot)
    return ob


def subdivide(ob, levels=2):
    m = ob.modifiers.new("sub", "SUBSURF")
    m.levels = m.render_levels = levels
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.modifier_apply(modifier=m.name)


def join_remesh(name, objects, voxel=1.0, relax=2):
    """Join many closed meshes into one watertight solid.

    `relax` runs that many smoothing passes over the remeshed skin. Voxel remesh leaves the
    creases where two primitives meet at about the voxel's radius, and a crease tighter than
    the wall makes solidify fold its inner surface back through itself; a pass or two opens
    them up. It costs about a tenth of a millimetre off the widest radii.
    """
    bpy.ops.object.select_all(action="DESELECT")
    for o in objects:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]
    bpy.ops.object.transform_apply(scale=True, rotation=True, location=False)
    bpy.ops.object.join()
    ob = bpy.context.object
    ob.name = name
    ob.data.remesh_voxel_size = voxel
    ob.data.remesh_voxel_adaptivity = 0.0
    bpy.ops.object.voxel_remesh()
    if relax:
        m = ob.modifiers.new("relax", "SMOOTH")
        m.factor = 0.5
        m.iterations = relax
        bpy.ops.object.modifier_apply(modifier=m.name)
    return ob


def _orient_outward(bm):
    """Make every normal agree, then make them all face away from the axis."""
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    f = max(bm.faces, key=lambda f: f.calc_center_median().xy.length)
    if f.normal.xy.dot(f.calc_center_median().xy) < 0:
        bmesh.ops.reverse_faces(bm, faces=bm.faces)


def cut_z(ob, z0=None, z1=None):
    """Slice the solid open at the section's planes and throw away what is outside them.

    What is left is a sheet with a free edge at each plane, which is what solidify wants: it
    walls the sheet and closes those edges into a flat rim exactly on the plane.
    """
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    for z, below in ((z0, True), (z1, False)):
        if z is None:
            continue
        bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:], dist=0.0,
                               plane_co=(0.0, 0.0, z), plane_no=(0.0, 0.0, 1.0),
                               clear_inner=below, clear_outer=not below)
    bm.to_mesh(ob.data)
    bm.free()
    return ob


def add_floor(ob, r, z, segments=96):
    """Weld a raised floor into a section that has been cut open at the bottom.

    The floor is a disc at `z` of radius `r` on a skirt that drops to the cut plane; the ring
    left between that skirt and the section's own outline there is filled in the plane, so the
    whole thing stays one sheet with one free edge — the top rim — for solidify to wall. The
    space under the floor is left open to the ground, which is where the stakes and the drain
    arches go.

    The skirt stands two walls inside the floor's rim. Sheets that run closer than that grow
    into each other when they are walled: with the skirt directly under the rim the trench
    between it and the outer wall came out solid and self-intersecting, and rays through it
    read anything from zero to the whole diameter.
    """
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    z_cut = min(v.co.z for v in bm.verts)
    r_skirt = r - 2 * P.WALL
    _bridge(bm, [_ring(bm, 0.0, z, segments), _ring(bm, r, z, segments),
                 _ring(bm, r_skirt, z - 2 * P.WALL, segments), _ring(bm, r_skirt, z_cut, segments)], segments)
    rim = [e for e in bm.edges if len(e.link_faces) == 1 and all(abs(v.co.z - z_cut) < TOL for v in e.verts)]
    bmesh.ops.triangle_fill(bm, use_beauty=True, use_dissolve=False, edges=rim, normal=(0.0, 0.0, 1.0))
    _orient_outward(bm)
    bm.to_mesh(ob.data)
    bm.free()
    return ob


def finish(ob, displace=0.0, noise_scale=6.0, solidify=True, wall=P.WALL):
    """Outward-only texture, then a wall of constant thickness grown inward."""
    if displace > 0:
        tex = bpy.data.textures.new(ob.name + "_tex", "CLOUDS")
        tex.noise_scale = noise_scale
        d = ob.modifiers.new("disp", "DISPLACE")
        d.texture = tex
        d.strength = displace
        d.mid_level = 0.0
        d.direction = "NORMAL"
    if solidify:
        s = ob.modifiers.new("solid", "SOLIDIFY")
        s.thickness = wall
        s.offset = -1
        s.use_even_offset = True
    bpy.context.view_layer.objects.active = ob
    for mod in list(ob.modifiers):
        bpy.ops.object.modifier_apply(modifier=mod.name)
    return ob


def skin_point(profile, z, y, sink=0.0):
    """A point on the skin at height z and offset y, pushed `sink` in along the radius.

    Somewhere to hang a button or a buckle from without guessing at the barrel's radius.
    """
    r = P.shell_r(profile, z) - sink
    return (math.sqrt(max(r * r - y * y, 1.0)), y, z)


def export_raw(ob, name):
    RAW.mkdir(parents=True, exist_ok=True)
    bpy.ops.object.select_all(action="DESELECT")
    ob.select_set(True)
    bpy.ops.wm.stl_export(filepath=str(RAW / f"{name}.stl"), export_selected_objects=True)
    print(f"raw   {name}: {len(ob.data.polygons)} faces")

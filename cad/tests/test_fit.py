"""Every placed part against the statue's own cavity.

The reach table in the fit report is four numbers a slab and no azimuth profile below the belt,
so it can only ever be a pre-check. The arbiter is the mesh the statue stage writes to
out/statue/cavity.stl; until that exists this file skips, and the pre-check is all there is.
"""
import json
import math
from pathlib import Path
import pytest
import params as P

OUT = Path(__file__).resolve().parents[1] / "out" / "statue"
CAVITY = OUT / "cavity.stl"
FEATURES = OUT / "features.json"

pytestmark = pytest.mark.skipif(not CAVITY.exists(),
                                reason="the statue stage has not written out/statue/cavity.stl yet")

# T8 from the fit report at H = 700: mech z -> (front +X, back -X, left +Y, right -Y)
REACH = {150: (54, 93, 118, 102), 180: (103, 95, 115, 115), 212: (99, 83, 124, 124),
         230: (99, 78, 133, 129), 250: (96, 77, 133, 129), 265: (98, 76, 129, 126),
         300: (86, 72, 115, 109), 340: (95, 74, 107, 98), 368: (100, 74, 103, 86),
         392: (92, 81, 114, 95), 400: (85, 79, 114, 95), 411: (72, 76, 106, 93)}
def blanks():
    """Every interface part, plus the floor plate: all are cut to the cavity by the assembler."""
    from mech import INTERFACES
    return {n for names in INTERFACES.values() for n in names} | {"floor_plate"}


def legs():
    """The measured leg centres if the statue stage wrote them, else the parameters' estimate."""
    from mech.torso import measured_legs
    return measured_legs()


def _reach_at(z):
    """The four cardinal reaches interpolated to z, or None outside the table."""
    zs = sorted(REACH)
    if z < zs[0] or z > zs[-1]:
        return None
    for a, b in zip(zs, zs[1:]):
        if a <= z <= b:
            t = 0.0 if b == a else (z - a) / (b - a)
            return tuple(REACH[a][i] + t * (REACH[b][i] - REACH[a][i]) for i in range(4))
    return None


def _outside_reach(v):
    """True when a point is outside the slab ellipse the reach table implies."""
    r = _reach_at(v[2])
    if r is None:
        return False
    front, back, left, right = r
    a = front if v[0] >= 0 else back
    b = left if v[1] >= 0 else right
    return (v[0] / a) ** 2 + (v[1] / b) ** 2 > 1.0


def _cavity():
    import trimesh
    return trimesh.load_mesh(str(CAVITY))


def test_every_placed_part_is_inside_the_cavity(placed):
    """The mesh is the arbiter; the reach table only says where to look first."""
    mesh = _cavity()
    for name, p in sorted(placed.items()):
        if name in blanks():
            continue
        pts = [(v.X, v.Y, v.Z) for v in p.vertices()]
        if not pts:
            continue
        outside = [q for q in pts if not mesh.contains([q])[0]]
        assert not outside, (name, len(outside), outside[:3])


def test_the_bought_parts_are_inside_the_cavity():
    from mech.base import bottle_body
    from mech.common import box
    mesh = _cavity()
    lg = legs()
    L, W, H = P.PUMP
    px, py = lg["left"]
    pump = box(px - L / 2, px + L / 2, py - W / 2, py + W / 2, P.PUMP_Z0, P.PUMP_Z0 + H)
    L, W, H = P.VALVE
    vx, vy = lg["right"]
    valve = box(vx - L / 2, vx + L / 2, vy - W / 2, vy + W / 2, P.VALVE_Z0, P.VALVE_Z0 + H)
    for name, body in (("bottle", bottle_body()), ("pump", pump), ("valve", valve)):
        pts = [(v.X, v.Y, v.Z) for v in body.vertices()]
        outside = [q for q in pts if not mesh.contains([q])[0]]
        assert not outside, (name, outside)


def test_the_reach_table_agrees_with_the_mesh(placed):
    """Anything the table calls outside had better be outside the mesh too, or the table lies."""
    mesh = _cavity()
    for name, p in sorted(placed.items()):
        if name in blanks():
            continue
        for v in p.vertices():
            q = (v.X, v.Y, v.Z)
            if _outside_reach(q):
                assert not mesh.contains([q])[0], (name, q)


def test_the_legs_are_where_the_brackets_expect(placed):
    """Whatever the statue measured, both brackets still stand inside their leg."""
    lg = legs()
    r = lg.get("r", P.LEG_R)
    for name, key in (("pump_bracket", "left"), ("valve_bracket", "right")):
        cx, cy = lg[key]
        bb = placed[name].bounding_box()
        corner = max(math.hypot(x - cx, y - cy)
                     for x in (bb.min.X, bb.max.X) for y in (bb.min.Y, bb.max.Y))
        assert corner <= r - 2.0, (name, corner, r)

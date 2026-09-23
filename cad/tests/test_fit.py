"""Every placed part against the statue's own cavity.

The mesh the statue stage writes to out/statue/cavity.stl is the arbiter, and until it exists
this file skips - there is nothing else worth asserting against. The fit report's reach table
used to stand in for it here and has been taken out: it is four numbers a slab, interpolated
from a different height, and it models an elliptical section the coat does not have. It called
the bottle cradle's corner at (-48.5, -97.5, 156) outside when the mesh has it comfortably in,
so it was rejecting good geometry rather than catching bad.
"""
import math
from pathlib import Path
import pytest
import params as P

OUT = Path(__file__).resolve().parents[1] / "out" / "statue"
CAVITY = OUT / "cavity.stl"
FEATURES = OUT / "features.json"

pytestmark = pytest.mark.skipif(not CAVITY.exists(),
                                reason="the statue stage has not written out/statue/cavity.stl yet")


def blanks():
    """Every interface part, plus the floor plate: all are cut to the cavity by the assembler.

    The nozzle arm is here for a different reason: its tip is meant to leave the cavity. It
    exits through the mouth, which the assembler cuts, and through the beard's parting.
    test_mech's test_the_nozzle_arm_leaves_only_through_the_mouth holds it to that.
    """
    from mech import INTERFACES
    return {n for names in INTERFACES.values() for n in names} | {"floor_plate", "nozzle_arm"}


def legs():
    """The measured leg centres if the statue stage wrote them, else the parameters' estimate."""
    from mech.torso import measured_legs
    return measured_legs()


def _cavity():
    import trimesh
    return trimesh.load_mesh(str(CAVITY))


def test_every_placed_part_is_inside_the_cavity(placed):
    """The mesh is the arbiter, vertex by vertex."""
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
    from mech.base import bottle_envelope
    from mech.common import box
    mesh = _cavity()
    lg = legs()
    L, W, H = P.PUMP
    px, py = lg["left"]
    pump = box(px - L / 2, px + L / 2, py - W / 2, py + W / 2, P.PUMP_Z0, P.PUMP_Z0 + H)
    L, W, H = P.VALVE
    vx, vy = lg["right"]
    valve = box(vx - L / 2, vx + L / 2, vy - W / 2, vy + W / 2, P.VALVE_Z0, P.VALVE_Z0 + H)
    for name, body in (("bottle", bottle_envelope()), ("pump", pump), ("valve", valve)):
        pts = [(v.X, v.Y, v.Z) for v in body.vertices()]
        outside = [q for q in pts if not mesh.contains([q])[0]]
        assert not outside, (name, outside)


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

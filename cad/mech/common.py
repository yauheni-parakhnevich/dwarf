import math
from pathlib import Path
from build123d import (Axis, Box, Compound, Cylinder, Location, Plane, Polygon, Pos, Rot, Part,
                       export_step, export_stl, mirror, revolve)
import params as P

OUT = Path(__file__).resolve().parents[1] / "out"
STEP = OUT / "step"
STL = OUT / "stl"


def export(part: Part, name: str) -> None:
    STEP.mkdir(parents=True, exist_ok=True)
    STL.mkdir(parents=True, exist_ok=True)
    if not export_step(part, str(STEP / f"{name}.step")):
        raise RuntimeError(f"STEP export failed: {name}")
    # 0.05 mm chordal tolerance: coarser than build123d's default, fine for a 0.6 mm nozzle
    if not export_stl(part, str(STL / f"{name}.stl"), tolerance=0.05, angular_tolerance=0.1):
        raise RuntimeError(f"STL export failed: {name}")


def polar(r, deg):
    """(x, y) at radius r, `deg` round from +X."""
    return r * math.cos(math.radians(deg)), r * math.sin(math.radians(deg))


def skin_solid(profile, inset=0.0):
    """The solid of revolution `inset` millimetres inside a shell profile's skin.

    Inset 0 is the skin itself; WALL - 1.2 is the surface ring_r_out puts an interface part on,
    so a part clipped to it is embedded 1.2 mm into the wall and never stands proud; WALL is the
    wall's inner face; WALL + 1 the cavity with a millimetre to spare.
    """
    pts = [(P.shell_r(profile, z) - inset, z) for _, z in profile]
    z0, z1 = profile[0][1], profile[-1][1]
    return revolve(Plane.XZ * Polygon((0.0, z0), *pts, (0.0, z1)), axis=Axis.Z)


def cyl_z(r, z0, z1, x=0.0, y=0.0):
    """A cylinder along Z from z0 to z1."""
    return Pos(x, y, (z0 + z1) / 2) * Cylinder(r, z1 - z0)


def cyl_y(r, y0, y1, x=0.0, z=0.0):
    return Pos(x, (y0 + y1) / 2, z) * Rot(90, 0, 0) * Cylinder(r, y1 - y0)


def cyl_x(r, x0, x1, y=0.0, z=0.0):
    return Pos((x0 + x1) / 2, y, z) * Rot(0, 90, 0) * Cylinder(r, x1 - x0)


def box(x0, x1, y0, y1, z0, z1):
    return Pos((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2) * Box(x1 - x0, y1 - y0, z1 - z0)


def servo_body(spec, shaft_xyz, axis="z"):
    """A servo as a solid, for clearance checks and cutters.

    `shaft_xyz` is where the output shaft leaves the body and `axis` is the shaft direction.
    Only the orientations this design uses exist:
    "-z": shaft down, body above the shaft face, length running +X from the shaft end (pan);
    "y":  shaft along +Y, body behind the shaft face, length running +Z from the shaft end (tilt,
          TILT_SERVO_UP) so the tabs sit where the sphere is wide.
    """
    L, W, H = spec["body"]
    off = spec["shaft_off"]
    sx, sy, sz = shaft_xyz
    if axis == "-z":
        return box(sx - off, sx + (L - off), sy - W / 2, sy + W / 2, sz, sz + H)
    if axis == "y":
        return box(sx - W / 2, sx + W / 2, sy - H, sy, sz - off, sz + (L - off))
    raise ValueError(axis)


def phone_body():
    """The iPhone standing upright, camera end down, screen facing -X, centred; its camera is at CAM_Y."""
    return box(P.PHONE_FRONT_X, P.PHONE_BACK_X,
               P.PHONE_Y_OFFSET - P.PHONE_W / 2, P.PHONE_Y_OFFSET + P.PHONE_W / 2,
               P.PHONE_BOTTOM_Z, P.PHONE_BOTTOM_Z + P.PHONE_L)


def canister_body():
    L, W, H = P.CANISTER
    cx, cy = P.CANISTER_XY
    return box(cx - L / 2, cx + L / 2, cy - W / 2, cy + W / 2, P.CANISTER_Z0, P.CANISTER_Z0 + H)


def pump_body():
    L, W, H = P.PUMP
    cx, cy = P.PUMP_XY
    return box(cx - L / 2, cx + L / 2, cy - W / 2, cy + W / 2, P.PUMP_Z0, P.PUMP_Z0 + H)


def valve_body():
    """Beside the pump on the pump mount's plate, at the back of the base."""
    L, W, H = P.VALVE
    cx, cy = P.VALVE_XY
    return box(cx - L / 2, cx + L / 2, cy - W / 2, cy + W / 2, P.PUMP_Z0, P.PUMP_Z0 + H)


def insert_holes(part, points, depth=P.INSERT_DEPTH, r=P.INSERT_D / 2, direction="down"):
    """Blind holes for heat-set inserts, drilled from each (x, y, z) point."""
    for x, y, z in points:
        if direction == "down":
            part = part - cyl_z(r, z - depth, z + 0.01, x, y)
        elif direction == "up":
            part = part - cyl_z(r, z - 0.01, z + depth, x, y)
        else:
            raise ValueError(direction)
    return part


def _placed(name, p):
    """Every copy of a part in the assembly, as (label, solid).

    All but two are modelled where they sit. The hard-stop pin is printed once and fitted
    twice, and the filler cap's neck belongs to the base's shell, which this compound does
    not contain, so the cap is carried out to where that neck comes through the back.
    """
    if name == "stop_pin":
        return [(name, Location() * p), (name + "_mirrored", mirror(p, about=Plane.XZ))]
    if name == "filler_cap":
        skin = P.shell_r(P.BASE_PROFILE, P.Z_FILLER)
        return [(name, Pos(-(skin + p.bounding_box().max.X), 0.0, P.Z_FILLER) * p)]
    return [(name, Location() * p)]


def assembly(parts: dict) -> Compound:
    """Every part at its assembled position, each child carrying its name."""
    children = []
    for name, p in parts.items():
        for label, child in _placed(name, p):
            child.label = label
            children.append(child)
    return Compound(children=children)

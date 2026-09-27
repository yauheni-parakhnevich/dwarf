import json
import math
from pathlib import Path
from build123d import (Axis, Box, Compound, Cylinder, Location, Plane, Polygon, Pos, Rot, Part,
                       Sphere, export_step, export_stl, extrude, mirror, revolve)
import params as P
from mech import ALL

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


def rod(a, b, r):
    """A cylinder of radius r from point a to point b."""
    d = math.dist(a, b)
    mid = tuple((ai + bi) / 2 for ai, bi in zip(a, b))
    return Plane(origin=mid, z_dir=tuple(bi - ai for ai, bi in zip(a, b))) * Pos(0, 0, -d / 2) * cyl_z(r, 0, d)


def polyline(points, r):
    """A chain of rods through `points`, with a ball at every inner joint so the bends are round."""
    out = None
    for i, (a, b) in enumerate(zip(points, points[1:])):
        if math.dist(a, b) < 1e-9:
            continue
        seg = rod(a, b, r)
        if i:
            seg = seg + Pos(*a) * Sphere(r)
        out = seg if out is None else out + seg
    return out


def ball(r):
    """A sphere of radius r about C = (0, 0, Z_NOD), the centre the head pans and nods about."""
    return Pos(0, 0, P.Z_NOD) * Sphere(r)


NOD_AXIS = Axis((0.0, 0.0, P.Z_NOD), (0.0, 1.0, 0.0))


def posed(part, pan=0.0, nod=0.0, nods=True):
    """A part carried to a pose: nodded about Y through C, then panned about Z.

    `nod` is the firmware's sign, nose up positive. build123d turns +deg about +Y nose down, so the
    rotation is -nod. A part that pans only is given nods=False.
    """
    if nods and nod:
        part = part.rotate(NOD_AXIS, -nod)
    return part.rotate(Axis.Z, pan) if pan else part


def pose_point(p, pan=0.0, nod=0.0, nods=True):
    """A point carried the way posed() carries a part."""
    x, y, z = p[0], p[1], p[2] - P.Z_NOD
    if nods and nod:
        a = math.radians(-nod)
        x, z = x * math.cos(a) + z * math.sin(a), -x * math.sin(a) + z * math.cos(a)
    if pan:
        b = math.radians(pan)
        x, y = x * math.cos(b) - y * math.sin(b), x * math.sin(b) + y * math.cos(b)
    return (x, y, z + P.Z_NOD)


def features():
    """out/statue/features.json, or None before the statue stage has run."""
    try:
        return json.loads((OUT / "statue" / "features.json").read_text())
    except (OSError, ValueError):
        return None


def inner_table(name):
    """The statue's published first-crossing table for `name` ("collar" or "torso"): a dict of
    z -> radii every step_deg, with the misses (0) left out, or None if it has not been written."""
    f = features()
    if not f or f"{name}_inner" not in f:
        return None
    t = f[f"{name}_inner"]
    return {float(z): row for z, row in t["rows"].items()}, float(t["step_deg"])


def servo_body(spec, shaft_xyz, axis="z", up=True):
    """A servo as a solid, for clearance checks and cutters.

    `shaft_xyz` is where the output shaft leaves the body and `axis` is the shaft direction.
    Only the orientations this design uses exist:
    "-z": shaft down, body above the shaft face, length running +X from the shaft end (pan);
    "y":  shaft along +Y, body behind the shaft face, length running +Z from the shaft end;
    "-y": shaft along -Y, body out to +Y from the shaft face, length running +Z from the shaft end:
          the nod servo.
    """
    L, W, H = spec["body"]
    off = spec["shaft_off"]
    sx, sy, sz = shaft_xyz
    if axis == "-z":
        return box(sx - off, sx + (L - off), sy - W / 2, sy + W / 2, sz, sz + H)
    if axis == "y":
        if up:
            return box(sx - W / 2, sx + W / 2, sy - H, sy, sz - off, sz + (L - off))
        return box(sx - W / 2, sx + W / 2, sy - H, sy, sz - (L - off), sz + off)
    if axis == "-y":
        return box(sx - W / 2, sx + W / 2, sy, sy + H, sz - off, sz + (L - off))
    raise ValueError(axis)


def phone_body():
    """The iPhone standing upright, camera end down, screen facing -X, centred; its camera is at CAM_Y."""
    return box(P.PHONE_FRONT_X, P.PHONE_BACK_X,
               P.PHONE_Y_OFFSET - P.PHONE_W / 2, P.PHONE_Y_OFFSET + P.PHONE_W / 2,
               P.PHONE_BOTTOM_Z, P.PHONE_BOTTOM_Z + P.PHONE_L)


# --- the filler hose's two barbs, one on the tank head and one under the divider's neck --------
BARB_R = P.HOSE_BARB_D / 2                 # the shank the hose stretches over
BARB_BORE_R = (P.HOSE_BARB_D - 2.0) / 2    # ... bored to leave a millimetre of wall all round
BARB_RING = 1.5                            # how wide each of the two ridges is


def barb_rings():
    """How far back from a barb's mouth each of its two ridges starts.

    One at the mouth, where the hose's end pulls back against it, and one half the grip in.
    Both are HOSE_BARB_LIP proud, which is what the hose has to be stretched over and what the
    divider's hole has to pass.
    """
    return (1.0, 1.0 + P.HOSE_BARB_L / 2)


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


def pose_transform(name, pan=0.0, nod=0.0):
    """How a part in its assembled place moves to a pose, as a function of a part: the one place
    the groups in mech/__init__.py are turned into motion."""
    from mech import LINKAGE, NODS, PANS, SHELL_NODS
    if name in NODS or name in SHELL_NODS:
        return lambda p: posed(p, pan, nod)
    if name in PANS:
        return lambda p: posed(p, pan, nods=False)
    if name in LINKAGE:
        rest, _ = P.crank_pins(0)
        pin, _ = P.crank_pins(pan)
        if name == "servo_crank":
            ax = Axis((P.PAN_SERVO_XY[0], P.PAN_SERVO_XY[1], 0), (0, 0, 1))
            return lambda p: p.rotate(ax, pan) if pan else p
        return lambda p: p.moved(Location((pin[0] - rest[0], pin[1] - rest[1], 0)))
    return lambda p: p


def assembly(parts: dict, pan=0.0, nod=0.0) -> Compound:
    """Every part carried from its print frame to where it sits, and on to a pose (pan, nod),
    each child carrying its name.

    The stop pin is the one thing this still knows by name: it is printed once and fitted
    twice, and a mirror is not a Location, so it cannot be declared as a placement.
    """
    at = {spec.name: spec.placement for spec in ALL}
    children = []
    for name, p in parts.items():
        child = pose_transform(name, pan, nod)(at.get(name, Location()) * p)
        child.label = name
        children.append(child)
        if name == "stop_pin":
            twin = mirror(child, about=Plane.XZ)
            twin.label = name + "_mirrored"
            children.append(twin)
    return Compound(children=children)

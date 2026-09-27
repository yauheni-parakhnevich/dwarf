"""The order the gnome goes together in, swept: every step is the real parts moved along the real
path, 2 mm at a time, against everything already there - 0 mm3 at every step.

In the statue, after the base and the belt (the ring with its sleeves, the four belt screws):

  1. the chassis with the cage bolted to it on the bench, down through the ring's top;
  2. the electronics deck, boards and all, down onto its standoffs;
  3. the phone's sled with the phone in it (its lens clip goes on through the window: see below);
  4. the deck sub-assembly from the bench - deck, bearing and cap, the plate with its hub ring,
     the stem with its pin and lug, the nod servo, the pan servo and the fan - onto the cage;
     the crank and the link go on from below after it, between the legs, as before;
  5. the collar, over all of it, onto the ring's spigot, and its four screws;
  6. the spider, onto the stem's head, its two screws from above;
  7. the beard's two halves, each from its own side along FIT_DIR - the glued unit has no
     straight way on at all (params' FITTING_SPLIT) - and then the head with the hat glued to it
     straight down over the spider, its socket sliding onto the tube's stab, and its four screws
     from outside.

Service is the same paths backwards, so these are its proof as well: the phone comes out after
the unit, the spider, the collar and the deck sub-assembly.

On the bench the deck sub-assembly goes together in an order of its own, and its screws are
test_mech's (bench_screws): the plate drops through the bearing, and so on.
"""
import math

import numpy as np
import pytest
import trimesh

import params as P
import machine as M

pytestmark = pytest.mark.skipif(not (M.built() and M.shell_built()),
                                reason="run `build.py` (mech, statue, assemble) first")

STEP = 2.0
UNIT = P.TURNING_SECTIONS


def fit_dir(side):
    """The way a beard half goes on, as the unit vector it comes in against (it moves along -u)."""
    th, az = math.radians(P.FIT_DIR[0]), math.radians(P.FIT_DIR[1] * side)
    return np.array([math.sin(th) * math.cos(az), math.sin(th) * math.sin(az), math.cos(th)])


@pytest.fixture(scope="session")
def world():
    """Everything, at rest, by name: printed parts, bought envelopes, shell sections."""
    iface = M.interfaces()
    out = {n: m for n, m in M.mech_meshes().items() if n not in iface}
    out.update({n: m for n, (m, _) in M.bought().items()})
    out.update(M.sections())
    out["tube"] = M.tube(0.0, 0.0)
    out["filler_cap"] = M.mech_meshes()["filler_cap"]
    from mech.common import box
    out["lens_clip"] = M.to_mesh(lens_clip(), "clip")
    return out


def lens_clip():
    """The clip-on lens as it sits on the phone: a barrel LENS_CLIP_W across and LENS_CLIP_T deep on
    the camera, and a clamp 10 mm wide from it round the phone's +Y edge."""
    from mech.common import box, cyl_x
    barrel = cyl_x(P.LENS_CLIP_W / 2, P.PHONE_BACK_X, P.LENS_FRONT_X, P.CAM_Y, P.Z_LENS)
    edge = P.PHONE_Y_OFFSET + P.PHONE_W / 2 + 3.0
    clamp = box(P.PHONE_BACK_X, P.LENS_FRONT_X, P.CAM_Y, edge, P.Z_LENS - 5.0, P.Z_LENS + 5.0)
    return barrel + clamp


def boards(world):
    return M.union([world["electronics_deck"], world["boards"]])


STEPS = {
    "chassis and cage": (("chassis", "deck_ring"), 130.0),
    "electronics deck": (("electronics_deck", "boards"), 120.0),
    "phone sled": (("phone_sled", "phone", "lens_clip"), 150.0),
    "deck sub-assembly": (("deck", "bearing", "bearing_cap", "plate", "hub_ring", "stem", "pin",
                           "bushing", "stop_lug", "horn", "nod_servo", "pan_servo", "fan"), 150.0),
    "collar": (("collar",), 260.0),
    "spider": (("spider",), 60.0),
    "left half of the beard": (("beard_left",), 200.0),
    "right half of the beard": (("beard_right",), 200.0),
    "head and hat": (("head", "hat", "nozzle"), 300.0),
}
# The pairs that sit on each other at home: the collar's bottom edge on the ring's top at z 307 (they
# are cut from one shell along that plane), and the head's bottom edge on the beard's top at z 412.
HOME_CONTACTS = {frozenset(p) for p in (("collar", "torso"), ("head", "beard_left"), ("head", "beard_right"))}
WAY = {"left half of the beard": fit_dir(1.0), "right half of the beard": fit_dir(-1.0)}
# The phone goes in with its lens clipped on, and the clip reaches 89.8 out where the ring's top edge
# is 84-87: so the sled comes down 6 mm behind its place - all the room there is while its lugs
# pass the boards' front edge - and the last 20 mm in its place, straight down onto its lugs.
SLED_PATH = [(-6.0, 150.0), (-6.0, 20.0), (0.0, 20.0), (0.0, 0.0)]
PATHS = {"phone sled": [(x, 0.0, z) for x, z in SLED_PATH]}


def path_points(step, rise):
    """The offsets a step's parts pass through, 2 mm apart, ending at home."""
    way = WAY.get(step, np.array([0.0, 0.0, 1.0]))
    corners = [np.array(c, float) for c in PATHS.get(step, [way * rise, (0.0, 0.0, 0.0)])]
    out = []
    for a, b in zip(corners, corners[1:]):
        n = max(1, int(np.ceil(np.linalg.norm(b - a) / STEP)))
        out += [a + (b - a) * i / n for i in range(n)]
    return out + [corners[-1]]
BEFORE = ("base_left", "base_right", "hand_left", "hand_right", "torso", "panel_left", "panel_right",
          "divider", "filler_neck", "filler_cap")
AFTER_DECK = ("servo_crank", "pan_link", "stop_pin", "stop_pin_mirrored", "tube")


def already(order_index, world):
    """What is in the statue when step `order_index` begins."""
    names = list(BEFORE)
    keys = list(STEPS)
    for k in keys[:order_index]:
        names += list(STEPS[k][0])
        if k == "deck sub-assembly":
            names += list(AFTER_DECK)
    return {n: world[n] for n in names if n in world}


@pytest.mark.parametrize("step", list(STEPS))
def test_each_step_goes_on_along_its_path(world, step):
    """The step's parts, brought `rise` along their way (straight down, but for the beard's halves)
    to home, 2 mm at a time, touch nothing that is already in. The one contact allowed is the one
    the step ends on: a part landing on its seat touches it, and a boolean of two coincident faces
    leaves a sliver."""
    names, rise = STEPS[step]
    index = list(STEPS).index(step)
    moving = M.manifold(M.union([world[n] for n in names if n in world]))
    there = M.manifold(M.union(list(already(index, world).values())))
    worst = (0.0, None)
    for off in path_points(step, rise):
        v = M.mvolume(moving.translate(tuple(float(c) for c in off)), there)
        if np.linalg.norm(off) < 1e-9:
            continue       # home is checked pair by pair below, against the declared contacts
        if v > worst[0]:
            worst = (v, tuple(round(float(c), 1) for c in off))
    assert worst[0] <= 0.05, f"{step}: {worst[0]:.2f} mm3 in the way at {worst[1]}"
    # at home, only the pairs that are made to sit on each other may touch, and only as two
    # faces that meet - a boolean of coincident faces leaves a sliver of a few mm3 at most
    there_parts = already(index, world)
    for n in names:
        if n not in world:
            continue
        mine = M.manifold(world[n])
        for k, m in there_parts.items():
            v = M.mvolume(mine, M.manifold(m))
            if frozenset((n, k)) in HOME_CONTACTS:
                assert v <= 3.0, (step, n, k, v)
            else:
                assert v <= 0.05, f"{step}: {n} is in {k} by {v:.3f} mm3 at home"


def test_the_glued_unit_has_no_way_on_and_its_pieces_have(world):
    """Why the beard is printed in halves. Every point of the unit within 1.5 mm of the sphere it
    keeps from C, as a direction from C: for a straight path u to take a piece off the collar, all
    of its directions have to lie on u's side, (d . u) > 0. For the glued unit no u does that -
    the best of 2 000 is under zero; for the head and hat together, u = +Z does; for each half of
    the beard, its FIT_DIR does."""
    c = np.array([0.0, 0.0, P.Z_NOD])

    def dirs(names):
        v = np.vstack([world[n].vertices for n in names])
        d = np.linalg.norm(v - c, axis=1)
        k = v[d < P.NECK_SPHERE_R + 1.5] - c
        return k / np.linalg.norm(k, axis=1)[:, None]
    th, ph = np.meshgrid(np.radians(np.arange(0, 181, 4)), np.radians(np.arange(0, 360, 4)))
    us = np.stack([np.sin(th) * np.cos(ph), np.sin(th) * np.sin(ph), np.cos(th)], -1).reshape(-1, 3)
    best = max((dirs(UNIT) @ us.T).min(axis=0))
    assert best < 0.0, best
    assert (dirs(("head", "hat")) @ np.array([0.0, 0.0, 1.0])).min() > 0.3
    for name, side in (("beard_left", 1.0), ("beard_right", -1.0)):
        assert (dirs((name,)) @ fit_dir(side)).min() > 0.15, name


def test_the_ring_passes_the_chassis_it_would_not_have(world):
    """What the chassis's new size is for: the old 70 x 100 one does not go down through the
    ring's top, the seam chamfer at 82 out at the sides; this one does (the sweep above)."""
    from mech.common import box, cyl_z
    torso = world["torso"]
    z = 300.0
    for y in (P.CHASSIS_RY + 1.0, 100.0):
        probe = M.to_mesh(cyl_z(0.5, z, z + 6.0, 0.0, y), f"probe_{y:.0f}")
        hit = M.overlap(probe, torso)
        if y > 90:
            assert hit > 0, "the ring's top no longer stops a 100 mm chassis: the chassis could be wider"
        else:
            assert hit == 0, f"the ring's top reaches in to {y} at the side"


def test_the_lens_clip_needs_the_dogleg(world):
    """Why the phone's path is a dog-leg: straight down, the clip on the phone meets the ring's top;
    along SLED_DOGLEG it meets nothing (the sweep above)."""
    clip = M.manifold(world["lens_clip"])
    torso = M.manifold(world["torso"])
    worst = max(M.mvolume(clip.translate((0.0, 0.0, float(dz))), torso) for dz in np.arange(150.0, 0.0, -STEP))
    assert worst > 1.0, worst
    corner = math.hypot(P.LENS_FRONT_X, P.CAM_Y + P.LENS_CLIP_W / 2)
    assert corner > 88.0, corner
    moved = math.hypot(P.LENS_FRONT_X + SLED_PATH[0][0], P.CAM_Y + P.LENS_CLIP_W / 2)
    assert moved < 87.0, moved


def test_the_collar_joint(world):
    """The collar's four tabs go SPIGOT_H down into the ring; each screw is under the turning unit
    at rest - straight up from its head is the unit - and a driver reaches it straight in under the
    unit's rim at rest: 40 mm of it out from the ring's skin touches nothing."""
    from mech.collar import screw_head
    from test_mech import _driver
    import assemble as A
    collar, torso = world["collar"], world["torso"]
    assert (P.Z_TURN - P.TURN_GAP) - collar.bounds[0][2] >= 8.0, collar.bounds[0][2]
    unit = M.union([world[n] for n in UNIT])
    others = M.union([unit] + [world[n] for n in ("panel_left", "panel_right", "hand_left", "hand_right",
                                                  "base_left", "base_right")])
    for a in P.COLLAR_SCREW_ANGLES:
        r = A.skin_at(torso, a, P.COLLAR_SCREWS_Z + 4.0)             # beside its countersink
        u = np.array([math.cos(math.radians(a)), math.sin(math.radians(a)), 0.0])
        head = np.array([r * u[0], r * u[1], P.COLLAR_SCREWS_Z])
        up, _, _ = unit.ray.intersects_location(np.array([head]), np.array([(0.0, 0.0, 1.0)]))
        assert len(up), f"the screw at {a:.0f} deg is not under the unit at rest"
        driver = M.to_mesh(_driver(tuple(head), tuple(u), r=3.0, length=40.0), f"collar_driver_{a:.0f}")
        assert M.overlap(driver, others) <= 0.05, f"no driver reaches the collar screw at {a:.0f} deg"
        tip = screw_head(a)[0]                                    # the insert is behind the hole,
        assert 0.0 < r - math.hypot(tip[0], tip[1]) <= 20.0 - 3.0, (a, r)   # within an M3 x 20's reach


def test_the_head_screws_have_a_driver(world):
    """The unit's four screws are driven from outside, along their holes: 40 mm of driver out from
    the head's skin touches nothing."""
    from test_mech import _driver
    head = world["head"]
    import assemble as A
    for a in P.HEAD_SCREW_ANGLES:
        r = A.skin_at(head, a, P.HEAD_SCREWS_Z + 5.0)             # beside the hole, which the axis is
        ux, uy = math.cos(math.radians(a)), math.sin(math.radians(a))
        driver = M.to_mesh(_driver((r * ux, r * uy, P.HEAD_SCREWS_Z), (ux, uy, 0.0), r=3.0, length=40.0),
                           f"head_driver_{a:.0f}")
        others = M.union([world[n] for n in ("beard_left", "beard_right", "hat", "collar", "panel_left",
                                             "panel_right")])
        assert M.overlap(driver, others) <= 0.05, a


SCREWS = {    # (angles, z, length at each angle): the kit's countersunk M3s, from the drilled holes
    "the head onto the spider": (P.HEAD_SCREW_ANGLES, P.HEAD_SCREWS_Z, {a: 30.0 for a in P.HEAD_SCREW_ANGLES}),
    "the beard's halves onto the head": ((45.0, 90.0, 270.0, 315.0), 417.0,
                                         {45.0: 8.0, 315.0: 8.0, 90.0: 14.0, 270.0: 14.0}),
    "the collar onto the ring": (P.COLLAR_SCREW_ANGLES, P.COLLAR_SCREWS_Z,
                                 {45.0: 16.0, 315.0: 16.0, 125.0: 20.0, 235.0: 20.0}),
}


@pytest.mark.parametrize("what", list(SCREWS))
def test_the_radial_screws_are_the_right_length(what):
    """A countersunk screw driven flush into the skin where the assembler drilled it: it takes at
    least 2.5 mm of its 6 mm insert and stops 0.5 mm short of the insert's floor. The skin and the
    floor are what the assembler measured and cut to (out/stl/holes.json); the lengths are the
    screw kit's."""
    import json
    import mech.head as H
    assert tuple(H.TONGUE_ANGLES) == SCREWS["the beard's halves onto the head"][0]
    assert H.TONGUE_SCREWS_Z == SCREWS["the beard's halves onto the head"][1]
    holes = json.loads((M.STL / "holes.json").read_text())
    angles, z, lengths = SCREWS[what]
    for a in angles:
        h = holes[f"{a:g}@{z:g}"]
        tip = h["skin"] - lengths[a]
        face = h["floor"] + P.INSERT_DEPTH
        assert face - tip >= 2.5, (what, a, h, tip)
        assert tip - h["floor"] >= 0.5, (what, a, h, tip)


# --- the filler on the coat's back ---------------------------------------------------------------
def _local_cyl(r, z0, z1, name):
    from mech.filler import FRAME
    from build123d import Cylinder, Pos
    return M.to_mesh(FRAME * (Pos(0, 0, (z0 + z1) / 2) * Cylinder(r, z1 - z0)), name)


def test_the_filler_port_is_open_and_the_cap_sits_in_it(world):
    """The pocket, the bore and the weep are open through the ring; the cap, screwed on, touches
    nothing of it, and stands out of the skin by its body's top and the grip bar, 14.5 mm at most."""
    import mech.filler as F
    from mech.base import CAP_L, GRIP
    torso = world["torso"]
    for what, origin, d in (("pocket", F.at((6.0, 0.0, -3.0)), F.U),
                            ("bore", F.at((0.0, 0.0, -P.FILLER_POCKET_D + 1.0)), F.U)):
        loc, _, _ = torso.ray.intersects_location(np.array([origin]), np.array([d]))
        assert not len(loc), f"the {what} is closed"
    cap = world["filler_cap"]
    on_neck = M.overlap(cap, M.mech_meshes()["filler_neck"])     # the cap's thread on the neck's
    assert on_neck > 1.0 and M.overlap(cap, torso) - on_neck < 0.5, (M.overlap(cap, torso), on_neck)
    top = -P.FILLER_POCKET_D + F.CAP_END + CAP_L + GRIP[2]
    assert top <= 14.5, top
    far = max(np.dot(v - np.array(F.O), np.array(F.U)) for v in cap.vertices)
    assert abs(far - top) < 0.05, (far, top)


FILL_PANS = (0.0,)


@pytest.mark.parametrize("pan,nod", [(p, n) for p in FILL_PANS for n in (-15.0, 0.0, 5.0)])
def test_a_funnel_and_a_hand_reach_the_filler(world, pan, nod):
    """A funnel's spout, 25 across and 80 long, along the port's axis out of the neck, and a gloved
    hand, 60 across and 60 deep, over the cap's top: neither meets the statue, the sleeves, the
    mitten caps or the turning unit, with the head parked at pan 0 and at every nod. Not at the pan
    stops (test_the_funnel_is_clear_over_most_of_the_pan says how far): the unit's low parts - the beard's flanks to 85 degrees either side of the front,
    and its back corners at 135 and 225, 22 degrees under C - swept through +-65 cover every
    azimuth of the coat, so no port anywhere on it is clear of them at both stops. Fill with the
    head parked; the firmware parks it at 0 whenever it is disarmed."""
    from mech.base import CAP_L, GRIP
    import mech.filler as F
    neck_top = -P.FILLER_POCKET_D + F.NECK_H + 1.5               # over the neck and its thread's end
    spout = M.manifold(_local_cyl(12.5, neck_top, neck_top + 80.0, "funnel"))
    top = -P.FILLER_POCKET_D + F.CAP_END + CAP_L + GRIP[2]
    hand = M.manifold(_local_cyl(30.0, top + 1.0, top + 61.0, "hand"))
    fixed = M.manifold(M.union([world[n] for n in ("collar", "panel_left", "panel_right", "hand_left",
                                                   "hand_right", "base_left", "base_right")]))
    unit = M.moved(M.manifold(M.union([world[n] for n in UNIT])), "nods", pan, nod)
    for what, m in (("the funnel", spout), ("the hand", hand)):
        for other, o in (("the fixed shell", fixed), ("the turning unit", unit)):
            assert M.mvolume(m, o) < 0.05, f"{what} meets {other} at pan {pan:+.0f}, nod {nod:+.0f}"
    torso = M.manifold(world["torso"])
    assert M.mvolume(spout, torso) < 0.05


def test_the_filler_weep_drains_the_pocket(world):
    """The pocket's lowest point drains out through the wall, 10 degrees down: a ray down the weep
    leaves the ring."""
    import mech.filler as F
    import math as _m
    start = F.at((0.0, -(P.FILLER_POCKET_R - 1.5), -P.FILLER_POCKET_D + 1.5))
    dn = _m.radians(10.0)
    d = (_m.cos(dn) * F.E_R[0], _m.cos(dn) * F.E_R[1], -_m.sin(dn))
    loc, _, _ = world["torso"].ray.intersects_location(np.array([start]), np.array([d]))
    assert not len(loc), "the weep is closed"


def test_the_filler_port_skin_is_where_the_mesh_says(world):
    """FILLER_PORT_SKIN_R, which the port is placed by, is the skin at that height and azimuth."""
    import assemble as A
    import trimesh as _t
    outer = _t.load(M.CAD / "out" / "statue" / "outer.stl")
    r = A.skin_at(outer, P.FILLER_PORT_AZ, P.FILLER_PORT_Z)
    assert abs(r - P.FILLER_PORT_SKIN_R) <= 1.0, r


def test_the_funnel_is_clear_over_most_of_the_pan(world):
    """How far the head may be turned with a funnel in the port: every 5 degrees of pan at every
    nod, the spout alone. It is clear from the -65 stop to +35; past that the beard's left flank
    comes round over the coat's back-left."""
    import mech.filler as F
    unit = M.manifold(M.union([world[n] for n in UNIT]))
    neck_top = -P.FILLER_POCKET_D + F.NECK_H + 1.5
    spout = M.manifold(_local_cyl(12.5, neck_top, neck_top + 80.0, "funnel"))
    clear = [p for p in range(-65, 66, 5)
             if all(M.mvolume(spout, M.moved(unit, "nods", float(p), n)) < 0.05 for n in (-15.0, 0.0, 5.0))]
    assert clear == list(range(-65, clear[-1] + 1, 5)) and clear[-1] >= 35, clear

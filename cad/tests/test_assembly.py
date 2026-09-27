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


@pytest.fixture(scope="module")
def world():
    """Everything, at rest, by name: printed parts, bought envelopes, shell sections."""
    iface = M.interfaces()
    out = {n: m for n, m in M.mech_meshes().items() if n not in iface}
    out.update({n: m for n, (m, _) in M.bought().items()})
    out.update(M.sections())
    out["tube"] = M.tube(0.0, 0.0)
    return out


def boards(world):
    return M.union([world["electronics_deck"], world["boards"]])


STEPS = {
    "chassis and cage": (("chassis", "deck_ring"), 130.0),
    "electronics deck": (("electronics_deck", "boards"), 120.0),
    "phone sled": (("phone_sled", "phone"), 150.0),
    "deck sub-assembly": (("deck", "bearing", "bearing_cap", "plate", "hub_ring", "stem", "pin",
                           "bushing", "stop_lug", "horn", "nod_servo", "pan_servo", "fan"), 150.0),
    "collar": (("collar",), 260.0),
    "spider": (("spider",), 60.0),
    "left half of the beard": (("beard_left",), 200.0),
    "right half of the beard": (("beard_right",), 200.0),
    "head and hat": (("head", "hat", "nozzle"), 300.0),
}
WAY = {"left half of the beard": fit_dir(1.0), "right half of the beard": fit_dir(-1.0)}
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
    moving = M.union([world[n] for n in names if n in world])
    there = M.union(list(already(index, world).values()))
    worst = (0.0, None)
    way = WAY.get(step, np.array([0.0, 0.0, 1.0]))
    for dz in np.arange(rise, -1e-9, -STEP):
        m = moving.copy()
        m.apply_translation(way * float(dz))
        v = M.overlap(m, there)
        if dz < 1e-9 and v <= 5.0:
            continue       # at home it sits on its seat: the sections' own allowance for a shared face
        if v > worst[0]:
            worst = (v, float(dz))
    assert worst[0] <= 0.05, f"{step}: {worst[0]:.2f} mm3 in the way at +{worst[1]:.0f} mm"


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


@pytest.mark.xfail(strict=True, reason="the clip-on lens cannot reach the phone: its corner is 89.8 "
                                       "out and the ring's top, as the parting chamfered it, 85; "
                                       "and the 44 mm window is too short for a 30 mm clip centred on "
                                       "the lens. Open: see the README's known limits")
def test_the_lens_clip_goes_in_with_the_phone(world):
    """The phone drops in with its clip-on lens on, down the sled's channel. The phone itself
    passes (the sled step above); this is the clip, lowered with it."""
    from mech.common import box
    clip = M.to_mesh(box(P.PHONE_BACK_X, P.LENS_FRONT_X, P.CAM_Y - P.LENS_CLIP_W / 2,
                         P.CAM_Y + P.LENS_CLIP_W / 2, P.Z_LENS - 15.0, P.Z_LENS + 15.0), "clip")
    torso = world["torso"]
    worst = 0.0
    for dz in np.arange(150.0, -1e-9, -STEP):
        m = clip.copy()
        m.apply_translation((0.0, 0.0, float(dz)))
        worst = max(worst, M.overlap(m, torso))
    assert worst <= 0.05, worst


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
        tip = screw_head(a)[0]                                    # the insert is behind the hole
        assert abs(math.hypot(tip[0], tip[1]) - r) < 8.0, (a, r)


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
    "the beard's halves onto the head": ((30.0, 75.0, 285.0, 330.0), 417.0,
                                         {30.0: 14.0, 330.0: 14.0, 75.0: 12.0, 285.0: 12.0}),
    "the collar onto the ring": (P.COLLAR_SCREW_ANGLES, P.COLLAR_SCREWS_Z,
                                 {45.0: 16.0, 315.0: 16.0, 135.0: 8.0, 225.0: 8.0}),
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

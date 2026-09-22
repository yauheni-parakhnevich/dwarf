# Dwarf — Printed Parts (CAD) Design

- **Date:** 2026-09-22
- **Status:** Approved design, pre-implementation
- **Parent specs:** `2026-09-21-mechanical-design.md` (what the parts must achieve),
  `2026-09-18-dwarf-cat-deterrent-design.md`
- **Sourcing:** `hardware/bom.md`

The mechanical design says what the gnome's body has to do. This document says how it is
modelled: which tool makes which part, how the parts are dimensioned before the bought
components exist, where the body splits for a 256 mm bed, and how the result is checked
without a printer.

## 1. Decisions

| Question | Decision | Why |
|---|---|---|
| Format | **STEP for every mechanical part, STL/3MF for the shell**, STL for everything that goes to the slicer | STEP is a B-rep format; it suits parts with fits, bores and threads. A sculpted organic shell only ever exists as a mesh, and a mesh forced into STEP is a huge faceted solid nobody can edit |
| Toolchain | **build123d** (Python, OCCT) for the mechanism, **Blender 5.2 headless** (Python, `bpy`) for the shell | Both are scriptable, both run from one `build.py`, both are already on this Mac. The mechanism needs exact geometry; the shell needs subdivision surfaces and displacement |
| Source of truth for dimensions | One module, `cad/params.py`, imported by both toolchains | The phone slot, the bearing bore and the belt flange must agree to a tenth of a millimetre, and they are made in two different programs |
| Where the shell meets the mechanism | **Interface parts are modelled in build123d and unioned into the shell mesh** | Precise features (the belt flange with its screw bosses, the turntable deck, the ear bosses for the tilt axle) stay in the tool that does precision. The shell wraps around them |
| Beard | **Fixed to the torso** as a collar around the neck, not to the head | A beard on a nodding head would sweep the chest. On the torso it shrouds the bearing gap, keeps rain off the mechanism and hides the fan exhaust |
| Pan drive | DS3218 under the turntable deck, off-axis, **parallelogram linkage** to a crank on the turntable plate | The mechanical design puts the servo in the torso driving a short hollow shaft. A servo cannot be coaxial with a hollow shaft that has tube and wires passing through it. Equal cranks with a parallel link transfer the angle exactly 1:1 over ±60° with no gear backlash; the only play is at two steel pins |
| Tilt drive | MG996R **inside the head** on a bulkhead, its horn on a printed coupler that passes out through the +Y ear into a hex in the yoke arm; the −Y ear is a boss with an M4 steel pin | No linkage to lose precision in, and the servo body cannot sit outside the head: there it would stand 43 mm proud of the yoke, outside the collar. The mechanical design already routes the tilt servo's wires up through the shaft into the head. The ears hide both pivots |
| Bought parts not yet bought | Every bought dimension is a **parameter with a listing-typical default**, listed in one table and flagged for re-measurement | The bearing, canister, pump and valve are on order or not ordered. Nothing here is committed to their exact sizes; the model is rebuilt from measurements when they arrive |
| Generated files | `cad/out/` is **not committed** | STEP and STL for a dozen parts run to tens of megabytes and change on every parameter tweak. The source is the artefact; a tagged release can carry the binaries when a design is frozen |

## 2. Layout

The gnome is 550 mm tall and stands on a footprint no larger than 250 × 250 mm, so every
section prints flat on the P1P's 256 mm bed.

| Height (mm) | Zone | Contents |
|---|---|---|
| 0–30 | Feet | Slotted floor on four raised feet; four stake holes in the flange |
| 30–210 | Base: boots and coat hem, **wet zone** | 3 L canister lying flat in its cradle; pump on soft grommets; valve immediately after the pump; float switch in the tank head; filler neck from the tank head to a screw cap at the back |
| 210 | **Belt split** | The divider deck is the base's lid: printed at 100 % infill, sealed to the shell with a polyurethane bead, four M3 heat-set inserts, two glands with drip loops for the tube and the wiring |
| 210–392 | Upper torso: coat and belly, **dry zone** | Phone sled, upright, camera end down so the lens sits at about 235 mm behind the belly window with its 10° hood; electronics deck behind the phone; mesh intake low at the back; 40 mm fan exhausting high at the back under the beard collar |
| 372–405 | Shoulders and neck | Turntable deck at 372 carrying the bearing and the hollow shaft; the pan servo hangs in a notch at the deck's rear edge with its horn level with the plate, so the linkage lives in the 16 mm band between the plate and the head's underside — the only band that is neither inside the bearing's footprint nor inside the head |
| 405–490 | Head | Nods in a yoke on the turntable plate. Axle through the ears. Nozzle rigid in the mouth. Nose, cheeks, brows and moustache belong to the head |
| 470–550 | Hat | Bonded to the head and nods with it. A cone with a slight bend and a brim |

The camera sits lower than the mechanical design's 32 cm because the phone must live above
the belt split so it lifts off with the upper assembly. At 235 mm the ground is 7° below
horizontal at 2 m and 2° at 6 m, still well inside the lens's vertical field with the hood's
downward pitch. The aiming calibration is empirical and absorbs the change.

The phone stands upright, portrait, as verified on 2026-09-22 with `quarterTurns` set for a
standing phone: good picture, boxes on the animal, ground point on the feet. Camera-down puts
the lens near the belt line and the phone's bulk in the belly, which is where the gnome has
room. The app's rotation setting is the only thing that knows which way up the phone is, and
it is set once when the sled is fitted and never touched again.

## 3. Mechanism — build123d

All parts in `cad/mech/`, one file per part or per closely related group, each exporting a
STEP and an STL through a shared `export(part, name)` helper. All dimensions come from
`cad/params.py`.

| Part | Fits to | Notes |
|---|---|---|
| Turntable deck | Torso interface; bearing's fixed ring; pan servo below | Bored for the hollow shaft with clearance; bosses for the bearing's screws; slot for the pan link; two printed hard stops at ±65° |
| Turntable plate | Bearing's rotating ring; hollow shaft; yoke; tilt servo | The head's foundation. Carries the pan crank on its underside |
| Hollow shaft | Bonded into the plate; passes through the bearing bore | OD 20 mm, ID 12 mm: room for 6 mm PU tube plus three servo wires with slack. Flared top so the tube's bend radius stays above 25 mm |
| Pan crank, pan link, servo crank | DS3218 horn; turntable plate; M3 screws into inserts as pins | Both cranks 20 mm, link 44 mm equal to the centre distance, all in the band above the plate. The link is the only part that can bind, so it has 0.3 mm clearance at each pin and a printed stop on the deck limits the servo, not the link |
| Yoke | Turntable plate; coupler and ear boss | Two arms on a bridge across the plate; +Y holds the coupler's hex, −Y takes the M4 pin and carries two stop pegs. Hard stops at −35° and +45°, outside the protocol fixture's `cfg` of −30° to +40° |
| Ear boss (interface part), coupler, tilt bulkhead (interface part) | Head shell; yoke; MG996R | The −Y ear boss is unioned into the head with the tilt stop tab. The coupler is a separate part: horn pocket inside, hex outside, turning in a 20.6 mm bore in the head wall. The bulkhead is a chord plate inside the head the servo's tabs screw to |
| Servo mounting | DS3218 hangs in a notch in the deck with its tabs on the deck top and nuts below; MG996R on the bulkhead | Metal screws through the horns; no printed splines |
| Nozzle holder | Head mouth; brass nozzle; PU tube barb | Heat-set inserts for its retaining screws, never printed threads near water |
| Belt flange (interface part) | Base's top edge; divider deck; upper torso's lower edge | Four M3 heat-set bosses; the upper torso's skirt shingles over the base by 8 mm |
| Divider deck | Belt flange; two glands; base cradle beneath | 100 % infill in the slicer; a raised lip for the PU bead |
| Phone sled | Torso rails; iPhone 6s 138.3 × 67.1 × 7.1 mm with clip-on lens | Three-point location, fits one way only (asymmetric key), witness mark. 0.3 mm clearance on the slide, zero on the datum faces |
| Chassis plate | Torso flange's upper inserts | Carries the phone sled at the front and the electronics deck at the back, so everything dry-side bolts to one plate that bolts to the torso |
| Electronics deck | Torso interior behind the phone | M3 standoff holes for ESP32 devkit, two XL4015, three MOSFET modules, fuse holder |
| Tank head | Canister's thread | Printed thread for retention only; the seal is the canister's own gasket. Dip tube boss, float switch mount, vent hole, filler neck stub |
| Tank cradle | Base floor; canister lying flat | Saddle shape; keeps the canister off the floor slots |
| Filler cap | Filler neck | Retention thread plus an O-ring groove |
| Fan frame (interface part) | Torso back, high, unioned into the wall | 32 mm hole pitch inserts for the 40 mm fan; the intake below it is a plain opening with mesh bonded inside |
| Pump mount | Base floor | Four grommet pockets |

**Dimensions of bought parts, with defaults.** All in `cad/params.py`, all re-measured when
the parts arrive:

| Parameter | Default | From |
|---|---|---|
| DS3218 body | 40.0 × 20.0 × 40.5 mm, tabs at 54.5 mm, 25T horn | Datasheet |
| MG996R body | 40.7 × 19.7 × 42.9 mm, tabs at 53 mm, 25T horn | Datasheet |
| Bearing | 60 mm square lazy susan, 6 mm thick, 32 mm central opening, 4 screws | Typical listing |
| Canister | 220 × 140 × 110 mm lying flat, 38 mm thread, 3 mm pitch | Typical 3 L listing |
| Pump | 160 × 100 × 65 mm, four feet on 130 × 70 mm | Typical listing |
| Valve | 45 × 25 × 55 mm, G1/4 ports | Typical listing |
| ESP32 devkit | 55 × 28 mm, holes not standard, sits in a printed cradle | Measured on the board in hand |
| XL4015 | 54 × 23 mm, two 3 mm holes | Typical listing |
| Fan | 40 × 40 × 10 mm, 32 mm hole pitch | Standard |
| iPhone 6s | 138.3 × 67.1 × 7.1 mm; rear camera centre 11 mm from the top edge and 11 mm from the side | Apple |

## 4. Shell — Blender

All scripts in `cad/shell/`, run by Blender in background mode from `build.py`. The shell is
built from primitives with subdivision surfaces, shaped by lattice and proportional edits in
script, with a displacement modifier driven by a procedural texture for the beard's strands
and the hat's felt. Blender only sculpts: each section is joined, voxel-remeshed and solidified to a 2.4 mm
wall, then exported as a raw closed mesh. Every boolean — unioning the interface parts,
cutting the openings and the section splits — runs afterwards in Python with `manifold3d`
through `trimesh`, because Blender's exact boolean was measured to leave non-manifold
results on subdivided meshes while manifold's stayed watertight in every probe.

**Style:** the classic garden gnome. Pointed hat with a bend near the tip and a rolled brim,
a round nose, full cheeks, heavy brows, a moustache on the head, a long beard on the torso
collar, a coat with a belt and buckle at the split line, and boots on the base.

**Sections, each within 256 mm in every axis:**

| Section | Height | Material | Contains |
|---|---|---|---|
| Base | 0–218 | PETG | Boots, coat hem, feet, stake flange, the belt flange's lower half |
| Upper torso | 210–392 | PETG | Belly, coat, window opening, vent openings, phone rails, the belt flange's upper half and the turntable deck's mounting ring |
| Beard collar | 330–420 | PETG | The beard and the neck shroud; bolts to the upper torso from inside |
| Face | 405–495, the cap in front of x = 20 | ASA if enclosed, else PETG | Nose, cheeks, brows, moustache, mouth opening, nozzle bosses inside |
| Back of head | 405–495, behind x = 20 | Same as face | Both ears, the tilt bulkhead, the face lip, the bottom opening for tube and wires |
| Hat | 473–550 | PETG | Bonded to the head on a spherical seat |

Horizontal seams shingle with the upper part outside the lower; vertical seams (face to back
of head) have dowel pockets and an inside lip. The belt split is the one seam that reopens,
on four M3 screws into the belt flange's inserts.

**Openings**, each cut with a primitive from the parameters so its position matches the
mechanism: camera window 40 × 60 mm centred on the lens; mouth 12 mm round for the nozzle;
ear bores; low intake and high exhaust vents at the back; filler neck at the back of the
base; drain slots in the floor.

## 5. Repository layout and build

```
cad/
  README.md          how to build, what to re-measure, which part is which
  params.py          every dimension, one place
  build.py           mech → shell → previews, or any one stage
  mech/
    common.py        export helper, servo and bearing models, shared profiles
    turntable.py     deck, plate, shaft, cranks, link, yoke, ear bosses
    head.py          nozzle holder
    torso.py         belt flange, divider deck, phone sled, hood, electronics deck
    base.py          tank head, cradle, filler cap, pump mount, vent frames
  shell/
    common.py        scene setup, import of interface STL, boolean helpers, export
    body.py          base and upper torso, raw
    head.py          face, back of head, hat, raw
    beard.py         beard collar, raw
    preview.py       workbench renders of each finished section and the assembly
  assemble.py        manifold booleans: interface parts in, openings and splits out
  tests/
    test_mech.py     build123d parts
    test_shell.py    exported meshes
  out/               generated, ignored by git
    step/  stl/  preview/
```

A dedicated virtual environment, `.venv-cad`, holds build123d, bd_warehouse, trimesh, manifold3d, rtree and pytest, created
with `uv` like the model-export environment. Blender uses its own bundled Python and needs
nothing installed; `params.py` is plain Python so both interpreters import it.

`build.py mech` writes every mechanism part as STEP and STL. `build.py shell` runs Blender
with each shell script and writes the raw section meshes; `build.py assemble` unions the
interface STLs in and cuts the openings, writing the printable sections.
`build.py preview` renders each section and the whole assembly from the front, side and a
three-quarter view. `build.py` with no argument does all three in order.

## 6. Verification without a printer

**Mechanism tests** (`tests/test_mech.py`, pytest in `.venv-cad`):

- Every part is a single valid solid with positive volume.
- Every part's bounding box fits within 256 mm in each axis.
- The phone slot is the phone's size plus 0.3 mm on the sliding faces and 0.0 mm on the
  datum faces.
- The hollow shaft's bore is at least the tube's outside diameter plus three wires' width
  plus 2 mm.
- The pan hard stops sit outside the firmware's `cfg` pan limit and the tilt stops outside
  the tilt limit, read from the same protocol fixtures the firmware tests use.
- The parallelogram's crank lengths are equal and the link length equals the centre distance,
  so the linkage stays a parallelogram.
- The belt flange's insert bosses land within the base's wall footprint.

**Shell tests** (`tests/test_shell.py`, trimesh on the exported STL):

- Every section is watertight and has consistent winding.
- Every section fits within 256 mm in each axis.
- The mechanism's bounding boxes, transformed to their assembled positions, lie entirely
  inside the shell's cavity: the phone sled inside the upper torso, the canister and pump
  inside the base, the turntable inside the shoulders, the nozzle holder inside the head.
- Every opening exists: a ray cast through the window position, the mouth and each vent
  passes through without hitting the shell.

**Previews** are the look test. Nothing automated judges whether it looks like a gnome; the
renders are inspected after every change to the shell scripts.

## 7. Risks

| Risk | Mitigation |
|---|---|
| Bought parts arrive a different size from the defaults | Every bought dimension is a parameter; the README lists what to measure. Print nothing that touches a bought part until it has been measured |
| Booleans on subdivided meshes produce non-manifold results | Measured: Blender's exact solver fails this, manifold3d does not. All booleans run in manifold3d; the watertight test catches any regression |
| Printed thread on the tank head does not match the canister | The thread is retention only and its pitch, diameter and starts are parameters; print the tank head alone first as the fit coupon |
| Head with hat is top-heavy and its centre of gravity is above the axle | The ear boss height is a parameter; balance the printed head on a rod and move the parameter, then reprint the face and back only |
| The shell's wall thickness is uncertain where displacement adds beard texture | Displacement is applied outward only, from a 2.4 mm base wall, so texture adds material and never thins it |
| Interface parts unioned into the mesh leave internal faces | Union is followed by a mesh clean-up pass and the watertight test |

## 8. Out of scope

- The visual design of the face beyond "classic gnome"; it is judged from renders, not
  specified.
- A GT2 belt or spur-gear pan drive. The parallelogram is the design; a gear pair is the
  fallback if the link binds in testing.
- Printing profiles, supports and slicer settings. `hardware/bom.md` carries the material
  and nozzle guidance.
- Weatherproofing and paint.
- Any printed part in the pressurised water path.

## 11. Revisions

- **2026-09-22, Task 1 of the plan.** The first layout test found the phone did not fit: 138 mm of
  phone between a chassis at 230 and a deck ring at 358 leaves 133 mm, and the torso narrowed below
  the phone's top corners. As built in `cad/params.py`: the deck rises to 380 and everything above
  it by 8 mm (head centre 458, brim 481, top **558 mm**); the lens sits at 245; the shoulders stay
  96 mm in radius up to 373 and are hidden under the beard collar; the deck ring is a narrow
  annulus (50–66 mm) joined to the wall by four webs so the phone passes outside it; the phone is
  centred and its camera sits 22.5 mm off the centreline, an offset the aiming calibration absorbs
  like every other. `BASE_PROFILE` is the outer skin only; the raised floor is a separate revolve
  row. The layout table in §2 is superseded by `params.py` where they differ.
- **2026-09-22, Tasks 1–2 review.** At pan zero both cranks pointed backwards and the link's far
  eye sat inside the neck wall; the neck is now 76 mm in radius (`TORSO_R_TOP`), hidden under the
  collar, and both cranks point +Y at rest so the link runs beside the shaft's mouth rather than
  across it. The deck ring is cut around the pan servo. The yoke stands on a ring on the plate's
  rim rather than on feet outside it. The window is biased 6 mm above the lens so it stops above
  the belt joint.
- **2026-09-22, Task 3.** The parallelogram could not live above the plate at all: a servo whose
  horn clears the yoke ring has its body top above the plate's underside, and that body sits
  inside the plate's radius. The pan servo now hangs under the deck, shaft down, at (5, −54);
  the plate's front stop tab carries a column through an arc slot in the deck to a foot bar
  with the crank pin at 30 mm; the link runs below both cranks. With 30 mm cranks and the servo
  54 mm off the axis no bar comes within 14 mm of the pan axis at any angle, which is where the
  tube and wires drop out of the shaft. The deck is 80 mm in radius to carry the servo's
  hangers. The band above the plate now holds only the tube and wires. §1's "pan drive" row and
  §3's linkage rows are superseded by this.
- **2026-09-22, Tasks 3–4 review.** Numbers as built: the pan servo sits at (5, −60), the deck is
  84 mm in radius, and the link's centreline comes to 14.6 mm of the pan axis at the +65° stop.
  The mechanism review then proved the head uninstallable: an MG996R cannot be threaded onto a
  plate inside a 90 mm sphere, none of its screws has a driver path, and a coupler with a horn
  boss cannot pass the wall. The tilt servo now rides a **cradle assembled on the bench** that
  slides in through the face opening along rails on the back of the head and is boxed in by a lip
  and a stop block on the face cap; the **coupler** is a plain 24 mm cylinder with a hex, entered
  from outside through the arm and a 24.6 mm wall bore, its two horn screws driven down
  counterbores; the ear pin is an M4 bolt into an insert; the arm's cross screw has an insert.
  The pan crank's top is the servo's shaft face so the horn sits in its pocket; the deck's stop
  posts are separate pins so the deck prints flat, their tops 1.5 mm under the yoke; the shaft
  reaches below the link's plane; link eyes ride on 3.2 mm bores with half-millimetre bosses.
  The fan frame follows the barrel instead of standing proud of the shoulder at 348 mm.

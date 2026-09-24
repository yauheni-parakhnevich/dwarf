# The printed gnome

Every printed part of the deterrent, generated from one file of numbers. `params.py` is the only
place a dimension is written down; the mechanism is build123d, the shell is the reference
statue, and the two meet in `assemble.py`, where manifold booleans let the interface parts into
the shell and cut the openings out of it. Nothing generated is committed.

The gnome stands **700 mm**. There are **ten shell sections** and **25 mechanism parts**, three
of which are unioned into the shell rather than printed on their own, and the stop pin prints
twice: **33 prints** in all, none wider than the 256 mm bed. About 1.8 kg of shell and 1.1 kg of
mechanism at 1.27 g/cm³.

The shell is no longer sculpted. It is an image-to-3D reconstruction of the user's own garden
gnome, hollowed to a 2.4 mm wall and cut into pieces around what has to turn: the coat's belt
ring and the two sleeve panels stay still, and everything above the beard's bottom edge - beard,
face, ears, hat - is one **bell** that turns on the neck shroud through ±65°. The head does not
nod; only the nozzle tilts, on a micro servo inside the beard, and its jet leaves through the
beard's parting under the mouth. There is no belly hatch: with the bell lifted off, the whole
inside is open from the top.

![The gnome, front and three-quarter](docs/gnome_front.png) ![](docs/gnome_iso.png)

![Cutaway through the assembled gnome](docs/cutaway_iso.png) ![The mechanism alone](docs/mechanism_iso.png)

*Renders from `build.py preview`, reduced. The full set is written to `out/preview/`, and
`out/statue/preview_*.png` shows the statue, its sections and the bell on its own.*

**To look at the assembly in Blender:** `.venv-cad/bin/python cad/build.py scene` writes
`out/gnome.blend` with every section and part as its own object, in collections (Shell, with the
bell tinted apart from the fixed pieces; Mechanism split into fixed / turns with the head /
interface; bought-part envelopes as wireframes). `open -a Blender cad/out/gnome.blend`.

## Build

```bash
uv venv --python 3.11 .venv-cad
uv pip install --python .venv-cad/bin/python -r cad/requirements.txt

.venv-cad/bin/python cad/build.py              # every stage, about a minute and a half
.venv-cad/bin/pytest cad/tests -q              # 172 tests in six files, 60-90 s
```

Blender 5.2 is driven headless from `/Applications/Blender.app`; set `BLENDER` to point
somewhere else. It is the only thing not installed by pip, and it is used for nothing but
hollowing the statue and the previews.

| Stage | What it does | Time |
|---|---|---:|
| `mech` | build123d: every mechanism part to `out/step/` and `out/stl/`, in the frame it prints in, plus the placed `mechanism_assembly` in both formats | 5 s |
| `statue` | the reconstruction into the project frame, hollowed in Blender, both voids cut back off the folds, measured, cut into the ten raw sections in `out/statue/raw/`, and its own previews | 60 s |
| `assemble` | trimesh + manifold3d: interface parts clipped into the cavity and unioned in, openings cut, ten printable sections to `out/stl/` | 3 s |
| `preview` | Blender: 38 renders to `out/preview/` — the gnome, each section, the mechanism, and a cutaway | 12 s |
| `scene` | Blender: `out/gnome.blend`, every section and part as its own object in assembled position | 2 s |

That is about a minute and a half on an idle machine — 82 s measured — and the `statue` stage is
three quarters of it, most of that the two keep-out passes that cut the folds out of the voids.
With other work running the whole build has been measured at two and a half minutes.
Stages can be named individually and run in any order, as long as `mech` and `statue` have run
before `assemble`. The tests that need built files skip themselves when there are none. The
`shell` stage is still in the list and does nothing: it says so and points here.

A Blender script that raises still exits 0 - Blender prints the traceback and quits happily - so
the stages that drive it delete what each script owns before running it and check afterwards
that it came back, by name and by mtime. A broken run fails the build instead of quietly leaving
yesterday's mesh for everything downstream to validate.

## The statue

`cad/in/` holds the reference photographs of the statue - front, back, left, right, bottom and
three close-ups - `gnome_ai.glb`, the reconstruction made from them, and `fit_report.md`, the
measurement pass that turned it into the numbers in `params.py`.
**It is not committed** - it is 200 000 triangles of someone's garden ornament - so a fresh
clone builds the mechanism but stops at `statue` until the file is put back.

To make it again: clone `Tencent/Hunyuan3D-2`, install its `hy3dgen` package, and run the
multi-view pipeline `tencent/Hunyuan3D-2mv` on four photographs of the statue - front, back,
left, right, evenly lit, the whole figure in frame. On an M4 Pro it runs locally on MPS in fp16;
backgrounds come off with `rembg` first, the shape pipeline is given an octree resolution of 384
and 50 inference steps, and the result takes about twenty minutes. Export the mesh as GLB to
`cad/in/gnome_ai.glb`. Nothing else about the model matters to this build: the `statue` stage
scales whatever it is given to `Z_TOP` and puts it in the project frame itself.

What that stage does, in order:

1. **Frame.** X = z, Y = x, Z = y of the GLB; scaled so the height is exactly `Z_TOP`; the soles
   on z 0; the body axis on the Z axis.
2. **Straighten and mirror.** The reconstruction leans - its lower half is centred near y +4 and
   its head near y +16 - so each height is slid sideways onto the axis before the +y half is
   mirrored onto the −y one. The shear is in y alone, so every horizontal section keeps its own
   shape and nothing is made fatter. `out/statue/outer.stl` is the result.
3. **Hollow.** Blender's SOLIDIFY, inward, twice: `WALL` for the wall solid that `cavity.stl`,
   the plain void, is cut from, and 1.2 mm for the `cavity_grown.stl` the assembler clips
   interface parts to, so a boss ends inside the wall and fuses to it instead of hovering a
   clearance away.
   SOLIDIFY offsets a *surface*, not a solid, so wherever the skin has a ridge thinner than two
   walls - the fold of the skirt over the boots, the parting between two strands of the beard -
   the offset runs through itself and the void reaches into the ridge as a spike. The wall there
   measured nothing at all. So both voids are then cut back: the thin patches are found by
   measuring, and around each one the distance to the skin is sampled on a 0.7 mm lattice and
   its contour meshed and subtracted, which is the honest erosion of the solid and simply loses
   a ridge too thin to hold the offset. Each void is cut 0.2 mm under its own nominal - the
   cavity at `WALL − 0.2`, `cavity_grown` at `WALL − 1.2 − 0.2` - which is never deeper than
   that void already goes, so the grown cavity still contains the cavity and nothing the
   mechanism is fitted to moves. It is local: each void keeps its own surface everywhere it was
   already deep enough. `shell.stl` is taken from the cut-back cavity, so the two stay each
   other's complement in the skin. `test_wall.py` measures what comes out: `WALL_MIN` is the
   floor the wall may never go under, and `WALL_MIN − 1.2` the floor for the grown cavity - the
   skin a boss clipped to it must still have over it.
4. **Measure.** `out/statue/features.json` - the feature heights (measured on the mesh where it
   has a signature, from `STATUE_FEATURES` where it has not, and it says which is which), the
   cavity's reach from the pan axis every 5 mm in five directions, and the two trouser legs'
   centres and free radius at `Z_FLOOR − 50`. **Everything else reads that file rather than
   guessing at the skin**, including the layout tests and the pump and valve brackets.
5. **Cut.** The ten raw sections, and the bell is turned through its stops against the fixed
   pieces every 5° to prove it does not touch them.

Every mesh it writes is read back from its own file and re-checked before the stage goes on: an
STL has no vertex identity, so a boolean that leaves two vertices in one place makes a solid
that is watertight in memory and not on disk.

## Before printing anything that touches a bought part

These numbers are listing-typical guesses. Measure the part in your hand, change `params.py`,
rebuild, and only then print anything that has to fit it.

| Parameter | Measure |
|---|---|
| `CAN_THREAD_PITCH`, `CAN_THREAD_LEN`, `CAN_NECK_ID` | **first, before anything else.** 3.0 mm, 12 mm and 30 mm are guesses, and the tank head's thread is cut to them: if the bottle's pitch is 4 or 6 the head does not screw on at all and no amount of sanding fixes a wrong pitch. Measure the bottle's neck — thread pitch, how far the thread runs down, the bore through it — and **print `tank_head` first as the coupon**, before the divider or anything else that takes a day |
| `BOTTLE`, `BOTTLE_SHOULDER_H`, `BOTTLE_SHOULDER_IN`, `BOTTLE_THREAD_MAJOR` | the 1 L rectangular bottle lying on its wide face, **and the taper of its shoulder**: its shoulder corners pass the coat's wall with about 2.5 mm at both ends. A squarer bottle does not go in |
| `PUMP`, `PUMP_FEET` | the micro diaphragm pump's body and the pitch of its feet — it stands in the left trouser leg, hanging under the floor plate |
| `VALVE`, `VALVE_STRAP` | the solenoid's body, and how tall the strap has to arch over it |
| `DS3218` | the pan servo as delivered: body, tab span, tab thickness, tab height, shaft offset, hole pitch |
| `MG92B` | the tilt servo, the same six numbers. It is a micro servo now, inside the beard |
| `HORN_D`, `HORN_T`, `HORN_SCREW_R`, `MICRO_HORN_D` | the round horns in both servos' bags — the crank and the nozzle arm are pocketed for them |
| `BEARING_SQ`, `BEARING_T`, `BEARING_PITCH`, `BEARING_HOLE` | the lazy susan: plate size, thickness, the bolt pitch and the bolt holes |
| `XL4015_HOLES`, `XL4015_HOLE_D` | the buck converters' mounting holes; the outlines come from `EDECK_LAYOUT` |
| `MOSFET_HOLES` | the MOSFET modules' hole pitch — the listing rarely gives it |
| `ESP32` | the devkit's outline. It has no usable hole pattern, so it sits in a printed cradle with tie slots |
| `FAN`, `FAN_T`, `FAN_PITCH` | the 40 mm fan's frame and screw pitch. It hangs under the deck and blows up through it |
| `LENS_CLIP_T`, `LENS_CLIP_W` | how far the clip-on lens stands off the phone's back glass, and how wide the clip is |
| `GLAND_D` | the M12 cable glands' thread |
| `NOZZLE_D` (`MOUTH_D` follows it) | the brass nozzle's shank, which the mouth is a bearing for |
| `FLOAT_HOLE_D`, `DIP_TUBE_D`, `FILLER_D`, `TUBE_OD`, `TUBE_BEND_R` | the float switch, the dip tube, the filler, and the PU tube with its static bend radius — the tube's route is planned by that radius |
| `FILLER_CAP_THREAD_MAJOR`, `FILLER_CAP_PITCH` | the filler cap is printed against its own neck; print the pair first as a coupon |
| `PHONE_L`, `PHONE_W`, `PHONE_T`, `PHONE_CAM_FROM_END`, `PHONE_CAM_FROM_SIDE` | the phone, with its case off. The sled is the second fit coupon |
| `HOSE_OD`, `HOSE_BARB_D`, `HOSE_BARB_L` | the filler hose. 8 mm silicone with about a 5 mm bore is what the belly leaves room for, and both barbs are cut to it — the tank head's and the filler neck's. A stiffer hose of the same bore will not take the corners; see `HOSE_BEND_R` |
| `INSERT_D`, `INSERT_DEPTH`, `INSERT_DEPTH_SHORT` | the heat-set inserts you actually bought |

## What prints, and how it lies on the bed

Material is **PETG** throughout: PLA softens in a closed body in the sun, and ASA wants an
enclosure at these sizes. If you have one, the bell - beard, head and hat - is
the part worth printing in ASA: it is the most sun-exposed and it is what anyone looks at.
Four perimeters on anything the mechanism screws into; the divider at 100 % infill.

The shell's sections are a 2.4 mm wall, so their volume is very nearly what they weigh: there is
no infill to speak of. Grams are at 1.27 g/cm³, solid.

### Shell — ten pieces

| File | What it is | mm | cm³ | g | On the bed |
|---|---|---|---:|---:|---|
| `base_left` | Boots, hem and skirt to the belt, split at y 0; drain arches, stake holes; the lower belt flange and the floor plate inside | 219 × 164 × 240 | 352 | 447 | Cut face down |
| `base_right` | Its mirror image | 219 × 164 × 240 | 353 | 449 | Cut face down |
| `hand_left` | The mitten cap, glued to the base half | 127 × 31 × 44 | 14 | 18 | Cut face down |
| `hand_right` | Its mirror image | 127 × 31 × 44 | 14 | 18 | Cut face down |
| `torso` | The coat's belt ring between the sleeves: the camera window, the intake at the back, the upper belt flange inside | 186 × 210 × 67 | 167 | 212 | Belt down |
| `panel_left` | The left sleeve and the shoulder's side, fixed, glued to the ring | 126 × 31 × 160 | 31 | 39 | Cut face down |
| `panel_right` | Its mirror image | 126 × 31 × 160 | 31 | 39 | Cut face down |
| `beard` | The bell's skirt: the beard to the chin, turned down to r 103 where it sweeps inside the panels, with the nozzle's parting | 189 × 228 × 103 | 177 | 225 | Rim down |
| `head` | Face, ears and the top of the beard, the mouth, the parting's upper half, four countersunk M3 × 30 into the shroud at z 440 | 188 × 221 × 88 | 137 | 174 | Cut face down |
| `hat` | Brim and cone, leaning back | 152 × 150 × 200 | 138 | 175 | Brim down |

### Mechanism — 25 parts

Three of them never print on their own: they are blanks the assembler clips to the cavity and
unions into a shell section, and their STLs exist only because that is how it eats them.

| File | What it is | mm | cm³ | g | On the bed |
|---|---|---|---:|---:|---|
| `belt_flange_lower` | The ring under the split the belt screws thread into, and its tongue | 178 × 240 × 16 | 204 | — | — into `base_left`/`base_right` |
| `belt_flange_upper` | The ring the belt screws pass down through, inside the skirt | 178 × 240 × 8 | 120 | — | — into `torso` |
| `floor_plate` | The wet zone's floor at `Z_FLOOR`, with the pour hole and the two leg ports | 212 × 250 × 4 | 159 | — | — into `base_left`/`base_right` |
| `divider` | The base's lid, sealed with a PU bead. **100 % infill, six perimeters** | 147 × 209 × 8 | 197 | 250 | Flat, with a brim |
| `sand_plug` | Closes the floor plate's pour hole | 38 × 38 × 6 | 4 | 5 | Disc down |
| `chassis` | The dry zone's floor, bolted down by the belt screws; carries the sled and the electronics deck | 135 × 200 × 12 | 74 | 94 | Flat |
| `phone_sled` | The phone drops in camera-down, screen to −X, from above. Fits one way | 26 × 73 × 136 | 31 | 39 | Upright, back to the bed |
| `electronics_deck` | ESP32 cradle, two XL4015, three MOSFET modules, a fuse holder | 100 × 92 × 8 | 36 | 46 | Flat |
| `filler_neck` | Bonded into the divider's front: the cap screws onto the M22 above it, the hose pushes onto the Ø6.5 barb hanging below it | 32 × 32 × 33 | 4.9 | 6 | Flange down |
| `tank_cradle` | The bottle's bed on the floor plate | 103 × 201 × 14 | 57 | 72 | Flat, as it stands |
| `tank_head` | Screws onto the bottle: dip tube, float switch, vent, and the filler's Ø6.5 barb off the shoulder | 44 × 60 × 30 | 24 | 31 | Axis vertical, mouth down; one blob under the barb |
| `filler_cap` | Retention thread; an O-ring in the groove seals | 32 × 32 × 14 | 5 | 7 | Open end down |
| `pump_bracket` | Hangs the pump in the left trouser leg under the floor plate | 51 × 46 × 103 | 43 | 54 | On its plate, cage up |
| `valve_bracket` | The same for the solenoid, in the right leg | 51 × 31 × 63 | 17 | 22 | On its plate, cage up |
| `valve_strap` | The bar that closes the valve's cage | 51 × 12 × 3 | 2 | 2 | Flat |
| `deck_ring` | A cage: the annulus the deck bolts to, on four legs down to the chassis | 124 × 130 × 134 | 109 | 139 | **Top annulus down**, legs up, **tree supports under the tie** |
| `deck` | Carries the bearing, the pan servo hanging under it, the fan, and the pan hard stops | 152 × 166 × 45 | 118 | 149 | Flat, hangers up |
| `stop_pin` | **Glued** into a Ø6.4 seat in the deck; the plate's tab runs into it. **Print two** | 6 × 6 × 16 | 0.4 | 1 | On end |
| `plate` | The head's foundation on the bearing; carries the shaft and the stop tab | 114 × 100 × 76 | 43 | 54 | Column up |
| `shaft` | Hollow and passive: water and wires up through the turning neck | 27 × 27 × 90 | 20 | 25 | On end |
| `servo_crank` | On the pan servo's horn, pocketed from above | 48 × 27 × 6 | 3 | 3 | Flat |
| `pan_link` | Joins the plate's pin to the crank's pin | 14 × 69 × 3 | 1 | 2 | Flat |
| `neck_shroud` | Turns with the plate and carries the bell; six radial inserts — four for the bell, two for the tilt bracket — and four Ø7 chimneys through the roof | 106 × 104 × 40 | 52 | 66 | **Closed (roof) end down** |
| `tilt_bracket` | Hangs off the shroud's front, carries the micro servo and the nozzle arm's pivot | 29 × 55 × 44 | 5 | 6 | Flat, on its back |
| `nozzle_arm` | The lever on the micro horn that swings the nozzle through the parting | 36 × 15 × 14 | 4 | 5 | Flat |

### Three of those orientations were measured, not assumed

Counting the down-facing area — within 45° of horizontal — that has nothing within a millimetre
under it in the stated pose:

- **`neck_shroud` prints closed end down, not open end down.** Stood on its rim, the whole
  ceiling of the cup hangs 40 mm over a void: **7 486 mm²**. Roof on the bed it is **1 902 mm²**,
  and 1 528 of that is one feature — the base ring's inward step, where the bore goes from
  r 49.6 to r 44 across 5.6 mm at the very top of the print. The remaining 342 mm² is the
  undersides of the six radial bosses. The four Ø7 access chimneys are bored along the axis, so
  they print vertically either way up.
- **`deck_ring` needs supports whichever way up**; "legs down, no support" was wrong. Legs down
  leaves **4 261 mm²** — both the top annulus and the tie ring cantilever off four 12 mm legs.
  Top annulus down leaves **2 505 mm²**: only the tie ring does. It also puts 2 700 mm² of ring
  flat on the bed instead of four 144 mm² feet under a 134 mm tower. So: **top annulus down,
  legs up, tree supports under the tie ring.**
- **`tank_head` still prints mouth down.** Under the old Ø22 filler stub that left 1 723 mm²
  hanging. The stub is a Ø6.5 barb off the shoulder now and the figure is **119 mm²** — a 16 mm
  cantilever 19 mm above the bed, which wants one small support blob under its end and nothing
  else. The other 674 mm² the measurement finds is the bottle thread's spiral and the 45° roof
  over the bore, both self-supporting by construction.

`deck` hangers-up measures 0 mm² and `plate` column-up 148. `pump_bracket` on its plate,
cage up, measures 2 068 — but that is the cage's floor bridging the 45 mm between its two flank
walls, not a cantilever, and it stays as it is.

## Fasteners

M3 heat-set inserts everywhere a printed part is screwed into, M3 machine screws through. Depths
are what the geometry actually gives, and the counts are the ones in the code.

| Part | Feature | Count | Type |
|---|---|---|---|
| `belt_flange_lower` | on the belt ring's mid-line ellipse (67, 98) at 55/140/220/305°, which lands at r 89.0 and 81.3, down from `Z_BELT` | 4 | M3 insert, **9 mm** |
| `belt_flange_upper` | the same four, 3.4 through with a Ø6.4 head recess | 4 | **M3 × 20** — the belt, through the divider into the lower flange |
| `divider` | the same four, 3.4 through | 4 | the same belt screws |
| `belt_flange_upper` | the same ellipse at 70/150/210/330° — r 94.9 and 75.9 — up from its top face | 4 | M3 insert, 6 mm — the chassis |
| `chassis` | the same four, 3.4 through | 4 | **M3 × 10** through 4 mm of chassis into a 6 mm insert |
| `floor_plate` | four at (±40, ±70), down | 4 | M3 insert, 6 mm — the bottle's cradle |
| `tank_cradle` | the same four, 3.4 through | 4 | M3 up into the plate |
| `floor_plate` | four per leg at the two leg centres (−6.9, ±39), up | 8 | M3 insert, 6 mm — the pump and valve brackets |
| `pump_bracket`, `valve_bracket` | four each, 3.4 up through the plate | 8 | M3 into those inserts |
| `valve_bracket` | two strap bosses | 2 | M3 insert, 6 mm |
| `valve_strap` | two 3.4 through | 2 | M3 up into the bracket |
| `chassis` | two lock bosses on the sled's line | 2 | M3 insert, 6 mm |
| `phone_sled` | two lugs, 3.4 through | 2 | M3 into those inserts |
| `chassis` | three e-deck standoffs | 3 | M3 insert, 6 mm |
| `electronics_deck` | three 3.4 through | 3 | M3 into those inserts |
| `electronics_deck` | 8 × Ø3.2 (two XL4015), 12 × Ø3.4 (three MOSFET modules) | 20 | the modules' own screws |
| `deck_ring` | four feet, up from the bottom of each leg | 4 | M3 insert, 6 mm — up through the chassis |
| `deck_ring` | r 60 at 82/98/235/250°, down from its top face | 4 | M3 insert, **7 mm** |
| `deck` | the same four, 3.4 through | 4 | M3 down from the deck's top face into the ring |
| `deck` | r 33.94 at 45/135/225/315° | 4 | the lazy susan's own bolts |
| `deck` | four hangers, up | 4 | M3 insert, 6 mm — the pan servo's tabs |
| `deck` | four at `FAN_PITCH` round the fan hole, up | 4 | M3 insert, **4 mm**, blind in a 6 mm deck — the fan hangs under it |
| `deck` | two Ø6.4 seats (`STOP_PIN_SEAT_D`) at ±70.7°, r 60, right through the deck | 2 | stop pins — **glue them, do not press**: a Ø6.0 pin in a Ø6.1 seat split the deck |
| `plate` | r 33.94 at 45/135/225/315° | 4 | the lazy susan's own bolts |
| `plate` | r 46.7 at 45/135/225/315°, down | 4 | M3 insert, **5 mm** — the shroud |
| `neck_shroud` | the same four, 3.4 through with the heads sunk and a Ø7 chimney (`SHROUD_ACCESS_D`) carried up through the roof over each | 4 | **M3 × 10** into the plate, driven down the chimney with a long driver |
| `plate` | pin boss, up | 1 | M3 insert, 4.5 mm — the link's pivot |
| `servo_crank` | pin boss, up | 1 | M3 insert, 4.5 mm — the link's pivot |
| `servo_crank` | r 7, four positions, 2.8 through | 4 | M2.5 self-tapping into the pan horn |
| `pan_link` | two 3.2 eyes | 2 | turn on the pivot screws' shanks |
| `neck_shroud` | four radial bosses at 60/120/240/300°, z 440 | 4 | M3 insert, 6 mm — **the bell screws onto these** |
| `head` | the same four, 3.4 through with a Ø6 countersink sunk 2 mm; the skin there is at r 84.1–84.3 | 4 | **M3 × 30 countersunk**, driven from outside. They are in the `head` section, which spans 412–500 — not in `beard` |
| `neck_shroud` | two more radial bosses at ±24°, z 424 | 2 | M3 insert, 6 mm — the tilt bracket |
| `tilt_bracket` | two radial 3.4 through, into those | 2 | M3, driven before the beard goes on |
| `tilt_bracket` | the micro servo's two tabs and the arm's pivot | 3 | M2 into the servo, M3 through the pivot |
| `nozzle_arm` | the micro horn's screws | 2 | M2 self-tapping into the horn |

**Totals.** 55 M3 inserts — 4 at 9 mm, 4 at 7 mm, 4 at 5 mm, 2 at 4.5 mm, 4 at 4 mm and **37 at
6 mm** — and 55 M3 screws to fill them, of which four are the M3 × 20 belt screws, four the
M3 × 10 that hold the shroud down, four the M3 × 30 countersunk through the head, and the rest
between 8 and 14 mm. Add 8 M3 through the lazy susan's own holes, 20 small screws for the
modules' own feet, and eight small self-tappers — four M2.5 into the pan horn, four M2 into the
micro horn and the micro servo's tabs. Buy the inserts and the soldering tip before anything
else: half the assembly below is inserts.

**Where the M3 × 30 comes from.** Nothing in `params.py` states it. The bell hangs on four
countersunk screws driven inward along the meridians at z 440, and the length is the distance
from the skin they sit flush in to the floor of the insert they land in. The statue's skin at
z 440 measures r 84.33 at 60 and 300°, r 84.09 at 120 and 240°; the boss's face is at
`SHROUD_R_OUT` + 5 = r 57 and the insert's floor `INSERT_DEPTH` further in, at r 51. So the hole
is 33.1–33.3 mm deep and **M3 × 30** is the screw: it takes about 2.7 mm of the 6 mm insert, and
an M3 × 35 bottoms out on the boss's back wall before its head seats. Note what that length is
made of — 27 mm of it crosses the open gap between the bell's inner skin and the shroud, and
only the last few millimetres are in anything.

## Assembly

Heat every insert first, with the parts cold and on a flat surface. Then:

**The legs, before the base is glued.** The pump's bracket and the valve's bracket bolt **up**
into the floor plate from underneath, and once the two halves are together there is no way under
that plate at all - the boots are closed. Every one of a bracket's four bolts lies wholly on one
side of y 0, so each bracket goes on its own half while that half is still open at the cut face:
pump into the left leg with its tie wraps, valve into the right with the strap over it, both
with their hoses and their wiring already fitted and long enough to reach the divider's glands.

**The base.** Now glue the two halves together at y 0 and the two mitten caps onto their flanks;
the belt flange's lower ring and the floor plate are already inside them, printed in. Then the
sand, and it is not a straight pour. `SAND_PLUG_XY` in `mech/torso.py` puts the hole at (−78, 0)
in the floor plate, 18 mm behind the belt joint's own bore (`BELT_IN_RX` 60), so nothing drops
onto it from above: reach in through the bore with a funnel and a length of hose snaked back and
down the 94 mm to the plate, or a rigid pipe held about 11° off vertical. Fill to `SAND_Z_TOP`,
well under the pump. Then the sand plug, which goes in the same way and is the last thing that
has to reach that corner: a Ø30 disc through the plate with a Ø38 lip that rests on the plate's
**top** face.

Then the bottle's cradle on top of the plate, the bottle in it neck to +Y, and the tank head
screwed on with its dip tube, float switch and vent. Push the filler hose onto the tank head's
barb now.

**The divider** goes on next, and the hose's far end has to be on the filler neck's barb
*before* it does - that barb hangs under the divider and there is no reaching it afterwards. PU
bead in its groove, glands through it, filler neck bonded into its hole, hose on, divider down.

**The belt.** The torso ring goes on with the two sleeve panels glued to it, and the four M3 × 20
belt screws pass down through the ring's flange and the divider into the base's inserts. The
chassis lands on the flange's four inserts, four M3 × 10.

**The phone sled and the electronics deck, before the cage.** Neither can be got past the deck
ring afterwards. Lift the sled straight up and it meets 2.40 cm³ of cage: the tie annulus
(r 54–62 at z 304–312) sits over its tray floor, and the top annulus (r 50–58 at z 386–394) sits
over the path of its two lock lugs. The 100 × 92 electronics deck meets 11.17 cm³ of the same two
rings. There is only 3.4 mm between the phone's top at 390.6 and the deck's underside at 394, so
nothing lifts a little and tilts out either. So: phone into the sled from above, camera end down,
screen to −X; sled down through the chassis's pocket and locked with its two screws; electronics
deck onto its three standoffs and two bare posts behind it.

**The neck and the drive.** The deck ring cage stands on the chassis, bolted up through it from
below - and it has to be worked down past the sled and the deck rather than dropped, because the
same 2.40 and 11.17 cm³ read the other way round: see the known limits. The deck is
assembled on the bench - pan servo up into its four hangers, fan under it, bearing's fixed ring
on top - and goes in **from above, through the bell's opening**, then four screws drive down into
the cage's inserts. Plate onto the bearing, shaft bonded into the plate, stop pins **glued** into
their Ø6.4 seats. The neck shroud goes on with four M3 × 10 into the plate: they are driven
downward from inside the cup, and the four Ø7 chimneys bored through its roof are how a long
driver gets onto their heads and out again. The crank, the link and the two pivot screws go on
**last, from below**.

**The head.** The tilt bracket hangs off the shroud's front on two M3 into its radial inserts at
±24°, with the micro servo in it and the nozzle arm on its horn; the brass nozzle presses into
the arm and the tube goes on its barb. Glue the beard, head and hat into one bell - it is one
piece from there on - and lower it over the shroud. Four **M3 × 30 countersunk** through the head
shell at z 440 into the shroud's radial inserts hold it: they are in the `head` section, not the
beard, and their heads sit flush in the skin at 60/120/240/300°.

## Service

- **The bell** comes off on four screws, countersunk into the **head** section at 60/120/240/300°
  and z 440 — above the mouth and below the nose, not down in the `beard` section, which is where
  this used to say they were. With the bell off the whole inside is visible from the top. Most of
  it is not yet reachable.
- **The phone is the worst job in the machine.** It comes out only after the bell, then the neck
  shroud (four M3 × 10 down the roof's chimneys), then the plate and the shaft off the bearing,
  then the deck (four screws into the cage), and then the cage itself (four screws up through the
  chassis) — because the cage's tie ring and top annulus stand over the sled and there are 3.4 mm
  between the phone's top and the deck. Only then do the sled's two screws come out and the sled
  lift. Recalibrate aim afterwards: the lens sits behind the ring's window and a millimetre of
  sled travel is a degree of aim.
- **Refilling** is the cap on the divider at (42, 54), reached with the bell off. Use a funnel:
  the phone's sled stands 8.8 mm from the cap's rim on the same divider, its tray floor 1 mm above
  the divider's face, and anything spilt at the cap runs straight at it. Wipe the divider before
  closing up. Filling is slow — the hose is 5 mm in the bore, so about 1 L/min falling to 0.6 as
  the bottle fills, call it a minute and a half for a litre. The float switch stops the pump.
- **The bottle** comes out only by opening the belt: four screws, and the whole upper shell lifts
  off the base. The tube and the loom have drip loops long enough to allow it.

## What the tests check

`test_params.py` (20) is arithmetic on `params.py` alone, so it runs without a build: the stack
adds up from the floor to the hat, the phone fits between the chassis and the deck, the window
sees where the camera needs to see, and the firmware fixture's soft limits sit inside the
mechanical hard stops.

`test_mech.py` (34) builds every build123d part and checks it is one valid solid inside the bed,
that the deck's cage stands inside the bell's bore and is cut around the pan servo, that the fan's
hole clears the bearing and the deck's rim, that the shaft's bore takes the tube and the wires,
that the linkage sweeps without touching anything and stays below the deck, that the phone drops
into the sled one way only, and that no two fixed parts share a millimetre. Three of them are
new: the shroud stands inside the statue's own cavity; **its four screws have a driver path** -
40 mm of driver down the roof's chimney onto each head, the radial insert bores are probed round
rather than square, and the stop pin's seat is probed with a pin 0.3 mm fat; and the electronics
deck's three standoffs are whole, 326.7 mm³ each, with none of them standing in the chassis's
bore for the filler cap.

`test_wet_and_head.py` (15) is the wet zone: the tank head's thread matches the bottle and its
ports pass its neck and the filler's bore, the threaded parts print standing up, the filler is
reachable from above and its hose reaches and clashes with nothing, **both ends of that hose are
barbs** - solid from the bore out to `HOSE_BARB_D` over the whole grip, nothing out there wider
than the ridges, bored through, and the route's two ends on the two mouths - the bottle sits in
its cradle and can still come out through the belt, the floor plate carries the sand and the two
leg ports, the brackets hang in the legs far enough apart that their cages cannot touch, and no
two wet parts overlap.

`test_fit.py` (3) is the statue's own contract: every placed part and every bought-part envelope
is inside `out/statue/cavity.stl`, and the trouser legs are where the brackets expect them.

`test_wall.py` (6) is the shell's: 25 000 points spread evenly over a void's surface, each
measured to the skin. The thinnest is at least the floor, next to none of the surface is under
0.4 mm below nominal, and the median is still nominal - the last so that buying a minimum by
fattening the whole offset, which would take the room out of the mechanism, fails here. Three
for `cavity.stl` against `WALL`, three for `cavity_grown.stl` against `WALL - 1.2`. What the
current build measures: minimum 2.13 mm and 0.89 mm, both medians still nominal, where before
the keep-out pass both minima were 0.00.

`test_shell.py` (94) needs `statue` and `assemble` to have run. Every section is watertight,
winding-consistent, **one body** and within the bed; no two of the ten share a millimetre;
every interface piece the assembler welded in is inside the section it went into; the window,
the intake, the mouth and the parting are open, and the parting is open at every tilt; the four
shroud screws have holes through the bell and bottom on their inserts' floors with the boss's
face beside each head — an assertion a shroud with no bosses at all used to pass; **the bell turns to
±65° without touching anything fixed**, its rim never dips under `Z_TURN` nor reaches outside the
panels below their tops; **the neck gap is the exhaust** - 62 of 72 directions out of it are
open, and the ten that are not are the sleeve panels; and **the jet leaves the statue at every
tilt** from −35° to +45°, in a `JET_D` envelope.

## Known limits

- **The face is a reconstruction, not a sculpture.** It reads as a gnome at any distance you
  would see it from, and as something soft and slightly uncanny in a close-up. The eyes are
  mush. Nothing in this repository can fix that but better photographs.
- **It is mirrored, so the moustache is symmetrical** in a way a carved one never is, and a
  hairline seam runs down the hat and the nose where the two halves met. A swipe of filler.
- **There is a 2 mm seam all round the beard, and the lathe takes more off it than one number
  says.** The bell has to turn inside the fixed panels, so it is turned down to r 103 between
  z 309 and 399. On the front meridian the skin reached r 105.8, so it loses **2.8 mm** — but the
  beard sweeps sideways over the chest, and there the skin stood out much further: r 107.3 at
  ±30° (4.3 mm off), **r 114.0 at ±40° (11.0 mm)**, **r 115.5 at ±50° (12.5 mm)** and r 112.7 at
  ±60° (9.7 mm). What is lost at the front is the tip of two locks; what is lost at ±40–50° is a
  centimetre of the beard's side, replaced by a cylindrical face. `PANEL_Y`'s comment in
  `params.py` used to quote the 2.3 mm alone and carries the whole table now.
- **The exhaust is that gap, and the air path is wrong.** The fan hangs under the deck and blows
  up through it; the air leaves through the bell's turning gap and the beard's parting. Two
  things follow from the numbers. First, **the intake and the exhaust are both at the back**: the
  intake is 40 × 20 = 800 mm² in the belt ring's back at z 262–282, the exhaust is the turning
  gap at z 307–309 — 661 mm of coat perimeter, 2 mm tall, 62 of 72 azimuths open, about
  1 100 mm² — and their centres are 36 mm apart. The short path from one to the other runs up the
  back of the coat, bypasses the phone at the front entirely, and re-ingests its own warm air.
  Second, **most of the fan's output recirculates**: it blows up through a 1 018 mm² hole into
  the bell, and the only way out of the bell is back down past the deck's rim, where the gap
  between the deck and the beard's inner skin is about **11 000 mm²** — eleven times the hole the
  air came up through, and far wider than the parting, so most of what the fan moves goes round
  in a circle inside the bell rather than out of the statue. The obvious remedy is to put
  the intake at the **front** of the ring, below the window, so the draught crosses the phone.
  Nothing in `params.py` sets the intake's azimuth: `VENT_IN_W`, `VENT_IN_H` and `Z_VENT_IN` give
  its size and height only, and `openings()` in `assemble.py` cuts it as a box out to −X. Moving
  it means a `VENT_IN_DEG` beside `Z_VENT_IN`. The geometry is deliberately left as it is here.
- **Nothing is filtered and nothing is sealed.** Rain that falls straight into the turning gap
  goes inside; the deck under it is solid but the phone is not far below. The four Ø7 access
  chimneys through the shroud's roof are the one hole that is sheltered: they are at z 454 and
  the highest opening anywhere in the bell above them is the countersunk screw holes at z 440,
  fourteen millimetres lower, with the head and hat a closed dome over the lot.
- **The tightest bought part is the bottle.** Its shoulder corners pass the coat's inner wall
  with **2.5 mm** at the back and a little more at the front (`BOTTLE_XY` sits it 2 mm forward
  of centre, the balance point); `BOTTLE_SHOULDER_IN` is what saves them, so a squarer 1 L
  bottle does not go in at all. Tighter still inside: the fan's hole in the deck clears the lazy
  susan's bolt circle by **1.0 mm**, and the plate's hanging column passes the pan servo by
  about a millimetre.
- **The bell is 573 g and turns on a 52 mm shroud.** Nothing in this repository has checked what
  that does to the pan servo's duty cycle or to the bearing over a season outdoors. It hangs on
  four M3 × 30 that cross 27 mm of open air between the bell's inner skin and the shroud's
  bosses, with about 2.7 mm of thread in each insert.
- **The cage, the phone sled and the electronics deck cannot be parted by a straight lift, in
  either order.** Vertical separability is symmetric, so the 2.40 cm³ that stops the sled coming
  up past the deck ring is the same 2.40 cm³ that stops the ring going down over the sled, and
  likewise the 11.17 cm³ for the electronics deck. Both are the cage's tie annulus (z 304–312)
  and its top annulus (z 386–394). The assembly order above puts the two boards in first because
  that is the way round with a hope of working — the cage is an open frame of four 12 mm legs and
  two thin rings, and it can be tilted and walked down over them, while the sled has to go
  straight down its pocket in the chassis. **Nothing in this repository proves a rigid motion
  that does it**, and no test asserts one. The honest fixes are to split the tie ring and glue it
  after, or to move the two rings' radii off the sled's and the deck's footprints.
- **Spilt water at the filler runs at the phone.** The cap is at (42, 54) on the divider and the
  sled's tray is 8.8 mm from its rim on the same flat face, with 1 mm of air under the tray. Fill
  with a funnel and wipe the divider. Nothing drains it.
- **The wall is measured now, and one thing about it is still untidy.** `WALL_MIN` is 1.6 mm and
  `keep_out` in `statue.py` holds the cavity to a measured 2.13 mm minimum and the grown cavity
  to 0.89; `test_wall.py`'s six tests are what keep it there. But **523 mm³ (0.0034 % of the
  cavity) of `cavity.stl` lies outside `cavity_grown.stl`**, mostly in two patches at the back of
  the head and over the face. That is the direction that costs nothing: `cavity_grown` is only
  the volume an interface part may reach into, so where it is the smaller of the two a part is
  clipped more conservatively than it had to be. It is not new and no part is near either patch.
- **`NECK_SECTION` is a hand-measured literal in `mech/turntable.py`.** Thirty-six radii of the
  coat's own section over the deck's band, which the deck is trimmed to. The plan was to read it
  out of `out/statue/features.json`, and the cleanup found that file cannot carry it: its `reach`
  rows keep five numbers each, the minimum and the four cardinals, and `statue.py`'s `reach()`
  throws the other sixty-eight directions away as it measures them. Rebuilt from what survives it
  is out by 35.6 mm from the minimum alone, or 22.1 and 17.3 mm interpolating the cardinals, and
  wrong in the dangerous direction — 84 mm at 150° where the coat's back corner is at 69.3. The
  literal itself was re-measured against the current mesh and is within **0.91 mm**, so it is
  right; it simply has nowhere better to live until the statue stage publishes a whole profile.
- **The lazy susan's eight bolts pass through clearance holes in the deck and the plate,** and
  what holds them — nuts, or self-tappers into the printed parts — is not modelled.

# The printed gnome

Every printed part of the deterrent, generated from one file of numbers. `params.py` is the
only place a dimension is written down; the mechanism is build123d, the shell is sculpted in
Blender, and the two meet in `assemble.py`, where manifold booleans let the interface parts
into the shell and cut the openings out of it. Nothing generated is committed.

The gnome stands 589 mm and prints as seven shell sections and twenty mechanism parts -
twenty-eight prints, since the stop pin is printed twice - none wider than the 256 mm bed.

## Build

```bash
uv venv --python 3.11 .venv-cad
uv pip install --python .venv-cad/bin/python -r cad/requirements.txt

.venv-cad/bin/python cad/build.py              # all four stages, about 29 s
.venv-cad/bin/pytest cad/tests -q              # 93 tests, about 36 s
```

Blender 5.2 is driven headless from `/Applications/Blender.app`; set `BLENDER` to point
somewhere else. It is the only thing not installed by pip, and it is used for nothing but the
sculpt and the previews.

| Stage | What it does | Time |
|---|---|---:|
| `mech` | build123d: every mechanism part to `out/step/` and `out/stl/`, in the frame it prints in, plus the placed `mechanism_assembly` in both formats | 5.2 s |
| `shell` | Blender: the five sculpted sections to `out/raw/` — revolved, textured, walled to a 2.4 mm shell | 4.1 s |
| `assemble` | trimesh + manifold3d: interface parts unioned in, openings and splits cut out, seven printable sections to `out/stl/` | 8.7 s |
| `preview` | Blender: 29 renders to `out/preview/` — the gnome, each section, the mechanism, and a cutaway | 10.7 s |

Stages can be named individually and run in any order, as long as `mech` and `shell` have run
before `assemble`. The tests that need built files skip themselves when there are none.

## Before printing anything that touches a bought part

These numbers are listing-typical guesses. Measure the part in your hand, change `params.py`,
rebuild, and only then print anything that has to fit it.

| Parameter | Measure |
|---|---|
| `BEARING_SQ`, `BEARING_T`, `BEARING_OPEN`, `BEARING_PITCH`, `BEARING_HOLE` | the lazy susan: plate size, thickness, the middle hole, the bolt pitch |
| `CANISTER`, `CAN_THREAD_MAJOR`, `CAN_THREAD_PITCH`, `CAN_THREAD_LEN`, `CAN_NECK_ID` | the canister lying down, and its neck thread. The tank head is the fit coupon — print it first, alone |
| `PUMP`, `PUMP_FEET` | the pump's body and the pitch of its rubber feet. **Height matters most:** it has 18 mm to the belt |
| `VALVE`, `VALVE_STRAP` | the solenoid's body, and how tall the strap has to arch |
| `DS3218`, `MG996R` | both servos as delivered: body, tab span, tab thickness, tab height, shaft offset, hole pitch |
| `HORN_D`, `HORN_T`, `HORN_SCREW_R` | the round horns in the servo's bag — the crank and the coupler are pocketed for them |
| `XL4015`, `XL4015_HOLES`, `XL4015_HOLE_D` | the buck converters' outline and mounting holes |
| `MOSFET`, `MOSFET_HOLES` | the MOSFET modules — the listing rarely gives the hole pitch |
| `ESP32` | the devkit's outline. It has no usable hole pattern, so it sits in a printed cradle with tie slots |
| `FAN`, `FAN_T`, `FAN_PITCH` | the 40 mm fan's frame and screw pitch |
| `LENS_CLIP_T`, `LENS_CLIP_W` | how far the clip-on lens stands off the phone's back glass, and how wide the clip is |
| `GLAND_D` | the M12 cable glands' thread |
| `NOZZLE_D` (`MOUTH_D` follows it) | the brass nozzle's shank, which the mouth is a bearing for |
| `FLOAT_HOLE_D`, `DIP_TUBE_D`, `FILLER_D`, `TUBE_OD` | the float switch, the dip tube, the filler and the PU tube |
| `PHONE_L`, `PHONE_W`, `PHONE_T`, `PHONE_CAM_FROM_END`, `PHONE_CAM_FROM_SIDE` | the phone, with its case off. The sled is the second fit coupon |
| `INSERT_D`, `INSERT_DEPTH`, `INSERT_M4_D`, `INSERT_M4_DEPTH` | the heat-set inserts you actually bought |

## What prints, and how it lies on the bed

Material is **PETG** throughout: PLA softens in a closed body in the sun, and ASA wants an
enclosure at these sizes. If you have one, the head, face and nozzle holder are the parts worth
printing in ASA — small, low warp risk, most sun-exposed. Four perimeters on anything the
mechanism screws into; the divider at 100 % infill.

Eleven parts never print on their own: `belt_flange_lower`, `belt_flange_upper`, `deck_ring`,
`hatch_lip`, `hatch_bosses`, `fan_frame`, `ear_boss`, `cradle_rails`, `head_lip`, `face_stop`
and `nozzle_bosses` are unioned into the shell section they belong to. Their STLs are written
anyway, because that is how the assembler eats them.

### Shell

| File | What it is | On the bed |
|---|---|---|
| `base` | Boots, the coat's hem and skirt, the raised floor with drain arches and stake holes; the belt flange's lower half inside its rim | As it stands, floor down |
| `torso` | Belly and coat, the window's frame, intake and exhaust; the belt flange's upper half, the deck ring, the hatch lip and bosses and the fan frame inside | As it stands, skirt down |
| `belly` | The coat's front between the belt and the shoulders: the camera window, the hood over it, the buttons, one mitten. Comes off on four screws | As it stands, outside up |
| `beard` | The collar: beard down the chest, a cape over the fan at the back, three screw bosses inside | Upside down — the hem is the flat face |
| `head_back` | The back of the head with the ear boss, the cradle rails and the face lip inside | On its cut face |
| `face` | The cap: nose, brows, cheeks, moustache, the mouth's bore; the nozzle bosses inside | On its cut face |
| `hat` | Brim and cone, leaning forward, with a spherical seat cut for the head | Brim down |

### Mechanism

| File | What it is | On the bed |
|---|---|---|
| `deck` | Carries the bearing, the pan servo hanging under it, and the pan stops | Flat, hangers up |
| `deck_ring` | The annulus the deck bolts to — *unioned into the torso* | — |
| `stop_pin` | Glued into the deck; the plate's tab runs into it. **Print two** | On end |
| `plate` | The head's foundation on the bearing; carries the shaft and the stop tab | Column up, with a support block under the foot bar |
| `shaft` | Hollow and passive: water and wires up through the turning neck | On end |
| `servo_crank` | On the pan servo's horn, pocketed from above | Flat |
| `pan_link` | Joins the plate's pin to the crank's pin | Flat |
| `yoke` | Ring on the plate with two arms: the coupler's hex on +Y, the M4 pin on −Y | Ring down |
| `neck_shroud` | Turns with the head; hides the yoke inside the collar | Base down |
| `coupler` | The +Y ear: horn inside, hex in the yoke's arm outside | Boss down |
| `tilt_cradle` | The tilt servo's plate, assembled on the bench and slid into the head | Upright |
| `divider` | The base's lid, sealed with a PU bead. **100 % infill, six perimeters** | Flat, with a brim |
| `chassis` | Bolts to the torso flange; carries the sled and the electronics deck | Flat |
| `phone_sled` | The phone drops in camera-down, screen to −X. Fits one way | Upright |
| `electronics_deck` | ESP32 cradle, two XL4015, three MOSFET modules, a fuse holder | Flat |
| `nozzle_holder` | Behind the mouth; the brass nozzle presses into its nose | On its +X face |
| `tank_head` | Screws onto the canister: dip tube, float switch, vent, filler stub | Mouth down |
| `tank_cradle` | Saddles for the lying canister and the two towers the pump stands on | Upright, as it stands |
| `filler_cap` | Retention thread; an O-ring in the groove seals | Open end down |
| `pump_plate` | The bridge over the canister: pump on grommets, valve beside it | Flat on its underside |
| `valve_strap` | A bar across the valve, pulled down by two long screws | Flat |

## Fasteners

M3 heat-set inserts everywhere a printed part is screwed into, M3 machine screws through.
Depths are what the geometry actually gives.

| Part | Feature | Count | Type |
|---|---|---|---|
| deck_ring | r 58, at 30/150/210/330, down from z 374 | 4 | M3 insert, 7 mm |
| deck | same r and angles, 3.4 through | 4 | M3 through 6 mm of deck into a 7 mm insert |
| deck | r 33.94, at 45/135/225/315, 3.4 through | 4 | the lazy susan's own bolts |
| deck | four hangers, up from z 348 | 4 | M3 insert, 6 mm — the pan servo's tabs |
| deck | two 6.1 × 6 blind seats at ±70.73°, r 60 | 2 | stop pins, glued |
| plate | r 33.94, at 45/135/225/315, 3.4 through | 4 | the lazy susan's own bolts |
| plate | r 46.7, at 45/135/225/315, down from z 391 | 4 | M3 insert, 4 mm — the yoke's ring |
| plate | pin boss, up from z 327.5 | 1 | M3 insert, 4.5 mm — the link's pivot |
| servo_crank | r 7, four positions, 2.8 through | 4 | M2.5 self-tapping into the pan horn |
| servo_crank | pin boss, up from z 327.5 | 1 | M3 insert, 4.5 mm — the link's pivot |
| pan_link | two 3.2 eyes | 2 | turn on the pivot screws' shanks |
| yoke + neck_shroud | r 46.7, 3.4 through both | 4 | **M3 × 10** into the plate — the shroud's base is under the yoke's ring, so these replace the yoke's own shorter screws |
| yoke | +Y arm, down from z 476 | 1 | M3 insert, 4 mm — the cross screw that locks the coupler |
| yoke | −Y arm, 4.2 through | 1 | M4 clearance. This hole is the tilt bearing |
| ear_boss | outer face, 5.6 × 8 | 1 | M4 insert, 8 mm — the tilt bolt threads into it |
| coupler | r 7 at 0 and 180°, 2.8 with 4.6 counterbores | 2 | M2.5 self-tapping into the tilt horn, driven from outside |
| coupler | 3.4 radial through the hex | 1 | the cross screw's tip lands here |
| tilt_cradle | four −Y bosses, opening at the +Y face | 4 | M3 insert, 6 mm — the tilt servo's tabs |
| belt_flange_lower | r 86, at 45/135/225/315, down from z 230 | 4 | M3 insert, 9 mm |
| belt_flange_upper | same, 3.4 through with a 3.5 mm counterbore | 4 | **M3 × 20** — the belt, through the divider into the lower flange |
| divider | same r and angles, 3.4 through | 4 | the same belt screws |
| belt_flange_upper | r 84, at 40/140/220/320, up from z 246 | 4 | M3 insert, 6 mm — the chassis |
| chassis | same r and angles, 3.4 through | 4 | M3 through 4 mm of chassis into a 6 mm insert |
| chassis | two lock bosses on the sled's line | 2 | M3 insert, 6 mm |
| phone_sled | two lugs, 3.4 with a 3.2 counterbore | 2 | M3 through 4 mm of lug into a 6 mm insert |
| chassis | three e-deck standoffs, up from z 238 | 3 | M3 insert, 6 mm |
| electronics_deck | three 3.4 through | 3 | M3 through 4 mm of deck into a 6 mm insert |
| electronics_deck | 8 × Ø3.2 (two XL4015), 12 × Ø3.4 (three MOSFET modules) | 20 | the modules' own screws |
| hatch_bosses | four brackets inside the opening, facing the panel | 4 | M3 insert, 6 mm |
| belly | four 3.4 through with a Ø6 countersink, 2 deep | 4 | **M3 countersunk** — 2.4 mm of panel into a 6 mm insert |
| fan_frame | four bosses round the exhaust | 4 | M3 insert, 6 mm — the fan's own screws |
| beard | three bosses inside at 90/210/330°, z 416 | 3 | M3 insert, 6 mm |
| torso | three 3.4 through the wall at the same places | 3 | **M3 × 12** from inside the torso: 2.4 mm of wall, 2 mm of air, 6 mm of insert |
| nozzle_bosses | two, on the face's inner wall | 2 | M3 insert, 6 mm |
| nozzle_holder | two 3.4 through with head pockets | 2 | M3 through 13 mm of holder into a 6 mm insert, driven from behind |
| tank_cradle | four towers | 4 | M3 insert, 6 mm |
| pump_plate | four 3.4 through, down into the towers | 4 | M3 through 4 mm of plate into a 6 mm insert |
| pump_plate | two strap bosses | 2 | M3 insert, 6 mm |
| valve_strap | two 3.4 through | 2 | M3 over the valve, 3 mm of bar and the strap's stand-off into a 6 mm insert |

**Totals.** 51 M3 inserts — 4 at 9 mm, 4 at 7 mm, 36 at 6 mm, 5 at 4 mm and 2 at 4.5 mm — one
M4 insert at 8 mm, and 51 M3 screws to fill them, of which four are the M3 × 20 belt screws and
four the countersunk ones in the belly. Add 8 M3 through the lazy susan's own holes, 20 small
screws for the modules' own feet, 6 M2.5 self-tappers for the two horns, one M4 × 20 tilt
bolt — 8 mm of yoke arm, a millimetre of gap, 8 mm of insert — and two glued 6 mm dowels. Buy
the inserts and the soldering tip before anything else: half the assembly below is inserts.

## Assembly

Heat every insert first, with the parts cold and on a flat surface. Then:

**Base, wet zone.** Tank cradle into the base; canister into the cradle, neck to −X; tank head
onto the canister with the dip tube, float switch and vent fitted; pump plate onto the cradle's
two towers; pump onto its grommets; valve beside it; valve strap over the valve; hose from the
filler stub to the filler neck in the back wall. Then the divider: PU bead in its groove, the
two glands through it, and leave the four belt screws out until the torso goes on.

**Neck and pan drive.** The deck is assembled outside the torso: pan servo up into its four
hangers, the bearing's fixed ring onto the deck's face. Then the deck goes into the torso from
below and the four screws come up into the deck ring. Plate onto the bearing, shaft bonded into
the plate, stop pins glued into the deck. Yoke ring and neck shroud together onto the plate —
one set of four M3 × 10. The crank, the link and the two pivot screws go on **last, from below**;
nothing above the deck has to come off to reach them.

**Head.** The tilt servo screws to the cradle on the bench, and the pair slides in through the
face opening along −X into the head's rails. Nozzle holder in behind the mouth, brass nozzle
pressed into its nose, tube on the barb. Face cap onto the lip and glued. The head then goes
into the yoke: M4 bolt through the −Y arm into the ear boss's insert, coupler in from outside
through the +Y wall onto the servo's horn, two M2.5 down the counterbores, and the cross screw
through the yoke's arm to lock the hex. Hat glued on its seat last.

**Dry zone.** Chassis onto the torso flange; electronics deck onto its three standoffs; sled
with the phone in it slid home and locked with its two screws; belly panel on four countersunk
screws. The collar is last: three M3 from inside the torso into its bosses.

## Service

- **The phone** comes out through the belly: four countersunk screws, lift the panel, slide the
  sled forward. Nothing else moves and nothing needs draining. Recalibrate aim afterwards — the
  lens sits against the window's pane and a millimetre of sled travel is a degree of aim.
- **The tank** fills through the cap at the back of the base. The float switch stops the pump.
- **The upper half** lifts off on the four belt screws, which is how you reach the pump, the
  valve and the divider's glands. The tube and the loom have drip loops long enough to allow it.
- **The head** comes off the yoke with one M4 bolt and the coupler's cross screw.

## What the tests check

`test_params.py` (21) is arithmetic on `params.py` alone, so it runs without a build: the stack
adds up from the floor to the hat, the phone fits between the chassis and the deck, the window
sees where the camera needs to see, the hat's brim clears the yoke's arms and the collar at both
tilt stops, and the firmware fixture's soft limits sit inside the mechanical hard stops.

`test_mech.py` (40) builds every build123d part and checks it is one valid solid inside the bed,
that the phone drops into the sled one way only, that the shaft passes the deck and the linkage
stays under it, that the pan servo misses the bearing and the tilt servo fits the head, and that
no two fixed parts share a millimetre.

`test_wet_and_head.py` (18) is the wet zone and the nozzle: the holder's bore is on the mouth's
axis and the nozzle is held at both ends, the tube reaches the shaft in one bend, the tank head's
thread matches the canister and its ports pass the neck, and the canister, pump and valve stand
on the floor under the belt.

`test_shell.py` (14) needs `assemble` to have run. Every section is watertight, winding-consistent
and within the bed; the canister, pump, valve and phone volumes are empty of shell; window,
mouth, exhaust, intake, filler and the head's underside are open to the outside; every interface
part was taken into its section; the belly panel and the torso re-unite into one solid with
nothing lost; the head nods to both stops and pans to both stops without touching the collar,
the torso or the shroud; and the hat seats on the head rather than hovering over it.

## Known limits

- **The face is relief, not sculpture.** Brows, nose, cheeks and moustache are analytic domes
  and ridges on the sphere. It reads as a face at arm's length and as a lump in a close-up.
- **The boots are weak.** The raised floor's rim forces the wall out to r 111 at the ankles, so
  the boots can only stand 3–4 mm proud of the profile; what shows them is the well cut around
  them, not their own height.
- **There is an 8 mm open ring** between the neck shroud's rim and the head. Rain that falls
  straight down the collar goes into the torso. The fan blows out, which helps, and the deck
  under it is solid, but it is not sealed.
- **`base.stl` is 25 MB and half a million triangles.** It slices, but slowly. The lever is
  `VOXEL` in `shell/body.py`, not the assembler.
- **The nozzle's line of fire clears the collar's rim by 13 mm** at zero tilt — the mouth is at
  z 456 and the rim at 443, and a horizontal jet meets nothing. Aim below horizontal and it
  will. The aiming envelope has to stay above the rim.
- **The pump's height is the tightest bought dimension.** 65 mm in `params.py` leaves 18 mm to
  the belt; a taller pump fouls the divider before anything else complains.
- `NUT_M3_AF` and `NUT_M3_T` are in `params.py` and nothing uses them: the lazy susan's eight
  bolts pass through clearance holes in the deck and the plate, and what holds them — nuts, or
  self-tappers into the printed parts — is not modelled.

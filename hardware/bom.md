# Bill of materials — AliExpress and 3D-printed build

Strategy: buy the parts that must be engineered, print everything structural on the P1P.
Prices checked 2026-09-21. AliExpress figures are the range seen in live listings that day;
Swiss figures come from fetched product pages. Anything unverified is marked, not guessed.

**Already owned:** iPhone 6s, ESP32 WROOM-32 devkit, Bambu Lab P1P.

**Three rules that decide what gets bought:**

1. **Anything at 4 bar is bought.** FDM layer bonding is roughly 50–70% of in-plane strength,
   and the weak plane sits exactly at threads and port bosses. Printed parts that merely weep
   at zero pressure will spray at 4 bar. Pump, valve, fittings, tubing: bought.
2. **The tank is bought.** Even unpressurised, layer lines and the Z-seam weep over days.
   A bought bottle in a printed cradle removes the one failure that drips onto the ESP32.
3. **The mains supply is bought locally, from a known brand.** It is 230V, outdoors,
   unattended, all season. Cheap CE marks are frequently self-declared.

---

## A. AliExpress cart

| Item | Search term | CHF | The trap to check |
|---|---|---:|---|
| Pan servo ×1 | `DS3218MG 180 degree servo` | 11–17 | The **180° vs 270°** SKU dropdown — same listing sells both, and the pulse-to-angle mapping differs. Wrong one silently breaks calibration |
| Tilt servo ×1 | `MG92B micro servo metal gear` | 4–9 | **The head no longer nods** — the CAD tilts only the nozzle arm, a few grams on a 20 mm lever inside the beard — so this is a micro servo, 22.8 × 12.4 × 28.5 mm, and the whole tilt mechanism hides behind the beard's parting. `MG92B` in `params.py` is its body, tabs and shaft offset: measure yours. Same fake-gear check applies |
| Diaphragm pump | `12V micro diaphragm pump 1L/min 7 bar self-priming` | 10–20 | Must state **bar or PSI**. Flow-only specs (L/h) mean an aquarium pump that cannot build pressure. It stands in the gnome's **left trouser leg**, hanging under the floor plate, so it has to fit about **45 × 40 × 95 mm** (`PUMP` in `params.py`) and its feet pitch (`PUMP_FEET`) has to match its bracket. A big 4 L/min pump with a pressure-switch housing will not go in |
| Solenoid valve, 1/4" NC | `12V direct acting solenoid valve 1/4 NC 0-0.8MPa` | 5–9 | Pressure range must **start at 0**. "0.02–0.8MPa" is pilot-operated: tens of ms slower to open and prone to dribble after closing, which wrecks a 300ms burst |
| Jet nozzle | `brass single jet fountain nozzle` or `nozzle orifice disc set 0.5-3mm` | 3–8 | Reject anything titled mist/fog/atomizing. Searching "brass nozzle 1mm" returns 3D-printer hotends; fountain nozzles are the right category |
| Float switch | `mini side mount float switch 12V` | 3–8 | Many are rated **AC only**. Confirm a DC rating; side-mount needs less vertical room, and this tank is only 71 mm deep |
| Buck converters ×2 | `XL4015 5A DC-DC adjustable step down` | 2–6 | Not LM2596: 3A absolute max, ~2A real, and widely counterfeited. One XL4015 at 6V for servos, one at 5V for logic |
| MOSFET modules ×3 | `AOD4184 MOSFET switch module 3.3V` | 3–8 | **Not IRF520**, even when the listing says "3.3V compatible". Its Rds(on) is only specified at Vgs=10V; at 3.3V it half-conducts and cooks at 5A |
| DS18B20 probe ×2 | `DS18B20 waterproof temperature probe` | 4–10 | Buy two. A clone reports exactly **85.0°C** forever — the power-on default it never updates |
| M3 heat-set inserts + tip | `M3 heat set threaded insert soldering tip` | 5–12 | The tip shank must match your iron (T12/900M/C245), which is the mistake people actually make |
| Wire, heatshrink, JST, 40mm fan | `22AWG silicone wire kit`, `40mm 5V fan` | 10–20 | JST pitch (2.0 PH vs 2.54 XH) must match what you're mating |
| Resistors: 10k ×5, 4.7k ×1 | `1/4W metal film resistor kit` | 2–5 | Four 10k hold the MOSFET gates down through boot, one pulls the float switch up on GPIO 34 (input-only, no internal pull-up), one 4.7k is the 1-Wire bus pull-up. Without the gate resistors **the valve opens every time the board reboots** |
| Flyback diodes ×2 | `1N5819 Schottky` or `1N4007` | 1–3 | Across the solenoid and the pump, cathode to +12 V. Both are inductive; switching one off without a path for the collapsing field fails the MOSFET **on**, leaving a valve stuck open |
| Electrolytic 1000 µF 25 V ×1 | `1000uF 25V low ESR capacitor` | 1–3 | Pump inrush sags the 12 V rail far enough to reset the ESP32 in the middle of timing a 300 ms burst |
| Fuse 5 A + inline holder | `5A automotive blade fuse holder` | 2–4 | A shorted pump has a 5 A supply behind it and 22 AWG in front of it |
| Tubing + fittings | `PU tubing 6mm 8bar`, `G1/4 BSP barbed fitting` | 10–20 | Tubing must state bar/MPa. Confirm **BSP (G), parallel** — AliExpress brass is often NPT and will weep |
| Clip-on 0.6x lens | `0.6x wide angle clip-on phone lens` | 3–8 | Check the clip doesn't vignette the 6s main camera |
| Thrust / lazy-susan bearing | `60mm lazy susan bearing` | 3–7 | Or print a BB race — see part list below |
| **Cart total** | | **~75–160** | |

**Swiss VAT, corrected:** the threshold is ~CHF 62 of goods value, where 8.1% VAT reaches the
CHF 5 minimum below which Switzerland doesn't collect. The CHF 150 figure is the EU's
customs threshold, a different country and a different tax. Since 2019 AliExpress charges
Swiss VAT at checkout under the mail-order rule, so **splitting orders saves nothing** and
only multiplies your chance of a CHF 11–16 per-parcel handling fee. Consolidate.

Pay for faster shipping on the servos, pump and valve — those are the parts whose being wrong
or dead on arrival costs you another month. Wire and heatshrink can crawl.

## B. Bought locally

| Item | Pick | CHF | Where |
|---|---|---:|---|
| 12V 5A supply | Sealed IP65/IP67 12V adapter with a Swiss plug, or Mean Well LRS-75-12 in the box below | 15–35 | [conrad.ch](https://www.conrad.ch/de/p/mean-well-lrs-75-12-ac-dc-netzteilbaustein-geschlossen-6-a-72-w-12-v-dc-1439450.html) (CHF ~14.95) or a sealed adapter to avoid wiring mains yourself |
| IP65 box for the supply | AP-Abzweigdose, 105×105×46mm | 5.90 | [obi.ch](https://www.obi.ch/aufputzschalterprogramme/ap-abzweigdose-ip65-hxbxt-105-x-105-x-46-mm/p/4015228) |
| Camera window | Acrylglasscheibe 100×50×3mm, cut to size | 1.15 | [conrad.ch](https://www.conrad.ch/de/p/acrylglasscheibe-l-x-b-100-mm-x-50-mm-materialstaerke-3-mm-transparent-1-st-530646.html) |
| Water tank | **1 L rectangular HDPE lab bottle**, opaque, at most 195 mm long, with a tapered shoulder | 5–15 | Any lab supplier / Landi. It lies on its wide face in the belly: 97 × 195 × 71 mm is what the CAD assumes, and its **rear top corners pass the coat's wall with 0.1 mm**, so the shoulder's taper is what lets it in. A squarer bottle of the same litre does not fit. No canister any more |
| Sealant | Polyurethane (Sikaflex-type), paintable and UV-stable | ~12 | OBI / Jumbo |
| Insect mesh | Fibreglass or stainless window screen | ~14 | [obi.ch](https://www.obi.ch/insektenschutznetze/obi-insektenschutznetz-fenster-weiss-150-x-130-cm/p/5021506) |
| Paint system | 400–600 grit, IPA, plastic adhesion promoter, opaque light topcoat | ~35 | Any DIY chain — see weatherproofing below |
| **Subtotal** | | **~90–130** | |

## C. Printed parts

The parts themselves are generated by `cad/build.py`: **ten shell sections and 25 mechanism
parts, 33 prints in all**, about 1.8 kg of shell and 1.1 kg of mechanism. `cad/README.md` is the
authority — it lists every piece with its size, weight and bed orientation, what to measure
before printing it, and what every screw and insert is for. The table below is only the material
advice; the shell itself is a 3D scan of a real garden gnome, so its split lines are where the
machine needs them rather than where a modeller would put them.

**Material: PETG, light or mid tone, for the whole shell.** Not PLA — its glass transition is
55–60°C and a closed body in sun reaches that, so screw bosses loosen and spans sag within a
season. ASA resists UV about ten times better than ABS and is what the TaubenTurret project
(an outdoor pan/tilt water deterrent, the closest published precedent to this build) chose for
direct sun — but both Prusa and Bambu flag ASA as enclosure-preferred, and 55cm sections on an
open frame are exactly where warping bites. If you build the enclosure, print the **head and
nozzle assembly in ASA** (small, low warp risk, most sun-exposed) and keep the big body
sections in PETG.

**Colour is a real trade-off.** Dark pigment absorbs UV and protects the polymer — that's why
outdoor HDPE pipe is black. But a dark closed body runs much hotter inside, and Apple rates
the iPhone for 0–35°C ambient, above which it throttles, stops charging and eventually
refuses to run. Electronics failure beats cosmetic yellowing, so go **light-coloured**, vent
it properly, and accept repainting every couple of seasons.

| Part | Material | Notes |
|---|---|---|
| Base halves, mitten caps, belt ring, sleeve panels | PETG, 0.6mm nozzle, 0.3mm layers | The fixed shell, 2.4 mm walls. The two base halves are the big prints: 219 × 164 × 240 mm and about 450 g each |
| The bell — beard, head, hat | PETG, or ASA if you have an enclosure | Glued into one piece and screwed to the neck shroud; it turns as a unit, 573 g of it. The face is the one part where detail shows, and it carries the mouth and the nozzle's parting |
| Neck / pan turntable | PETG, 4+ perimeters | Bought lazy susan carries the bell; the servo drives a **hollow** shaft through its centre, and water plus wiring pass up inside it. Printed BB race is the fallback, with **glass or stainless** balls, never raw steel |
| Servo brackets, horn adapters | PETG | Put a metal screw or pin through the horn joint — printed splines strip under torque |
| Deck cage, deck, plate, shroud | PETG, 4+ perimeters | Everything the drive screws into. The cage prints legs down and needs no support |
| Nozzle holder | PETG or ASA | Rigid in the mouth, aimed along the head's axis. The wetted orifice is the bought brass nozzle, pressed in. Heat-set inserts, never printed threads, near the water path |
| Wet/dry divider | PETG, 4–6 perimeters, **100% infill** | A normal sparse panel is porous. Seal to the shell with a polyurethane bead |
| Internal decks, phone cradle | PETG | Cradle geometry is easy; the phone's heat problem is solved by venting and shade, not by the cradle |
| Vent grille frames | PETG | 3–6mm openings with bonded-in insect mesh — a 0.4mm nozzle can't print real mesh. Louvres sloped down, tucked under the hat brim |
| Filler neck and cap | PETG | On the divider, reached from the top with the bell off. Threads for retention only; an O-ring does the sealing |
| Tank cradle | PETG | Holds the bought bottle. Do not print the tank |

**Budget:** ~2kg of filament (range 1.5–3kg), roughly 40–50 hours of machine time, CHF 30–85
in filament. Using a 0.6mm nozzle for the body roughly halves the shell time — two 0.6mm
perimeters (~1.3mm) match three 0.4mm ones structurally, and nobody inspects layer lines on a
garden ornament from three metres. Slice a real STL before trusting these numbers.

**Joining sections:** the slicer's cut tool with **dowel** connectors, plus two-part epoxy —
acetone welding does **not** work on PETG, only on ASA/ABS. Shingle horizontal seams so the
upper section overlaps outside the lower one; a flat outward-facing ledge collects water and
freeze-thaws through the winter. Use heat-set inserts and screws anywhere you'll reopen.

**Models worth starting from:**

- [Garden Gnome, magiczztab](https://www.thingiverse.com/thing:626907) — **CC BY-SA**, so
  modification is allowed. A 3D scan of a ~60cm statue; solid, needs hollowing.
- [Tactical Garden Gnome, MakerWorld](https://makerworld.com/en/models/2898276) — already
  split and pre-scaled to 45cm, with the designer's own warning about base stability at
  scale, which is directly relevant to a rotating head.
- [TaubenTurret, MakerWorld](https://makerworld.com/en/models/2801562) — **CC BY-NC-SA.**
  Not a gnome, but it is this exact machine: outdoor pan/tilt servos, camera, relay-fired
  water jet, hollow multi-part housing, real bearings, full assembly guide, ASA for sun.
  Worth reading before designing anything.
- Avoid [thing:6949434](https://www.thingiverse.com/thing:6949434): CC BY-**ND** forbids the
  modification this needs.

**Weatherproofing, as a system rather than a rattle-can:** sand 400–600, wipe with IPA, apply
a plastic adhesion promoter (PETG and ASA both have low surface energy and ordinary paint
peels), then an opaque UV-stabilised topcoat. Light colours with TiO2 protect best and run
coolest. This genuinely slows polymer degradation rather than just looking nicer, but it is a
wear item — expect to recoat every couple of seasons.

---

## Totals

| | CHF |
|---|---:|
| AliExpress cart | 75–160 |
| Bought locally | 90–130 |
| Filament | 30–85 |
| **Total** | **~195–375** |

Against roughly CHF 460 for the bought-body version, and the printed shell is better suited:
mounts where they're needed, vents where the heat is, a gasketed refill hatch, and a camera
window positioned for the lens instead of cut into whatever the statue happened to offer.

## Open risks

See also `docs/superpowers/specs/2026-09-21-mechanical-design.md`, which defines what the
printed parts have to achieve.


- **The iPhone's 0–35°C ambient rating is the tightest thermal constraint in the build**, and
  it sits inside a closed body in the sun. Light colour, cross-ventilation behind the belly
  window, shade placement and the ESP32-driven fan all serve this. Measure it in M4 before
  trusting a summer.
- PETG will yellow and surface-chalk over years. Structural life is fine for several
  spring-to-autumn seasons with winter storage.
- The nozzle is the least certain purchase: matching a 1–1.5mm coherent-jet orifice from a
  listing photo is unreliable. Buy two or three candidates; they're a few francs each.
- Print-time and filament figures are planning-grade until a real STL is sliced.

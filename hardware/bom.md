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
| Nod servo ×1 | `MG996R metal gear servo 180` | 5–10 | **The head nods now** — beard, head and hat together, about 0.55 kg, −15° to +5° about a pin in the neck — on the firmware's tilt channel. An MG996R-class metal-gear standard servo, about 1.0 N·m at 6 V: gravity needs 0.10 N·m nose-down, wind 0.55 N·m at 15 m/s and 0.97 at 20, where it stalls onto the printed stops. `MG996R` and `SPLINE_BOSS` in `params.py` are its case, tabs, shaft offset and the height of its spline boss: **measure yours** — its case face is 7 mm inside the cage's legs and its spline passes a 14 mm hole. Same fake-gear check as the pan servo; use the **round horn** from its bag, it is screwed into the stem's hub |
| Nod pin + bushing | `4mm steel dowel pin 14mm` or an M4 shoulder bolt; `4x6x6 bronze sleeve bushing` | 2–4 | A Ø4 × 14 dowel pressed into the stem's hub and held by an **M2 set screw** on a flat you file on it; it turns in one Ø4 × Ø6 × 6 bushing pressed into the −Y cheek. The servo's own output bearing is the other side |
| Diaphragm pump | `12V micro diaphragm pump 1L/min 7 bar self-priming` | 10–20 | Must state **bar or PSI**. Flow-only specs (L/h) mean an aquarium pump that cannot build pressure. It stands in the gnome's **left trouser leg**, hanging under the floor plate, so it has to fit about **45 × 40 × 95 mm** (`PUMP` in `params.py`) and its feet pitch (`PUMP_FEET`) has to match its bracket. A big 4 L/min pump with a pressure-switch housing will not go in |
| Solenoid valve, 1/4" NC | `12V direct acting solenoid valve 1/4 NC 0-0.8MPa` | 5–9 | Pressure range must **start at 0**. "0.02–0.8MPa" is pilot-operated: tens of ms slower to open and prone to dribble after closing, which wrecks a 300ms burst |
| Jet nozzle | `brass jet nozzle M8 1mm orifice` or `nozzle orifice disc set 0.5-3mm` | 3–8 | **Short: Ø8 × 10 at most** (`NOZZLE_D`, `NOZZLE_L`). It is fixed in the mouth, pressed into a holder printed with the head, and its back cannot come nearer the neck than x 73.5 — the head keeps 100 mm from the neck's centre there — so a 25 mm fountain nozzle does not fit. Reject anything titled mist/fog/atomizing. Searching "brass nozzle 1mm" returns 3D-printer hotends |
| O-ring for the head's water joint | `NBR O-ring 5x1.5` | 1 | The tube stands up out of the spider and the head's socket slides down over it as the head goes on; this O-ring in the socket's groove is the seal. The water pushes the tube 20 N down at 7 bar; the spider's clamp screw holds it |
| Float switch | `mini side mount float switch 12V` | 3–8 | Many are rated **AC only**. Confirm a DC rating; side-mount needs less vertical room, and this tank is only 71 mm deep |
| Buck converters ×2 | `XL4015 5A DC-DC adjustable step down` | 2–6 | Not LM2596: 3A absolute max, ~2A real, and widely counterfeited. One XL4015 at 6V for servos, one at 5V for logic |
| MOSFET modules ×3 | `AOD4184 MOSFET switch module 3.3V` | 3–8 | **Not IRF520**, even when the listing says "3.3V compatible". Its Rds(on) is only specified at Vgs=10V; at 3.3V it half-conducts and cooks at 5A |
| DS18B20 probe ×2 | `DS18B20 waterproof temperature probe` | 4–10 | Buy two. A clone reports exactly **85.0°C** forever — the power-on default it never updates |
| M3 heat-set inserts + tip | `M3 heat set threaded insert soldering tip` | 5–12 | **69 of them** — 52 at 6 mm, 4 at 9, 4 at 7, 7 at 4 and 2 at 4.5 — see `cad/README.md`'s fastener table for the depths (the short ones are blind in thin parts, so a 6 mm insert will not do). Buy 100. The tip shank must match your iron (T12/900M/C245), which is the mistake people actually make |
| M3 screw kit | `M3 stainless socket cap screw assortment` + `M3 countersunk hex 8/10/12/30mm` | 6–12 | 69 M3 screws fill those inserts: **4 × M3 × 20** (the belt), **4 × M3 × 30 countersunk** (the head onto the spider — 27 mm from the skin to the boss), **2 × M3 × 16, 2 × M3 × 14, 2 × M3 × 12 countersunk** (the collar and the beard's tongues), **5 × M3 × 8 and 2 × M3 × 10 countersunk** (the bearing's cap, the collar's back pair, the hub ring), **2 × M3 × 12** (the spider onto the stem), and the rest socket heads 8–14 mm. Plus 8 M2.5 self-tappers for the two servo horns and one M2 × 4 grub for the nod pin. `cad/README.md` has every one |
| M12 cable glands ×2 | `M12 IP68 cable gland nylon` | 2–4 | Two, through the divider at (−40, ±30) — `GLAND_D` is 12.5, the thread with clearance. They are the only wiring path from the dry side to the pump, the valve and the float switch, and they are what keeps the wet zone a wet zone |
| Silicone hose, 8 mm OD | `8x5mm food grade silicone hose` | 2–5 | **0.3 m is twice what is needed** — the run is about 155 mm, 134 of route plus 10 over each barb, from the filler port on the coat's back down through the belt joint to the tank head. 8 mm is the widest that fits: where it rises beside the tank head's stub the belt ring's bore leaves 8.9. It must take a 5 mm bend at the fittings (`HOSE_BEND_R`): silicone will, plain PVC of this bore will not |
| O-ring for the filler cap | `NBR O-ring 15x2mm` | 1–3 | The cap has a real groove — 14.8 mm ID, 19.2 OD, 2.2 wide, 1.5 deep — so about **15 × 2 mm cord**. The thread is retention only; this is the seal |
| Wire, heatshrink, JST, 30mm fan | `22AWG silicone wire kit`, `30mm 5V fan 3010` | 10–20 | JST pitch (2.0 PH vs 2.54 XH) must match what you're mating. The fan is **30 mm**, not 40: it hangs under the deck's back and the collar has to go down past it |
| Resistors: 10k ×5, 4.7k ×1 | `1/4W metal film resistor kit` | 2–5 | Four 10k hold the MOSFET gates down through boot, one pulls the float switch up on GPIO 34 (input-only, no internal pull-up), one 4.7k is the 1-Wire bus pull-up. Without the gate resistors **the valve opens every time the board reboots** |
| Flyback diodes ×2 | `1N5819 Schottky` or `1N4007` | 1–3 | Across the solenoid and the pump, cathode to +12 V. Both are inductive; switching one off without a path for the collapsing field fails the MOSFET **on**, leaving a valve stuck open |
| Electrolytic 1000 µF 25 V ×1 | `1000uF 25V low ESR capacitor` | 1–3 | Pump inrush sags the 12 V rail far enough to reset the ESP32 in the middle of timing a 300 ms burst |
| Fuse 5 A + inline holder | `5A automotive blade fuse holder` | 2–4 | A shorted pump has a 5 A supply behind it and 22 AWG in front of it |
| Tubing + fittings | `PU tubing 6mm 8bar`, `G1/4 BSP barbed fitting` | 10–20 | Tubing must state bar/MPa. Confirm **BSP (G), parallel** — AliExpress brass is often NPT and will weep |
| Clip-on 0.6x lens | `0.6x wide angle clip-on phone lens` | 3–8 | Check the clip doesn't vignette the 6s main camera |
| Pan bearing | `6810-2RS bearing` (stainless `S6810-2RS` if you can get it) | 4–12 | A sealed thin-section deep-groove ball bearing, **50 bore × 65 OD × 7**. It replaced the lazy susan: the nod drive reaches the neck's pivot down through its 50 mm bore. Outer ring in the deck, inner ring on the plate's hub, both with 0.15 mm of printed fit and clamped face to face; measure it before printing the deck, the cap, the plate and the hub ring |
| **Cart total** | | **~85–185** | |

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
| Water tank | **1 L rectangular HDPE lab bottle**, opaque, at most 195 mm long, with a tapered shoulder | 5–15 | Any lab supplier / Landi. It lies on its wide face in the belly: 97 × 195 × 71 mm is what the CAD assumes, and its **shoulder corners pass the coat's wall with about 2.5 mm**, so the shoulder's taper is what lets it in. A squarer bottle of the same litre does not fit. No canister any more |
| Sealant | Polyurethane (Sikaflex-type), paintable and UV-stable | ~12 | OBI / Jumbo |
| Insect mesh *(optional)* | Fibreglass or stainless window screen | ~14 | **No printed part carries mesh.** The camera window and the intake are plain rectangular cuts in the belt ring, and the exhaust is the dome's bore and the 2 mm seam under the head. If you want the openings screened you are bonding mesh over a flat cut yourself |
| Paint system | 400–600 grit, IPA, plastic adhesion promoter, opaque light topcoat | ~35 | Any DIY chain — see weatherproofing below |
| **Subtotal** | | **~90–130** | |

## C. Printed parts

The parts themselves are generated by `cad/build.py`: **twelve shell pieces and 28 mechanism parts, 35 prints in all**, about 1.9 kg of shell and 0.9 kg of mechanism, about 1.8 kg of shell and 1.1 kg of mechanism. `cad/README.md` is the
authority — it lists every piece with its size, weight and bed orientation, what to measure
before printing it, and what every screw and insert is for. The table below is only the material
advice; the shell itself is an image-to-3D reconstruction of a real garden gnome, so its split
lines are where the machine needs them rather than where a modeller would put them.

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
| Base halves, mitten caps, belt ring, collar, sleeve panels | PETG, 0.6mm nozzle, 0.3mm layers | The fixed shell, 2.4 mm walls. The two base halves are the big prints: 219 × 164 × 240 mm and about 450 g each |
| The turning unit — beard halves, head, hat | PETG, or ASA if you have an enclosure | The head and hat glued into one; the beard in **two halves**, each screwed to the head (the whole unit has no straight way onto the collar). It pans and nods on the spider, about 0.5 kg. The face carries the mouth and, printed with it, the nozzle's holder |
| The collar | PETG | The socket the head turns in: fitted after the mechanism, four radial countersunk M3 through the ring's top edge into its tabs, so it comes off for service |
| Neck / pan turntable | PETG, 4+ perimeters | A bought 6810-2RS carries the plate; the plate's hub and yoke hang down through its bore to the nod pin, and the tube runs down inside the stem |
| Servo brackets, horn adapters | PETG | Put a metal screw or pin through the horn joint — printed splines strip under torque |
| Deck cage, deck, bearing cap, hub ring, plate, stem, spider | PETG, 4+ perimeters | Everything the drive screws into. The cage prints **foot ring down, legs up, no support**. The plate carries the hub, both cheeks and the nod servo's posts in one print, disc down. The stem prints **on its side**; the spider hub down |
| Wet/dry divider | PETG, 4–6 perimeters, **100% infill** | A normal sparse panel is porous. Seal to the shell with a polyurethane bead |
| Internal decks, phone cradle | PETG | Cradle geometry is easy; the phone's heat problem is solved by venting and shade, not by the cradle |
| Filler port and cap | PETG | **On the coat's back**, printed into the belt ring: unscrew the cap and pour, nothing taken off. Threads for retention only; a 15 × 2 mm O-ring in the cap's groove does the sealing. The neck's underside is a Ø6.5 barb the filler hose pushes onto |
| Tank cradle | PETG | Holds the bought bottle. Do not print the tank |
| Stop pins ×2 | PETG | **Printed, not bought** — two Ø6 × 16 pins, `stop_pin` in the CAD. They **glue** into Ø6.4 seats in the deck; a press fit into a tenth of clearance split the deck |

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
| AliExpress cart | 85–185 |
| Bought locally | 90–130 |
| Filament | 30–85 |
| **Total** | **~205–400** |

Against roughly CHF 460 for the bought-body version, and the printed shell is better suited:
mounts where they're needed, vents where the heat is, a gasketed filler on the outside of the
coat's back — there is no hatch any more — and a camera window positioned for the lens instead of
cut into whatever the statue happened to offer.

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

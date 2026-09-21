# Bill of materials — Swiss sourcing

Prices in CHF including VAT, checked 2026-09-21. Every price below comes from a fetched
product page; anything that could not be verified is marked **unverified** rather than
guessed. Stock changes, so treat these as a starting point, not a quote.

**Buying strategy:** Swiss shops for the pump, valve, power supply and anything bulky or
safety-relevant; AliExpress for commodity electronics where the Swiss markup is 3x or more.
Allow 2–4 weeks for the AliExpress half and order it first.

**Already owned, not in the totals:** iPhone 6s, ESP32 WROOM-32 devkit (classic ESP32 has
BLE, which is all this needs).

---

## 1. Servos and head mechanics

| Item | Pick | CHF | Where | Notes |
|---|---:|---|---|---|
| Pan servo | DS3218 PRO, metal gear, dual ball bearing | 19.90 | [planet-rc.ch](https://planet-rc.ch/ds-servo-ds3218-pro-high-speed-23-5kg-0-1sec6-8v-en/) | **Backordered, ~4 weeks.** Order first |
| Pan servo, fallback | MG996R | 24.90 | galaxus.ch | Price unverified (bot-blocked). See accuracy note below |
| Pan servo, cheap fallback | MG996R | 14.90 | [bastelgarage.ch](https://www.bastelgarage.ch/high-torque-servo-mg996r-10kg-cm-1-324) | Out of stock |
| Tilt servo | TowerPro MG90S, metal gear | 7.90 | [bastelgarage.ch](https://www.bastelgarage.ch/towerpro-micro-servo-mg90s-with-metal-gear) | Out of stock; ~CHF 2–3 on AliExpress |
| Servo extension cable | AWG26, 300mm | 1.40 | [bastelgarage.ch](https://www.bastelgarage.ch/servokabel-servo-verlangerungskabel-awg26-300mm) | In stock |
| Aluminium servo horn | RUDDOG offset horn 25T | 10.90 | [planet-rc.ch](https://planet-rc.ch/rp-0088-aluminium-offset-servo-horn-25t-rot-en/) | In stock. **Spline fit to DS3218 unconfirmed** — the horn in the servo box may serve |
| Thrust / lazy-susan bearing 60–80mm | — | ~3–7 | AliExpress | Not stocked by any Swiss hobby or hardware shop checked |

**Why not just use the cheap MG996R.** Its deadband looks comparable on paper, but under this
load pattern — swing, hold, swing back — a budget unit realistically shows 1–3° of backlash,
which is **10–30cm of error at 6m**. The DS3218 PRO's 3µs deadband works out to 2.7–4.1cm at
the same distance, with confirmed dual ball bearings. Since the design aims at a cat's head
beyond 4m, and a cat's head is about 10cm, the cheaper servo would turn aimed shots into
sprayed guesses. The DS3218 costs CHF 5–14 more.

---

## 2. Water path

| Item | Pick | CHF | Where | Notes |
|---|---:|---|---|---|
| Pump | Seaflo 12V diaphragm, 4.3 l/min, 5.5 bar cut-off, built-in pressure switch | 32.90 | [swiss16.ch](https://swiss16.ch/p/seaflo-wasserpumpe-dc-12v-membranpumpe-pumpe-druckpumpe-fuer-wohnmobil-boot-garten) | In stock, 3–5 days |
| Solenoid valve | 12V NC, DN15 (1/2"), direct-acting, 0.2–8 bar | 12.90 | [bastelgarage.ch](https://www.bastelgarage.ch/12v-magnetventil-dn15-1-2-zoll) | In stock. Needs a 1/2"→1/4" BSP reducer |
| Solenoid valve, alternative | 12V NC, 1/4" | 33.49 | [campinggoods.shop](https://campinggoods.shop/camping-shop/wasser-sanitaer-campingtoilette/absperrhaehne-wasser/16230/magnetventil-12-v-1/4-innengewinde) | Right thread, but pressure rating not stated — confirm before buying |
| Jet nozzle, 1–1.5mm | — | ~2–5 | AliExpress | **Not sold in Switzerland in the right pattern.** Buy a *jet/stream* nozzle, not a mist/cone one — this part sets the 6m throw |
| Float switch | mini PP float switch, 12V-rated | ~1–3 | AliExpress | The only Swiss listing found is an industrial unit at CHF 67.50 — skip it |
| Tank, 3L opaque | food canister or fuel-gel canister | ~5–15 | Landi / supermarket | Nothing found matching 3L *and* a 20–25cm base; a repurposed canister is fine if opaque |
| Tubing 6–8mm, 4 bar | PU or reinforced PVC | ~3–6 | AliExpress | Gardena Micro-Drip is stocked locally but is drip-irrigation rated, not confirmed for 4 bar |
| Hose clamps, barbed fittings, thread adapters | assorted | ~10 | AliExpress / Jumbo | See thread warning below |
| PTFE tape | 12mm × 12m | 1.60 | [Landi](https://www.landi.ch/shop/sanitaer-verbrauchsmaterial_170502/teflon-gewindedichtband_112509) | In stock in branches today |

**Thread standards will bite.** Swiss and EU parts are BSP (parallel G-thread); AliExpress
brass fittings are frequently NPT (tapered). They look alike and will cross-thread or weep.
Decide per part, keep BSP↔NPT adapters on hand, and use the PTFE tape.

**Two shortcuts that were checked and rejected:**

- *A 12V windscreen-washer pump instead of the diaphragm pump.* Those are centrifugal, not
  positive-displacement. Realistic flowing pressure is 0.3–0.7 bar against the 4 bar this
  design assumes, and jet throw scales with √ΔP, so the 6m target becomes about **2.1m**.
  They also cannot hold a pressurised standing line at idle, which destroys the clean 300ms
  pulse the whole aiming model depends on.
- *Buying a ready-made 12V sprayer and stripping it.* The cheapest motorised option found is
  a Birchmeier Accu Star 8 at CHF 138.85 (Hornbach), running about 3 bar — two to four times
  the individual part cost, below the target pressure, and it contains no solenoid valve,
  float switch or jet nozzle anyway.

---

## 3. Electronics

| Item | Pick | CHF | Where |
|---|---|---:|---|
| Temperature probe | DS18B20, 1m, waterproof, shielded | 9.90 | [bastelgarage.ch](https://www.bastelgarage.ch/1m-temperatursensor-wasserdicht-ds18b20-geschirmt) |
| Resistors (incl. the 4.7k pull-up) | 600-piece assortment, 1/4W 1% | 9.90 | [bastelgarage.ch](https://www.bastelgarage.ch/widerstand-set-600-stk-assortiert-1-4w-1-genauigkeit) |
| MOSFET for the pump | DFRobot Gravity MOSFET driver, 10A | 6.90 | [bastelgarage.ch](https://www.bastelgarage.ch/gravity-mosfet-treiber-modul-10a) |
| MOSFETs for valve + fan (2×) | IRLZ44NPBF discrete | 2.72 | [distrelec.ch](https://www.distrelec.ch/mosfet-kanal-55v-47a-to-220-infineon-irlz44npbf/p/30341412) |
| Flyback diodes (30) | Diotec 1N5408 | 2.70 | [conrad.ch](https://www.conrad.ch/de/diotec-si-gleichrichterdiode-1n5408-do-201-1000-v-3-a-162434.html) |
| Buck 12V→6V, 5A (servo rail) | DFRobot DFR0946 buck-boost | 14.90 | [bastelgarage.ch](https://www.bastelgarage.ch/5a-dc-dc-buck-boost-converter-module) |
| Buck 12V→5V, 3A | MP1584 module | 2.90 | [bastelgarage.ch](https://www.bastelgarage.ch/mp1584-3a-switching-regulator-dc-dc-step-down-converter) |
| 12V supply | Mean Well LRS-75-12 (12V, 6A) | ~14.95 | [conrad.ch](https://www.conrad.ch/de/p/mean-well-lrs-75-12-ac-dc-netzteilbaustein-geschlossen-6-a-72-w-12-v-dc-1439450.html) |
| Inline fuse holder | IWH automotive blade type | 2.55 | [conrad.ch](https://www.conrad.ch/de/p/iwh-kfz-sicherungshalter-1-st-2730166.html) |
| Perfboard | 90×70mm prototype PCB | 3.90 | [bastelgarage.ch](https://www.bastelgarage.ch/90x70mm-prototype-pcb-board) |
| Screw terminals (4×) | 2P PCB screw terminal | 2.80 | [bastelgarage.ch](https://www.bastelgarage.ch/2p-printklemme-mit-schraubanschluss) |
| Heatshrink | 328-piece assortment | 17.90 | [bastelgarage.ch](https://www.bastelgarage.ch/schrumpfschlauch-set-diverse-farben-328-stuck) |
| Phone USB power switch | 1-channel relay module, 3.3V trigger | 5.50 | [bastelgarage.ch](https://www.bastelgarage.ch/1-kanal-relais-modul) |
| Silicone hookup wire | 22AWG multi-colour kit | ~9 | AliExpress — no Swiss shop checked stocks silicone-jacketed wire |
| 40mm 5V fan | generic axial | ~3 | AliExpress (Sunon at Distrelec is CHF 10.79 if you want it now) |

**Do not use an IRF520 module for the pump**, despite the "3.3V–5V compatible" wording on the
common Keyes board sold at Play-Zone for CHF 5.90. The IRF520's gate threshold is 2–4V and it
needs about 10V to reach its rated on-resistance; at 3.3V it only partially turns on and will
run hot at 5A. The Gravity module above states 3.3V logic explicitly, which is why it's the
pick for the one switch that carries the pump.

The relay for the phone's USB 5V is a mechanical SPDT. That's fine here — the charger toggles
a few times a day at the 40/80% thresholds, not thousands of times — and it switches only the
+5V line, leaving ground and the data pins alone. A true P-MOSFET high-side switch is
AliExpress-only among the shops checked.

Counterfeit DS18B20 chips are a known AliExpress problem and the saving is about a franc, so
that one is worth buying locally.

---

## Totals and ordering

| Section | Swiss | AliExpress |
|---|---:|---:|
| Servos and head mechanics | ~40 | ~5 (bearing) |
| Water path | ~47 | ~30 (nozzle, float switch, tubing, fittings, tank) |
| Electronics | ~98 | ~12 (silicone wire, fan) |
| Enclosure (Lechuza body) | ~210 | ~15 (clip-on lens) |
| **Total** | **~395** | **~62** |

Roughly **CHF 460 all in**, plus CHF 15–25 of Swiss shipping across three or four shops.

**Trim list, if that's too much:** the 3M Dual Lock (CHF 33.95) and the IP55 extension cord
(CHF 39.95) are the two soft items — velcro straps and a cord you already own cover both.
That alone takes about CHF 60 off.

**Order in this sequence, because two items gate everything else:**

1. **Today:** the DS3218 from planet-rc.ch — it's a ~4 week backorder and it's on the critical
   path for any aiming work.
2. **Today:** the AliExpress batch (nozzle, float switch, tubing, fittings, bearing, silicone
   wire, fan, clip lens) — 2–4 weeks in transit.
3. **Before ordering the body:** phone Lechuza or Brack about UV stability, and shopparen
   (052 366 12 39) about wall thickness, if you want the classic gnome look.
4. **Whenever:** the Swiss electronics, pump and valve. All in stock, 1–3 days.

Bench work can start as soon as the ESP32, the buck converters, one MOSFET module and the
pump arrive — the servos aren't needed until the aiming step.

**Still unverified, flagged rather than guessed:** the MG996R price at Galaxus (bot-blocked),
the 1/4" valve's pressure rating at campinggoods.shop, Gardena Micro-Drip tubing pricing and
its 4-bar suitability, whether the shopparen gnomes are hollow, and whether the Lechuza figure
is UV-stable.

## 4. Enclosure and weatherproofing

### The body — the item that decides whether this design works

A hollow garden figure of 50cm or more is a specialist size; most decorative gnomes are
20–30cm. Two real options were found.

| Option | CHF | Where | State |
|---|---:|---|---|
| **Lechuza × Playmobil "Glücksgartenzwerg Felix"**, ~65cm tall, 31×20cm, jointed figure | 65.00 | [brack.ch](https://www.brack.ch/lechuza-gluecksgartenzwerg-mehrfarbig-1695813) | **In stock.** Hollow by construction, and **its head already rotates on a built-in neck joint** |
| shopparen.ch classic gnomes, 67–91cm, Kunststein | 199–239 | [shopparen.ch](https://shopparen.ch/produkt-kategorie/gartenzwerge/) | Every one of six checked is **backorder**, freight-shipped, lead time unpublished. Hollowness *inferred*, never stated |
| Second-hand XXL gnome | ~71 | ricardo.ch / tutti.ch | Listings churn; one Breitenbach pickup listing seen but unverifiable |

**The Playmobil figure is the better starting point**, and not only on price: the factory neck
joint is the pan axis this design has to build otherwise, and a CHF 65 mistake is cheaper to
absorb than a CHF 239 one.

**Two questions to settle before ordering, neither answerable from a product page:**

1. **Is it UV-stable outdoors?** Sources conflict. Brack's own spec sheet says
   "Winterhart: Nein" (not winter-hardy), which fits a spring-to-autumn deployment. But one
   retailer describes it as not UV-resistant and indoor-only, while Lechuza's own copy says
   indoor *and* outdoor. Months of full sun could fade or embrittle it. Ask Lechuza directly,
   or budget for a UV clearcoat.
2. **For the shopparen gnomes: hollow, and can the shell be cut?** Not stated anywhere,
   including on the shop's own manufacturing page. Polyresin figures this size are
   near-universally hollow-cast — consistent with the freight-shipping note — but that is
   inference. Their number is 052 366 12 39.

### Everything else

| Item | Pick | CHF | Where |
|---|---|---:|---|
| Camera window | Acrylglasscheibe 100×50mm, 3mm, cut down to ~40×40 | 1.15 | [conrad.ch](https://www.conrad.ch/de/p/acrylglasscheibe-l-x-b-100-mm-x-50-mm-materialstaerke-3-mm-transparent-1-st-530646.html) |
| Cable glands | Quadrios PG7–PG16 assortment, 50 pcs | 14.95 | [conrad.ch](https://www.conrad.ch/de/p/quadrios-24ca388-kabelverschraubung-pg7-pg9-pg11-pg13-5-pg16-polyamid-schwarz-50-st-3362061.html) |
| IP65 box for the 12V supply | AP-Abzweigdose IP65, 105×105×46mm | 5.90 | [obi.ch](https://www.obi.ch/aufputzschalterprogramme/ap-abzweigdose-ip65-hxbxt-105-x-105-x-46-mm/p/4015228) |
| Window gasket / sealing | Sanitär-Silikon transparent, 310ml | 3.95 | [obi.ch](https://www.obi.ch/silikon-acryl/obi-sanitaer-silikon-transparent-310-ml/p/3123684) |
| Outdoor extension cord | Max Hauri H07RN-F 3G1.5, IP55, 5m | 39.95 | [obi.ch](https://www.obi.ch/verlaengerungskabel/max-hauri-gdv-verlaengerung-h07rn-f3g1-5-ip55-schwarz-laenge-5-m/p/6105688) |
| Insect mesh for vents | Insektenschutznetz 150×130cm | 13.95 | [obi.ch](https://www.obi.ch/insektenschutznetze/obi-insektenschutznetz-fenster-weiss-150-x-130-cm/p/5021506) |
| Internal decks | Sperrholz Pappel 4mm | 9.75 | [obi.ch](https://www.obi.ch/regalboeden-moebelbauplatten/sperrholz-pappel-4-mm/p/2084861) |
| Wet-zone divider | Guttagliss Hobbycolor PVC foam board 50×50cm | 6.95 | [obi.ch](https://www.obi.ch/kunststoffbedachung/kunststoffplatte-guttagliss-hobbycolor-weiss-50-x-50-cm/p/3483369) |
| M3 standoffs and screws | Whadda WCS400 assortment | 14.95 | [conrad.ch](https://www.conrad.ch/de/p/whadda-wcs400-wcs400-abstandsbolzen-set-l-200-mm-nylon-vernickelt-1-set-2481989.html) |
| Phone mount | 3M Dual Lock, 2.5m × 25mm | 33.95 | [conrad.ch](https://www.conrad.ch/de/p/3m-dual-lock-klettband-zum-aufkleben-l-x-b-2-5-m-x-25-mm-schwarz-1-st-2144904.html) |
| Clip-on wide lens, ~0.6x | **Not stocked** by the Swiss retailers checked | ~10–20 | AliExpress, or Ulanzi/Sandmarc at digitec for CHF 30–60 |

True ABS sheet is not sold by the Swiss DIY chains; the PVC foam board above is fine for
non-structural internal decks. OBI items are walk-in; Conrad ships next day.

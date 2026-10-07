# Mumbai surge-pricing simulation

This project is an educational simulation of an Uber/Ola-style platform in Mumbai.
It asks a simple question:

> During a busy period, should the platform raise prices to bring drivers toward a
> high-demand area, even if that makes some riders stop booking?

The repository contains two connected models:

1. A **synthetic Mumbai data generator** that creates a month of ride activity.
2. A **two-zone economic game** that turns part of that data into a pricing and
   driver-allocation experiment.

It is not real Uber, Ola, or Mumbai data, and it is not a production pricing
system. It is designed to make the trade-offs behind surge pricing visible.

## Quick start

From the repository root:

```bash
uv run python data/simulate_data.py
uv run surge-pricing
```

The first command regenerates the synthetic data. The second calibrates the game
from that data, prints the comparison table, and writes the four-panel figure to
`src/surge_pricing/results.png`.

Run the test suite with:

```bash
uv run pytest
```

## The Mumbai being simulated

The data generator divides Mumbai into six simplified zones. They are familiar
place labels, not exact geographic boundaries or real ride-hailing service areas.

| Zone | Behaviour in the simulation |
| --- | --- |
| BKC | A high-demand office/commute hub, especially on weekday mornings and evenings. |
| Bandra | A nightlife zone, with stronger late-evening and weekend demand. |
| CSMIA Airport | Airport-related trips with morning and evening peaks and longer rides. |
| Lower Parel | Another office/commute area. |
| Powai | A residential zone with commuting demand. |
| Borivali | A lower-demand residential comparison zone. |

For every hour in a 28-day period, the generator considers:

- weekday versus weekend;
- the zone's demand pattern;
- a random demand shock;
- rain, which raises demand by 25%; and
- the share of the driver fleet that is online at that time of day.

The generated trip data uses kilometres and Indian rupees. It contains completed
trips only, with fields such as `ride_platform`, `pickup_zone_id`, `trip_km`,
`rider_fare_inr`, and `driver_pay_inr`.

`data/zone_hours.csv` is the more informative file. It includes simulated
information that a typical trip log would not show: all riders arriving, requests,
drivers active, completed trips, and unmet requests for every zone-hour.

## How the synthetic data is created

The generator is `data/simulate_data.py`.

### Demand

Each zone starts with a baseline rider count. A time-of-day profile changes that
count. For example, BKC gets a strong weekday evening peak, while Bandra gets a
late-night peak. Rain and random variation are applied afterward.

### Drivers

At the busiest hours, the simulated fleet has up to 260 active drivers across all
six zones. Fewer are online overnight. Drivers are distributed based on expected
demand, but with an exponent below one (`demand ** 0.8`), so they do not fully
follow the busiest area. That deliberate mismatch creates shortages and makes
surge possible.

### Surge in the generated data

The data generator uses a simple shortage rule:

```text
shortage = demand at normal price / driver capacity - 1
surge    = 1 + 0.6 × shortage + small random noise
```

Surge is clipped between `1.0×` and `1.8×` and rounded to steps of `0.05×`.
Higher demand relative to nearby driver capacity means higher surge.

### Riders, matching, and fares

The generator assumes riders have different willingness to pay. When surge goes
up, some choose not to request a ride. Riders who do request are matched to
available drivers probabilistically: a zone with more drivers per request has a
higher completion rate.

Synthetic fares are in rupees and use a base charge, a per-kilometre charge, and
a time charge. Airport rides are generally longer. A platform commission is drawn
around 25%, and the remaining fare is driver pay.

## How the two-zone pricing game is chosen

The game does not try to solve all six Mumbai zones at once. It creates one clear
comparison between a busy and a quiet area.

`src/surge_pricing/calibration.py` reads the generated files and uses only:

```text
Weekdays, 17:00 through 19:59
```

Within that window it:

1. calculates the average rider arrivals and active drivers in every zone;
2. chooses the zone with the most arriving riders as the **hot zone**;
3. chooses the zone with the fewest arriving riders as the **calm zone**;
4. sums active drivers in those two zones; and
5. estimates the platform's commission from total rider fares and driver pay.

With the default, seeded data, this selects **BKC as the hot zone** and
**Borivali as the calm zone**. The exact averages are printed each time the model
runs. If you change the seed, demand profiles, date range, or calibration window,
the selected zones can change.

## The economic model

The game itself is intentionally smaller than the data generator: two zones,
one period, one platform, riders, and drivers.

### Platform decision: surge prices

The platform chooses a surge multiplier in each zone. `1.0×` is the base fare;
`1.3×` means a 30% higher fare.

The program tries every pair on this grid:

```text
1.00×, 1.05×, 1.10×, ..., 3.00×
```

It can choose prices to maximize either platform revenue or total modeled welfare.
This is called a **Stackelberg game**: the platform chooses first, anticipating
how drivers will respond.

### Rider behaviour and the rider limit

The core model uses normalized money units, rather than literal rupees. Its base
fare is `1.0` and the maximum willingness to pay is `2.0` base-fare units.

The model assumes willingness to pay is uniformly distributed from zero to that
maximum. Therefore the share of arriving riders who request a trip is:

```text
max(0, 1 - fare / maximum willingness to pay)
```

Examples in this model:

| Surge | Fare | Share of arriving riders who request |
| --- | --- | --- |
| 1.0× | 1.0 | 50% |
| 1.3× | 1.3 | 35% |
| 1.8× | 1.8 | 10% |
| 2.0× or more | 2.0 or more | 0% |

This is a deliberately simple demand curve. It captures the idea that a rider may
decide a heavily surged ride is not worth it, but it does not represent real
individual trips, public transport alternatives, cancellations, or different rider
income levels.

### Completed rides

Each driver can serve `1.0` trip per model period. If there are many drivers,
more requested trips are completed. The matching rule is:

```text
completed trips = requests × (1 - exp(-driver capacity / requests))
```

It has useful behaviour:

- when driver capacity is small, many riders fail to match;
- adding drivers helps, but each extra driver helps less than the prior one;
- completed trips never exceed requested trips.

### What drivers want

Drivers want the greatest expected earnings per driver, not merely the highest
fare. Their expected pay is:

```text
(1 - platform commission) × surged fare × completed trips / drivers in that zone
```

A high BKC surge can initially make BKC attractive. But if too many drivers move
there, they must share the same pool of trips, reducing pay per driver. Meanwhile,
Borivali becomes less crowded and its drivers can earn more easily.

The equilibrium is the allocation where neither side gives a driver a reason to
switch:

```text
expected BKC driver earnings ≈ expected Borivali driver earnings
```

`equilibrium.py` finds that point with bisection: it repeatedly tests a possible
number of BKC drivers and moves the estimate until the pay gap is nearly zero.

### What the model measures

For each price pair, `evaluate()` calculates:

| Output | Meaning |
| --- | --- |
| `trips` | Completed rides in both zones combined. |
| `unmet_share_hot` | Fraction of BKC requests that do not get a driver. |
| `platform_revenue` | Platform commission across completed rides. |
| `rider_surplus` | Modelled value riders receive above the fare they paid. |
| `driver_income` | The share of completed-trip fare paid to drivers. |
| `welfare` | Rider surplus + driver income + platform revenue. |

The monetary results in the game output are **normalized model units**, not rupees.
The Mumbai data sets relative demand, driver availability, and commission; it does
not yet convert the game payoff table into actual ₹ estimates.

## Two ways drivers adjust

### Instant equilibrium

For every candidate price pair, the Stackelberg calculation assumes drivers can
immediately settle at the earnings-equalizing allocation. This is used for the
flat-price, maximum-revenue, and maximum-welfare rows.

### Dynamic adjustment

`dynamics.py` instead simulates 400 periods. In each period:

1. drivers observe which zone paid more last period;
2. some drivers shift toward that zone;
3. the platform nudges each zone's surge toward a demand-to-capacity ratio rule;
4. the next period begins.

The program runs both slow and fast driver-adjustment settings. The `Ratio rule
(end of run)` row reports the last state of the slow simulation. Unlike the
instant-equilibrium rows, it can temporarily have unequal driver earnings because
drivers are still adjusting.

## Reading the terminal output

The first line tells you the calibration chosen from the data, for example:

```text
hot=BKC, calm=Borivali; arrivals=(...), drivers=(...), commission=0.250
```

Then the comparison table has four scenarios:

| Row | What it means |
| --- | --- |
| Flat price | Both zones stay at `1.0×`. |
| Stackelberg: max revenue | Price pair that gives the platform the greatest commission revenue. |
| Stackelberg: max welfare | Price pair with the greatest combined modeled welfare. |
| Ratio rule (end of run) | Where the gradual driver/surge simulation ends after 400 periods. |

Read across a row. For example, if maximum revenue has a higher `platform` value
but a lower `riders` and lower `welfare` value than flat price, that says surge is
good for platform revenue but harmful to the broader modeled outcome.

`driver pay` is the expected pay for one driver in the hot zone. At the instant
equilibrium rows, hot and calm driver pay are equal by construction; the terminal
prints the hot-zone value only and then explicitly prints both values for the
revenue-maximising outcome.

## Reading `results.png`

The saved Matplotlib figure has four panels.

### Top-left: driver allocation

This holds the calm-zone surge at `1.0×` and increases only hot-zone surge.
It shows how BKC drivers and Borivali drivers change. A moderate BKC surge can
pull drivers toward BKC. At a very high surge, riders stop requesting, so BKC can
become unattractive again.

### Top-right: gains and losses

This also varies only hot-zone surge. It plots:

- platform revenue;
- rider surplus;
- driver income; and
- total welfare.

Do not treat the highest line as automatically "best." It is a trade-off chart.
For instance, a price can increase commission revenue while decreasing rider
surplus and welfare.

### Bottom-left: platform revenue heat map

This tries every hot-zone and calm-zone surge pair. The horizontal axis is hot-zone
surge; the vertical axis is calm-zone surge. Brighter colours mean higher platform
revenue. The red star marks the best revenue pair found on the price grid.

### Bottom-right: gradual driver movement

This plots the number of drivers in BKC over 400 periods. The slow line moves in
small steps. The fast line reacts much more quickly. A line that becomes flat has
settled near a stable allocation.

## Recommended code-reading order

Read one file at a time and run the program after each stage. The aim is to follow
one question through the code: *who wants a ride, who drives where, and what does
the platform earn?*

1. `data/simulate_data.py` — Where does Mumbai demand, rain, driver supply, and
   rupee trip data come from?
2. `src/surge_pricing/calibration.py` — How are BKC and Borivali selected from
   those six zones?
3. `src/surge_pricing/market.py` — What does a fare do to rider demand, completed
   trips, and driver earnings?
4. `src/surge_pricing/equilibrium.py` — How are drivers split until neither zone
   pays better?
5. `src/surge_pricing/stackelberg.py` — How does the platform try all price pairs?
6. `src/surge_pricing/dynamics.py` — What changes when drivers move gradually?
7. `src/surge_pricing/run.py` — How are all scenarios run and printed?
8. `src/surge_pricing/plots.py` — How does each result become one of the four
   panels?
9. `tests/test_model.py` — What facts does the project verify about the model?

Useful questions to ask while reading each function:

```text
Is this creating demand?
Is this deciding whether a rider requests?
Is this deciding whether a request is completed?
Is this calculating a driver's expected pay?
Is this moving drivers between zones?
Is this choosing a platform price?
Or is this only displaying the outcome?
```

## Important limitations

- The data is fabricated and illustrative, not measured Mumbai ride-hailing data.
- Zones are broad labels, not geographic shapes or road-network travel times.
- Drivers can move between the two game zones without travel delay or fuel cost.
- All drivers are treated as identical.
- Riders are represented with a simple willingness-to-pay distribution.
- The model does not include public transport, cancellations, traffic congestion,
  driver costs, regulation, incentives, or safety constraints.
- The game reports normalized payoff units even though the generated trip records
  use rupees.

Those simplifications are intentional: they keep the main surge-pricing trade-off
easy to inspect in code.

# Building-aware EMF physics (twin/physics)

Plain summary: the antenna field no longer passes through buildings. Two engines share one API
(`twin/physics/api.py`), and both give Monte Carlo P5 / P50 / P95 and exceedance probabilities.

| Engine | What it models | Where it runs | When it is used |
|---|---|---|---|
| Sionna RT ray tracing | reflections, diffraction, diffuse scattering on the LoD1 city mesh (ITU materials) | Modal GPU (L4, scales to zero), about 3-10 s per 600 m district; or locally on CPU, about 25 s | when the site has been traced (`scripts/raytrace_site.py`) |
| CPU building-aware | 3GPP sector pattern, Deygout rooftop diffraction (ITU-R P.526) on LiDAR heights, diffuse multipath floor | anywhere, about 0.1 s per 441-point grid | every other site |
| Free space (old) | isotropic, no buildings: a worst case | kept in twin/scenarios | comparison only |

Indoor receptors (points inside a footprint) get building entry loss from ITU-R P.2109-2
(traditional masonry, about 15 dB median at 1.8 GHz). Every parameter lives in `config/physics.yaml`
with its basis.

## What is sampled in the Monte Carlo

* building heights: `height_m + height_sd_m * N(0, 1)` per building (CPU engine; ray tracing uses the mean heights);
* EIRP: log-normal, 1.5 dB for a declared value;
* unknown sector directions: uniform; unknown downtilt: uniform 2-10 degrees (CPU), 6 degrees (ray tracing);
* entry loss: the P.2109 distribution;
* model error: 3 dB with a clear line of sight, 7 dB when obstructed (CPU), 4 dB (ray tracing).

## The diffuse multipath floor (CPU engine)

Knife-edge diffraction alone ignores facade reflections, so deep street canyons would come out
60-80 dB below free space. The engine adds, in power, a diffuse component at free space minus
`multipath.diffuse_loss_db` = 35 dB. Basis: COST 231 Walfisch-Ikegami excess loss for Rome-like
geometry (f = 1840 MHz, d = 0.3 km, street width w = 20 m, building spacing b = 40 m,
roofs 22 m, mast 30 m, receiver 1.5 m):

* L_rts = -8.2 - 10 log w + 10 log f + 20 log(h_roof - h_m) = -8.2 - 13.0 + 32.6 + 22.6 = 34 dB (L_ori about 0 at 30-55 degrees);
* L_msd = L_bsh + k_a + k_d log d + k_f log f - 9 log b = -17.2 + 54 - 9.4 - 10.8 - 14.4 = 2 dB.

Excess over free space is about 36 dB, rounded to 35 dB (C=55).

## Check against ray tracing

At the test site (12.4823, 41.8960, 30 m, 1800 MHz, unknown azimuth), outdoor street-level points:
ray tracing minus CPU engine, median +1.5 dB, interquartile range -4.5 to +7.8 dB. Ray tracing
versus free space: median -22 dB. So the CPU engine agrees with ray tracing on average, and ray
tracing is preferred where it has run.

## Antenna register v2

See `docs/register_refit.md`: fitting tri-sector patterns, directions and LiDAR mast heights to the
Cartoradio grid cut the error on held-out cells from 9.2 dB (v1) to 7.2 dB. Directions are
*estimated* from the shape of the official field, not declared.

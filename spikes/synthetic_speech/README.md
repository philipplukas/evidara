# Synthetic Speech Dynamics

A mathematically controlled laboratory for a structural framework for speech:

```
q  ->  theta_{q->r}  ->  F_t  ->  u(t)  ->  Phi  ->  S(t) + eps,   eps ~ N(0, Sigma)
```

Every generative parameter is known, so every recovery error can be measured — and, more
usefully, so can the difference between what is *recoverable* and what is merely *assumed*.

This is a research spike, not a speech synthesiser. It lives under `spikes/` because it is
exploratory work with no product surface, no CI gate, and no dependency on the rest of the
monorepo; nothing here is imported by `platform-control`, `legal-search` or
`document-intelligence`.

## Run it

```bash
cd spikes/synthetic_speech
uv venv --python 3.12 && uv pip install -e ".[dev]"
uv pip install torch --index-url https://download.pytorch.org/whl/cpu   # optional, for the GRU baseline

bash run_all.sh --quick    # smoke run, a few minutes
bash run_all.sh            # full corpora
```

Results land in `results/`: one PDF (and PNG) per figure, one JSON per experiment, and
`results/SYNTHETIC_SPEECH_REPORT.md` aggregating all of it.

Everything is deterministic given `--seed`. Individual experiments run standalone
(`uv run python experiments/03_kernel_recovery.py`), and `build_report.py` rebuilds the
report from whatever JSON is present, marking anything missing rather than omitting it.

## Layout

| Path | What it is |
|---|---|
| `config.py` | every ground-truth parameter, and the named experimental conditions |
| `dynamics.py` | `M u'' + C u' + K(u - theta) = 0`, propagated by matrix exponential |
| `acoustics.py` | `Phi` and its analytic Jacobian, verified against finite differences |
| `noise.py` | spatial covariance regimes and AR(1) temporal correlation |
| `generator.py` | sequences, speakers (group and groupoid), datasets, the identifiability twin |
| `analysis/` | the inference side — **never imports a generator module** (enforced by a test) |
| `experiments/` | one script per experiment, each writing a figure + JSON |
| `tests/` | 80+ tests pinning the generator's exactness and the oracle discipline |

`analysis/` carries two modules beyond the four the specification names — `kernels.py`
(parametric kernel families) and `recognizers.py` (the three recognisers) — both split out
so that `svd.py` and `system_id.py` stay readable.

## Oracle discipline

The rule is: *never use latent ground truth in an inference experiment unless the
experiment is explicitly labelled oracle.* It is enforced mechanically, not by convention
(`tests/test_oracle_discipline.py`):

1. Nothing in `analysis/` may import `config`, `dynamics`, `acoustics`, `noise` or
   `generator`. An estimator that can reach `DEFAULT_ALPHA` will eventually reach it.
   Where an estimator legitimately needs `Phi` or `DPhi`, the **caller** supplies it, so
   the oracle boundary is visible at the call site.
2. Every line in `experiments/` that reads a ground-truth attribute of a `Dataset` must
   carry one of two markers:
   - `# GT` — the value is used for *scoring* or *reporting* (required: the spec asks
     every experiment to print its ground truth);
   - `# ORACLE` — the value is fed *into* an estimator.

   Both show up in a diff. The observable surface is `observed`, `source`, `speaker`,
   `sequence_index`, `position`, `t`, and the label-conditioned helpers `mask()` /
   `mean_observed()` — conditioning on the transition label is the experimental design,
   not a leak.

## What the world is

**Articulation.** `u(t) in R^2` by default; `d_art` is configurable to 3, 5, 10. Targets
`u_A = (0,0)`, `u_B = (1, 0.3)`, `u_C = (-0.4, 1)` — abstract coordinates, not tongue and jaw.

**Anticipation.** `theta_{qr} = (1 - alpha_{qr}) u_q + alpha_{qr} u_r`, with four conditions:
no anticipation, shared `alpha`, transition-dependent `alpha` (the hypothesis), and a
time-varying `alpha_{qr}(t)`.

**Dynamics.** `M = I`, `C = diag(70, 50)`, `K = diag(900, 625)`. That makes mode 1
**overdamped** (`zeta = 7/6`, poles −16.97 and −53.03) and mode 2 exactly **critically
damped** (`zeta = 1`, a defective double pole at −25). Two different damping regimes in one
world, deliberately: no single kernel family can be exactly right, so experiment 03 has to
discover the answer rather than confirm it.

Propagation is exact zero-order-hold via `expm`, not Euler. `tests/test_dynamics.py` pins
it against the closed-form modal solution to 1e-12, which is many orders of magnitude below
every effect measured here.

Note that the trajectory does **not** fully settle inside a 200 ms segment: the slow pole
has `tau = 59 ms`, so `K(200 ms) = 0.951`. The kernel is still informative across the whole
window, and any inference that assumes a settled trajectory is wrong in this world.

**Acoustics.** `Phi(u) = (u1 + 0.15 u1 u2, 2 u2 + 0.10 u1^2, u1 - u2 + 0.08 u1 u2)`,
represented as `W u + u' Q u` so it generalises to any `(d_art, d_acoustic)` with a
closed-form Jacobian. Variants: `linear` and `strong_nonlinear` (a saturating map) for the
stress test.

**Noise.** `eps ~ N(0, scale^2 Sigma)`, with `scale = 1.0` reproducing the literal spec
covariance — a *very* low-SNR regime (−4 dB against this signal). Experiments that need a
usable per-frame SNR set a smaller scale explicitly and print the measured SNR beside every
result. Three spatial regimes (white / correlated / one dominant eigenvalue), all normalised
to the same mean variance so regime and level are independent knobs, plus optional AR(1)
temporal correlation with `Cov(eps_t, eps_{t+k}) = Sigma rho^|k|` exactly.

**Speakers.** `g_{r,q}(u) = A_{r,q} u + b_{r,q}`, applied as a **read-out warp** on the
canonical trajectory rather than inside the dynamics. That is what makes the group and
groupoid worlds differ in exactly one respect — whether the chart depends on the phone —
with no confound from the dynamics being warped differently. In the groupoid world the
per-phone deviations are constructed zero-mean across phones, so the two worlds share a
speaker-average chart. The warp is piecewise constant per segment, so a groupoid trajectory
has a small discontinuity at each segment boundary; that is what a phone-local chart means.

**The identifiability twin.** For `h(u) = P u + p`, `generator.affine_twin_world` builds a
second world with targets `h(u_q)`, matrices `P M P^-1, P C P^-1, P K P^-1`, and
`Phi_2 = Phi . h^-1` (computed exactly inside the polynomial family). The two emit
**bit-identical** clean acoustics from latents that differ by 40%.

## What the experiments found

Short version; `results/SYNTHETIC_SPEECH_REPORT.md` has the numbers and the controls.

- **The anticipation effect is easy to detect and easy to over-read.** A transition contrast
  appears within ~20 ms and is significant across most of the segment. Both no-anticipation
  controls sit at the noise floor — including the *dynamic* one, where the trajectory moves
  through the whole segment and the contrast is still exactly zero. But a shared-`alpha`
  world also produces a contrast, so a non-zero `Delta S` proves anticipation, not
  transition-specific anticipation.
- **Low-dimensionality is robust; the exact dimension is not.** `R_1 > 0.999` on clean
  acoustics. The generative rank is 2, but the second mode carries ~0.03% of the contrast
  energy because the two damped responses are nearly collinear curves, so it drops below a
  permuted-label null as soon as noise is non-trivial.
- **The commonly assumed exponential kernel is measurably wrong**, and it shows up in
  extrapolation rather than in fit: ~20x worse than a second-order family when asked to
  predict the last 40% of a window it was not fitted on. A smoothing spline fits best
  in-sample and extrapolates catastrophically.
- **The temporal inverse problem is easy; the acoustic one is not.** With `Phi` known,
  inversion is essentially exact. Blind of `Phi`, local PCA recovers the tangent *subspace*
  but not the Jacobian, and the blind latent is a linear reparameterisation of the true one
  — 1.19 direct error, 0.05 after an affine map.
- **The dynamics are identifiable; the standard recipe is what fails.** Fitting the forward
  model to trajectories recovers `A_u` to ~1% at working noise. Smoothing-then-differentiating
  the same data is off by ~26%, and its answer moves by up to 20x across reasonable
  Savitzky-Golay settings.
- **Latent coordinates are not identifiable and the poles are** — measured, not asserted.
  The twin worlds are statistically indistinguishable at the nominal rate while a
  positive control (a genuinely different world) is rejected every time.
- **Groupoid structure is detectable.** A global-group speaker model loses ~160% held-out
  accuracy on groupoid data against ~0% on group data — the synthetic analogue of an
  empirical 1.70x versus 1.13x. The ratio compresses toward 1 as noise grows, so a ratio
  reported without its noise level is not interpretable.
- **The recognition result is split, and the ablation is why.** The structured model
  transfers to a transition it has never seen (~0.82 accuracy where the discriminative
  baselines cannot place the class at all). But **randomising its dynamics costs nothing**,
  while removing anticipation costs ~0.23. On this task the discriminative information is in
  *where* the trajectory is heading, not *how* it gets there. That supports the gesture layer
  of the factorisation and does not, on its own, support the time layer. The structured model
  also degrades *more* than the GRU on an unseen speaker — a negative result for the
  strongest form of Hypothesis 3.

## Extending it

Dimensionality, noise regime, speaker regime and anticipation condition are all
`config.py` factories (`dimension_world`, `noise_world`, `speaker_world`,
`condition_world`), so a new sweep is usually a list comprehension in an experiment rather
than a change to the generator. Adding a phone means adding a target; targets for
non-canonical phones and for `d_art > 2` are generated deterministically from a seed so
higher-dimensional worlds remain strict extensions of the base world.

# The Lie-bracket test on real articulography — what survived

> Mirror of https://claude.ai/code/artifact/2eb718ee-c765-455c-a487-f9396b7c2545 (updated
> 2026-08-13), captured 2026-08-16. The live page is authoritative.

Corpus: **TORGO**, Carstens AG500 electromagnetic articulography at 200 Hz, synchronised with
head-mic audio and phone labels. **18,186 phone-boundary trajectories, 6 speakers, 885 ordered
phone pairs.** Code: `ema_lie_extract.py` → `ema_lie_test.py`, calibrated by
`ema_lie_selftest.py`. Numbers: `ema_lie_summary.json`, `ema_lie_test.log`.

The plan called for SAIT-EMA. It was not needed — TORGO ships real 3-D EMA and it was already
in this repo at `~/Projects/SpeechRecognition/data/raw/torgo`. Nothing here rests on synthetic
articulation.

## Verdict

| Signature | Prediction | Measured | |
|---|---|---|---|
| `nu_AB > 0` — interaction leaves the first-order span | > 0 | **0.456** (0.000 under pure noise) | **PASSES** |
| `C_AB -> 1` — `R_AB(t) = -R_BA(-t)` | → +1 | **−0.097**, typical speakers **−0.262** CI [−0.341, −0.062] | **FAILS — sign is wrong** |
| `alpha = 2` — residual quadratic in gesture size | = 2 | not identifiable from this design | **UNTESTABLE** |

**The pairwise Lie-bracket mechanism is not supported.** There is a large, reliable,
label-driven interaction at phone boundaries, and it does introduce articulatory directions the
first-order gestures never use. But it is not antisymmetric. Where a bracket predicts
`R_AB = -rev R_BA`, the data give the opposite sign: the residual is weakly **time-symmetric**,
which is the signature of target undershoot and blending, not of a commutator.

By your own decision rule this is line 2 — "quadratic interaction, but not convincing Lie
structure" — with the caveat that the quadratic part was never actually established.

## 1. The interaction is real, and it is not small

The non-interaction model `x_AB(t) = mu + S_s + L_A(t) + R_B(t)` was fitted by OLS over all
18,186 boundary windows after removing the static boundary posture. Its residual `R_AB`:

| | all (6 spk) | typical (3) | dysarthric (3) | placebo |
|---|---|---|---|---|
| boundaries | 18,186 | 12,904 | 5,282 | 18,186 |
| split-half reliability of `R_AB` | **0.596** | 0.554 | 0.099 | **0.000** |
| interaction / first-order energy, 40 ms out | 0.150 | 0.133 | 0.064 | — |
| interaction / first-order energy, 80 ms out | 0.196 | 0.179 | 0.078 | — |

`R_AB` carries **15–20 % of the first-order energy** and reproduces across independent halves of
the tokens at r ≈ 0.6. Shuffling phone identities within speaker drives the reliability to
**0.000**, so the structure is genuinely a property of *which two phones met*, not of the window
or the speaker.

Two incidental findings worth keeping:

- The interaction energy is **smallest at the boundary and grows outward**, reaching its maximum
  at ±80 ms. (Partly forced — removing the boundary posture pins every trajectory to zero at
  t = 0 — but the *ratio* to first-order energy also rises with distance, 0.15 → 0.20.) The
  interaction is not a boundary event; it is a spreading one.
- Dysarthric speakers show a **much weaker and barely reliable** interaction (energy ratio 0.078,
  reliability 0.099) than typical speakers. Their coarticulatory structure is not just noisier —
  there is less of it.

## 2. Antisymmetry — the distinctive prediction — fails

For the 53 unordered phone pairs seen in both orders ≥ 25 times each,
`C_AB = cos(R_AB, -rev R_BA)`:

- all speakers: median **−0.097**, CI [−0.294, +0.032], 40 % positive
- typical speakers: median **−0.262**, CI [−0.341, −0.062], 32 % positive
- unrelated-pair null: −0.010

In the typical-speaker set the interval excludes zero **on the negative side**. A negative `C`
means `R_AB ≈ +rev R_BA`: swap the two phones and the interaction comes back the same, not
inverted. That is what a symmetric blend between two targets does. A bracket cannot do it.

This reading is trustworthy because the estimator was calibrated against planted ground truth
(§4): it returns **+0.95** when a real antisymmetric bracket is present and **−0.94** when the
planted term is symmetric instead. It is not a low-power test that happened to miss.

The per-pair spread is wide (individual `C` from −0.67 to +0.65, unrelated-pair null p95
|C| = 0.67), so no single pair means anything; the result is in the median over 53 pairs.

## 3. Rank growth — the 2 → 3 idea — holds

The span of the fitted first-order effects `{L_A, R_B}` in the 12-dimensional articulator space
is **k = 2**, as the picture assumed. Of the reliable residual energy, **ν = 0.456** lies outside
that plane (raw 0.528; isotropic chance would be 0.913; pure measurement noise gives 0.000
because the estimator uses cross-half products and so cancels it).

So the interaction genuinely moves articulators in directions the two gestures alone never move
them — it is not a relabelled combination of the first-order effects. This part of the story
survives. It is also the weakest of the three tests on its own: almost any nonlinearity would
produce it.

## 4. The exponent test cannot be run — and this is a property of the design

The originally specified regression

```
log |R_AB| = alpha log eps + gamma_AB + gamma_s + xi
```

is **not identified**: `eps`, the magnitude of the fitted first-order gesture, depends only on
(speaker, A, B), which `gamma_AB + gamma_s` already absorbs. There is no variation left to
regress. Three successively better estimators were built and calibrated against planted truth:

| estimator | planted α=2 | planted α=1 | no interaction |
|---|---|---|---|
| token-level `log ‖R_n‖`, per-token gain | 0.41 | 0.37 | 0.00 |
| cross-token covariance (cancels noise floor) | 0.65 | 0.80 | −0.12 |
| ε and R on disjoint parts of the window | **1.10** | **1.20** | 0.13 |

None separates 2 from 1. The reason is structural, and was confirmed directly against the known
generating gains: **any ε read off the observed trajectory already contains the quadratic term
whose exponent it is meant to predict.** On the planted-α=2 data, log ε scales as `a^1.35`
rather than `a^1.0`, which flattens the measured slope toward 1 no matter what estimator sits
downstream. Identifying α needs an *exogenous* handle on gesture magnitude — experimental rate
or loudness control — that an observational corpus does not provide.

What the estimator does do reliably is separate "an interaction is present" (real data: **0.85**,
CI [0.67, 1.00]) from "there is none" (0.13). That agrees with §1 and adds nothing beyond it.

## 5. Calibration (`ema_lie_selftest.py`)

Trajectories were regenerated on TORGO's actual speaker/phone/token structure — same cells, same
counts, same imbalance — with known ground truth, and put through the identical estimator. The
planted interaction is orthogonalised against the additive design, since an interaction that has
an additive projection is partly first-order by definition (leaving it in was itself dragging
every world to α ≈ 1).

| world | α | C | ν | reliability |
|---|---|---|---|---|
| bracket — antisymmetric, quadratic | 1.10 | **+0.947** | 0.914 | 0.993 |
| linear — antisymmetric, linear | 1.20 | **+0.951** | 0.928 | 0.987 |
| symmetric — quadratic, not a bracket | 1.10 | **−0.937** | 0.922 | 0.992 |
| noise — no interaction at all | 0.13 | +0.034 | **0.000** | 0.000 |

`C` discriminates cleanly in both directions. `ν` is at chance in the three interaction worlds
because the planted term is isotropic by construction; its calibration point is the noise world,
where it correctly reads 0.000 rather than being inflated to chance. `α` does not discriminate.

## 6. Data provenance and what was thrown away

Sensor identity was **verified, not assumed**. TORGO ships no channel map; the assignment was
read off the per-session geometry and then checked phonetically across the corpus — velars
`k, g, ng` peak on TD_z (+0.64 to +0.72 σ), coronals `t, d, n, s, z` on TT_z, `sh` higher and
further back than `s`, and the smallest lip aperture belongs to `m, v, b, p, f, w` with the
largest to `ae, eh, ay`. Channels 1/2/3/6/7/8 are tongue dorsum / blade / tip and upper lip /
lower lip / jaw; 4, 5, 11, 12 are references; 9, 10 are lip corners.

Excluded, with reasons:

- **M04/S2, M05/S1, M05/S2** — tongue coils dead (identically zero).
- **MC03/S1** — phone labels run 2.7× past the recording; they are aligned to a different audio
  stream. An earlier pass silently kept 1,062 windows from this session before the alignment
  gate was added; they were noise wearing phone labels.
- **2,561 individual windows** — sensor teleports (> 4 mm between consecutive 5 ms frames) or
  excursions > 30 mm from the window mean.

Both remaining groups are small: 3 typical speakers and 3 dysarthric. Speaker-cluster bootstraps
over n = 6 are coarse, and that is the main limitation of everything above.

## What would move this

1. **Replication on a wider corpus.** SAIT-EMA, if it is as described (18 speakers, 250 Hz,
   head-corrected 3-D, same six midsagittal sensors), would take the speaker bootstrap from 6 to
   18 and is a direct drop-in — only `ema_lie_extract.py`'s reader changes. Worth doing whatever
   this result was going to be; the antisymmetry test is cheap and already validated.
2. **The symmetric alternative, taken seriously.** `C < 0` is a positive finding, not just a
   failed prediction. A blending/undershoot model predicts `R_AB = +rev R_BA` and predicts the
   outward-growing energy profile in §1. It is worth fitting on its own terms rather than as the
   null.
3. **Do not go looking for the ε³ term.** The rule was that only `alpha ≈ 2, C → 1, nu > 0`
   justifies it. `C` came back with the wrong sign and `alpha` cannot be measured here at all.

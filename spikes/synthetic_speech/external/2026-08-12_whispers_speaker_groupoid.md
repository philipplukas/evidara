# Whisper's Speaker Groupoid

> Mirror of https://claude.ai/code/artifact/a39c1365-cda5-4824-b0a9-d51c4a8e2730 (updated
> 2026-08-12), captured 2026-08-16. The live page is authoritative.

**TIMIT · whisper-small · 8 seeds**

Half of what separates speakers inside Whisper's encoder is not a vector you can add. It is
phone-dependent, and the phone-to-phone transforms compose only when their endpoints match —
but a microphone filter passes that same test, so composition measures the generator's
dimension, not its anatomy.

| Run metadata | |
|---|---|
| Corpus | TIMIT, 630 speakers, 6300 utts |
| Representation | frozen encoder, 8 hidden states |
| Tokens | 187,737 phone-aligned |
| Design | speaker × phone cells, two halves |

| Experiment | Question | Verdict |
|---|---|---|
| 1 | Is the speaker effect additive? | **No — 50% is interaction** |
| 2 | Does free phone-dependence adapt better? | **Unresolved** |
| 3 | Is the phone-dependence low-dimensional? | **Yes — 6 of 29** |
| 4 | Do the arrows compose? | **Yes — endpoints matter** |
| 5 | Can a microphone fake all of it? | **The algebra, yes** |
| 5b | Can it fake the magnitude? | **No — 3–16× short** |

## The design: two halves of every speaker, so noise cancels

A *cell* is a (speaker, phone) pair, measured twice in two disjoint halves of that speaker's
material. Two independent measurements mean cross-half inner products estimate signal energy
with the noise removed in expectation — no held-out set can substitute for this, because the
quantity of interest is smaller than the per-cell noise.

Three conditions. In `SXSI` the halves are a random 4/4 split of a speaker's SX and SI
sentences: the most material, no controls. In `SA` the halves are the two SA sentences that all
630 speakers read, so the same phone sits in a *different word* in the two halves and anything
driven by sentence content decorrelates by construction. `SXSI11` cuts SX/SI down to the SA
phone inventory and adaptation size, so that any SA-vs-SXSI difference is the content control
rather than the smaller design.

Adaptation is scored by `captured` = 1 − E‖ρ − p‖² / E‖ρ‖², where ρ is the speaker's true
residual on *unseen phones* and p the prediction from a handful of adaptation cells. 1.0 is a
perfect prediction; 0.0 is no better than not adapting at all; negative is worse than not
adapting.

### Two scoring bugs found during the rebuild

**Same-half leakage.** Cells inside one half share session, channel and prosody, so a predictor
fitted on both halves and scored against either was scoring partly against its own noise. In SA,
where a half is a single sentence, this produced `captured` values of 3.7 and 19.0. Adaptation
now takes one half, evaluation the other.

**Half-averaged phone reference.** The halves are different sentences, so a phone's content
offset enters them with opposite sign and drives the cross-half denominator negative. The
reference is now computed per half, from training speakers only.

## Experiment 1 — the interaction is real, and content does not explain it

Decompose each cell into grand mean, phone effect, additive speaker effect and interaction, fit
per half, then measure each term's cross-half energy.

Share of reliable energy · 630 speakers · SA is the content-controlled condition

| Layer | 0 | 1 | 2 | 3 | 4 | 6 | 8 | 12 |
|---|---|---|---|---|---|---|---|---|
| interaction, SX/SI | .176 | .149 | .114 | .103 | .091 | .065 | .043 | .023 |
| interaction, SA | .163 | .151 | .115 | .105 | .094 | .058 | .035 | .021 |
| additive speaker, SA | .166 | .121 | .106 | .093 | .089 | .059 | .053 | .041 |
| interaction ÷ speaker-related | .49 | .55 | .52 | .53 | .51 | .50 | .40 | .34 |
| phone-effect reliability, SX/SI | .99 | .99 | .99 | 1.00 | 1.00 | 1.00 | 1.00 | .99 |
| phone-effect reliability, SA | .25 | .44 | .46 | .47 | .45 | .45 | .38 | .17 |

The last two rows are the control's own proof of work: the phone main effect loses most of its
reliability under SA, exactly because the halves are different sentences. The interaction does
not budge. **About half of the speaker-related signal in the early layers is invisible to any
`u ↦ u + d_s` embedding**, and it is not sentence content.

## Experiment 2 — a free phone-dependent basis does not reliably adapt better

Matched comparison: same adaptation protocol, same number K of per-speaker parameters, same
fitting and scoring. Only the basis structure changes — `tied` uses one vector for all phones,
`free` gives every phone its own block. Ridge strength chosen on validation speakers; every
number is on held-out speakers and their held-out phones, paired within seed.

free-1 minus tied-1, mean ± SE over 8 seeds

| Layer | SX/SI | SXSI11 (design-matched) | SA (content-controlled) |
|---|---|---|---|
| 0 | +0.211 ± .005 | +0.204 ± .013 | +0.235 ± .022 |
| 1 | +0.119 ± .002 | +0.126 ± .006 | −0.083 ± .021 |
| 2 | +0.088 ± .002 | +0.096 ± .005 | −0.078 ± .021 |
| 3 | +0.075 ± .002 | +0.081 ± .005 | −0.048 ± .017 |
| 4 | +0.057 ± .002 | +0.063 ± .005 | −0.043 ± .016 |
| 6 | +0.047 ± .002 | +0.046 ± .004 | +0.062 ± .017 |

SXSI11 tracks SX/SI, not SA — so the sign flip at layers 1–4 is *not* the smaller phone
inventory or the thinner adaptation set. It is the content control, or the lower per-cell token
count that comes with it, which this design cannot separate. The interaction energy survives the
control; the few-shot adaptation advantage of a free phone-dependent basis does not.
**Unresolved, and it should be reported as unresolved.**

One thing here is not in doubt. The free 768-parameter additive baseline — `d_s` = mean
adaptation residual, the ordinary speaker embedding — scores between −0.76 and −11.8 depending
on layer, and optimal shrinkage only lifts it to 0.10. With ten adaptation cells it fits noise.
That is the sample-efficiency failure the structured account predicts, measured directly.

## Experiment 3 — six shared phone coordinates out of twenty-nine

The model confines every basis component to one shared phone subspace `P ∈ R^(Q×r)` whose first
column is the constant vector — so `r = 1` *is* the phone-constant basis and `r = Q` *is* the
free basis, with a continuous ladder between. Run at K = 1.

SX/SI, layer 1, 29 phones · the increment is free-1 minus tied-1 = 0.119

| r | 1 | 2 | 3 | 4 | 6 | 8 | 12 | 16 | free (29) |
|---|---|---|---|---|---|---|---|---|---|
| captured | .214 | .257 | .276 | .288 | .309 | .320 | .331 | .334 | .333 |
| share of increment | 0% | 36% | 52% | 62% | 80% | 89% | 98% | 100% | 100% |
| basis parameters | 797 | 1,594 | 2,391 | 3,188 | 4,782 | 6,376 | 9,564 | 12,752 | 22,272 |

**Six of twenty-nine phone coordinates recover 80% of what free per-phone blocks buy, at 4.7×
fewer basis parameters; eight recover 89%.** The curve is smooth and saturating at every layer
and in every condition — there is no elbow at r = 2, and the earlier reading that two
coordinates suffice does not survive multi-seed testing.

## Experiment 4 — the arrows compose, and only when their endpoints match

The groupoid claim is about composition: `A_(r→p) A_(q→r) ≈ A_(q→p)` for arrows whose endpoints
agree, and nothing at all for arrows whose endpoints do not. So the test must include the
mismatched control.

Arrows are fitted per ordered phone pair over training speakers, acting on a 12-dimensional
subspace chosen by cross-half *reliability* rather than variance — ordinary PCA is useless here,
since a single interaction cell is noise-dominated and its top variance directions are noise.
The additive speaker component is removed first.

captured on held-out speakers · the composed predictor never sees the q→p arrow

| Condition | direct | composed | mismatched | identity |
|---|---|---|---|---|
| SX/SI, layer 0 | 0.153 | 0.261 | −0.000 | −9.4 |
| SX/SI, layer 1 | 0.247 | 0.287 | −0.000 | −4.6 |
| SX/SI, layer 3 | 0.080 | 0.217 | −0.000 | −12.4 |
| SX/SI, layer 8 | 0.018 | 0.056 | −0.000 | −20.7 |
| SA, layer 1 | 0.108 | 0.218 | −0.000 | −8.6 |
| SA, layer 8 | 0.225 | 0.260 | −0.000 | −6.1 |
| SA, layer 12 | 0.241 | 0.328 | −0.000 | −9.7 |

All sixteen layer × condition cells give composed − mismatched > 0. In SX/SI every layer clears
eleven standard errors. In SA five of eight layers clear two; layers 3 and 4 are positive but
inside the noise (t = 1.8 and 1.7).

- **Composition beats the directly fitted arrow.** The composed predictor is built only from
  arrows through third phones, and still outperforms the arrow fitted on that very pair.
  Composition does not merely hold, it *denoises*.
- **Mismatched composition is worth nothing.** At matched ridge strength it is strictly negative
  (−0.043, −0.033, −0.010, −0.001 as γ rises); it reaches 0.000 only by being shrunk out of
  existence. Composition holds *only* when the endpoints agree — the property that separates a
  groupoid from a bundle, a fibrewise deformation, or a family of unrelated local maps.
- **It survives the content control** — positive at every layer, significant at five of eight.

## Experiment 5 — what a microphone can fake, and what it cannot

One hundred pseudo-speakers built by passing an identical pool of 36 TIMIT utterances through
one hundred random channels — smooth random EQ plus a mild room response — at three strengths.
The articulation is byte-identical across pseudo-speakers.

layer 1 · pseudo-speakers differing only by channel

| | weak | mid | strong | real speakers |
|---|---|---|---|---|
| additive share | .023 | .086 | .265 | .108 |
| interaction share | .007 | .025 | .069 | .149 |
| composed | .966 | .950 | .907 | .287 |
| mismatched | −.000 | −.000 | −.000 | −.000 |
| free-1 − tied-1 | +.042 | +.036 | +.031 | +.119 |

**A pure channel reproduces the entire qualitative signature** — arrows that compose, mismatched
composition worth exactly nothing, free beating tied, a saturating ladder — and it composes
*better* than real speakers do, at every strength and every layer. Composition with endpoint
matching is therefore evidence that the generator is low-dimensional, not that it is
articulatory.

interaction ÷ additive energy · channel at three strengths vs real speakers

| Layer | weak | mid | strong | real | discrepancy |
|---|---|---|---|---|---|
| 0 | .072 | .073 | .071 | 1.13 | 16× |
| 1 | .30 | .29 | .26 | 1.38 | 5× |
| 2 | .43 | .38 | .34 | 1.23 | 3.3× |
| 3 | .44 | .44 | .40 | 1.32 | 3× |

Even under the absurd upper bound that *all* of TIMIT's additive speaker energy is channel
rather than anatomy, a channel accounts for 6% (layer 0) to 32% (layer 3) of the observed
interaction. For a single-studio, single-microphone corpus the realistic figure is a few percent.

**The composition score estimates the generator's effective dimension**: a one-parameter
generator drives it to .95 because every phone's transform descends from the same scalar, and
real speakers sit at .29. **The ladder's saturation rank says the same** — the channel takes 52%
of its increment at r = 2 and 88% by r = 6, where real speakers take 36% at r = 2 and need
r ≈ 6–8. Channel generator ≈ 1–2 dimensions; real generator ≈ 6.

That triad — interaction ÷ additive, composition score, saturation rank — is a *fingerprint of
the generator*. Next step: synthesise pseudo-speakers from known generators (vocal-tract-length
warp, F0 shift, rate change), fingerprint each, and ask which one real speakers match.

## Limits

- **One recording session per TIMIT speaker.** Channel and speaker are perfectly confounded in
  the corpus. Experiment 5 bounds what that can cost — a few percent of the observed interaction
  — but bounding is not separating. The clean version needs the same speakers recorded across
  sessions, or TORGO's simultaneous head and array microphones.
- **Deep layers are small-denominator regimes.** By layer 12 the reliable speaker energy is 2–4%
  of the total, so `captured` ratios swing wildly (one condition returns −2.5 with an SE of 3.5).
  Layers 8 and 12 are not evidence in either direction.
- **SXSI11 isolates the content control but not per-cell SNR**, since an SA cell rests on one
  sentence per half.
- **Everything is whisper-small.** Nothing here says the structure survives a change of scale —
  or that it corresponds to anything articulatory. That question needs EMA or rtMRI.

---

Code: `algebra_extract.py` · `algebra_cells.py` · `algebra_interaction.py` · `algebra_rank.py` ·
`algebra_composition.py` · `algebra_report.py`
Results: `algebra_interaction.json`, `rank_sweep_{SXSI,SXSI11,SA}.json`,
`algebra_composition.json` · written up in `FINDINGS.md §J`

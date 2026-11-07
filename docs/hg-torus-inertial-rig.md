# Hg-Torus Inertial Rig: Evidence Tiers and Test Protocol

Status: DRAFT for design review. Timestamp: set at publish (single pack-level stamp).
Claim under test (H1): a rotating liquid-metal toroid produces a measurable reduction in the apparent inertia (or weight/thrust response) of its host rig.

## 1. Evidence tiers

| Tier | Meaning | What qualifies |
|---|---|---|
| T0 | Idea | Stated hypothesis, no data |
| T1 | Modelled | Written physics model with predicted magnitude and a stated detection threshold |
| T2 | Measured, uncontrolled | One run, one rig, no sham |
| T3 | Measured, controlled | Sham/null runs, blinded analysis, error budget; effect exceeds budget |
| T4 | Replicated | Independent rig or team reproduces T3 with pinned code/data (commit SHA) |

Nothing is promoted without a pinned SHA for the analysis code and raw data. A result that fails a null run is demoted, not explained away.

## 2. Prior and why controls matter

Momentum and energy conservation predict no net inertia change for a closed rig. A positive result is extraordinary, so the protocol is built to find artifacts first: gyroscopic torques, buoyancy and sloshing, bearing and motor reaction, air drag and convective lift, magnetic coupling to the environment, thermal drift, and load-cell creep.

## 3. Safety

Mercury is toxic and volatile. Do not build the first rig with Hg. Use a surrogate of matched density behavior where possible (galinstan, sealed, or water-glycol for geometry-only trials), double containment, and no open handling. Mercury work needs a lab with vapor control and disposal.

## 4. Protocol

1. **Rig**: sealed toroidal channel on a rigid frame; drive motor outside the fluid path; fluid mass logged to 0.01 g.
2. **Measurement**: (a) load cell for apparent weight, (b) torsion pendulum or linear air-track for inertial response. Log at a fixed rate with a shared clock.
3. **Conditions**, each repeated at least 20 times in randomized order by a script that hides the label from the analyst:
   - A: fluid, spinning at set rate
   - B: fluid, stationary
   - C: sham, same total mass as a solid ring spinning at the same rate
   - D: empty channel, motor running
   - E: fluid, spinning, reversed direction
4. **Error budget** before the first run: load-cell noise floor, thermal drift per hour, vibration coupling (measure with motor on, fluid out), seal leakage.
5. **Environment sweep**: repeat A and C in vacuum or at reduced pressure to separate air effects; shield or rotate the rig relative to the lab magnetic field.
6. **Analysis**: preregistered (effect size, test, threshold) and committed before data is taken. Report A-minus-C, A-minus-B and E-minus-A with confidence intervals.
7. **Pass condition for T3**: A differs from C and B by more than the error budget, sign flips or vanishes appropriately under E and D, and the effect scales with spin rate in the direction the model predicts.
8. **Publish**: raw data, scripts and rig drawings under a pinned commit SHA via the shelf (`tru_shelf.py propose`, `approve`, `check`).

## 5. Open items for design review

- Model for H1 with predicted magnitude (needed to reach T1)
- Which inertia measure we commit to (weight, thrust, or oscillation period)
- Surrogate fluid choice and containment design

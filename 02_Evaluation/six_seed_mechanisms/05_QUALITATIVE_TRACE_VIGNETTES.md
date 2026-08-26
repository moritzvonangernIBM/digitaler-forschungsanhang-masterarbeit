# Qualitative Trace Vignettes

## Purpose and selection

This audit complements, but does not replace, the complete quantitative
mechanism linkage. Cases were selected purposively as contrasting,
information-rich pairs:
one `saved` and one `broken` Exact-Mutation transition for A, B, and C3. A
cases require at least one support card linked to a later write candidate. B
cases require at least one material decision. C3 cases require both links.

The six cases are explanatory vignettes. They do not estimate frequencies,
mediator effects, or causal effects within the selected subgroups.

## Coding frame

Each case is read along the same evidence chain:

1. visible user goal and later revision or uncertainty;
2. materialized A card, where applicable;
3. exact linked write candidate;
4. B disposition and cited visible evidence, where applicable;
5. executed mutation and offline Exact-Mutation transition;
6. mechanism-consistent interpretation and explicit alternative explanation.

## A: semantic support

### Saved case: task 5, seed 976302, C1

- The user first requested exchanges for a bottle and a lamp, then explicitly
  revised the request: no exchange should be made and the bottle should be
  returned instead.
- Card `AC-0001` retained the return goal and marked the revision cue. Its
  linked candidate was `return_delivered_order_items` for item `8538875209`.
- The cell changed from native Exact failure to C1 Exact success.
- Interpretation: the trace is consistent with A preserving a late revision
  until the write boundary. The vignette does not prove mediation because the
  intervention can also change the preceding dialogue trajectory.

### Broken case: task 3, seed 976304, C1

- The dialogue contained compound and evolving requirements for two pending
  orders, including an initial purple preference and a later order-specific
  request concerning black, XXL, polyester, and v-neck.
- Cards `AC-0002` and `AC-0003` were linked to writes for both orders. The
  support state retained multiple temporally distributed commitments rather
  than resolving them into one unambiguous current order-level state.
- The C1 cell executed an additional modification for order `#W6247578` and
  changed from native Exact success to C1 Exact failure (`extra_effect`).
- Interpretation: source grounding alone did not prevent an over-broad or
  stale commitment state from reaching a write candidate. The trace supports
  a revision-resolution boundary, not the claim that A alone caused the
  regression.

## B: pre-write control

### Saved case: task 0, seed 976301, C2

- B inspected an exchange candidate and found that the payment profile had not
  yet been observed (`B_PAYMENT_PROFILE_NOT_OBSERVED`).
- The candidate was held, the authenticated user profile was read, and the
  identical candidate was then released unchanged.
- The candidate used replacement item `7706410293`; the cell changed from
  native Exact failure to C2 Exact success.
- Interpretation: B enforced evidence completeness at the transaction boundary.
  Because it did not alter the candidate, the saved outcome cannot be
  attributed to semantic correction by B alone.

### Broken case: task 0, seed 976303, C2

- B followed the same control pattern: hold for the missing payment profile,
  read the profile, then release the candidate unchanged.
- This candidate used replacement item `6342039236` instead of the expected
  `7706410293`.
- The cell changed from native Exact success to C2 Exact failure
  (`wrong_parameter`).
- Interpretation: the control established payment feasibility but had no
  runtime authority or evidence for semantic target correctness. The matched
  task contrast shows the implemented control's exact governance boundary.

## C3: combined intervention

### Saved case: task 21, seed 976304, C3

- A materialized a card linked to a two-item pending-order modification and
  preserved the requested use of the gift card.
- B held the candidate because relevant product evidence had not been observed,
  requested the read, and then released the unchanged candidate.
- The cell changed from native Exact failure to C3 Exact success.
- Interpretation: the trace is compatible with complementary support and
  feasibility control, but does not isolate which component produced the
  outcome change.

### Broken case: task 1, seed 976301, C3

- A materialized compound exchange commitments and linked them to the later
  exchange candidate.
- B held the candidate only until the payment profile was observed and then
  released it unchanged.
- The executed exchange contained replacement item `6342039236`; the offline
  diagnosis identified an `extra_effect`, and the cell changed from native
  Exact success to C3 Exact failure.
- Interpretation: simultaneous component activation did not guarantee semantic
  target correctness. The case is consistent with the negative point estimate
  of the interaction, but one vignette cannot establish an interaction effect.

## Synthesis

The positive and negative cases support three bounded conclusions. A can keep
late user revisions visible near a write but needs stronger temporal conflict
resolution. B creates an auditable feasibility gate but does not validate the
business-semantic target under its current information boundary. C3 can combine
both paths, yet their activation is neither sufficient for success nor evidence
of additive benefit.

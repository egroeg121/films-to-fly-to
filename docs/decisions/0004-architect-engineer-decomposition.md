# Decision: Architect + Engineer roles for autonomous backlog decomposition

Status: Proposed (2026-06-19)
Issue: ftft-yjf

## Problem

Beads land in the backlog vague and large: a one-line title, no acceptance
criteria, no children, no size estimate. A polecat slung such a bead either
guesses at scope (and ships the wrong thing) or stalls asking the Witness for
clarification (and burns a session). Today the only thing standing between a
vague bead and a confused polecat is the Mayor's manual judgement at sling time.

We want a **continuous, autonomous loop** that turns vague beads into a set of
small, executable leaf beads *before* they reach a polecat — and that refuses to
let under-specified work through.

## Decision

Introduce two cooperating Gas Town roles that run on patrol loops and
communicate **only through beads and mail** (never within one session):

- **Architect** — decomposes vague/large beads into structured child beads.
- **Engineer** — reviews each decomposition for executability; approves it
  (→ ready to sling) or bounces it back with specific feedback.

The Mayor's existing sling behaviour is unchanged: it slings *ready* leaf beads.
The new loop simply guarantees that what reaches "ready" is genuinely
executable.

```
            ┌──────────────────────────────────────────────┐
            │                                              ▼
 vague bead ──► [Architect] ──decomposes──► child beads ──► [Engineer review]
 (needs-                                                          │
  decomposition)                                    approve │     │ reject (feedback)
                                                            ▼     ▼
                                                  ready-to-sling   back to Architect
                                                            │      (round++ , max 3)
                                                            ▼
                                                        [Mayor slings] ──► [Polecat]
```

## Why two roles, not one

A single agent that both decomposes *and* declares its own work ready has no
adversarial check — it will rationalise its own vagueness. Splitting the author
(Architect) from the reviewer (Engineer) gives an independent gate, the same way
a polecat's work is gated by the Witness/Refinery rather than self-merged. The
Engineer's only job is to be a sceptic: *"could a polecat execute this child bead
without asking a single question?"* If not, it bounces.

## State machine (label convention)

State lives on the **parent bead** as a single mutually-exclusive label, so any
agent can discover the backlog's state from beads alone (discovery over
tracking — the Gas Town principle). No state is held in any session.

| Label | Meaning | Set by |
|---|---|---|
| `arch:needs-decomposition` | Vague/large; awaiting Architect | Architect intake (or human) |
| `arch:decomposing` | Architect actively working it | Architect (claim) |
| `arch:pending-review` | Decomposed; awaiting Engineer | Architect (on submit) |
| `arch:changes-requested` | Engineer bounced it; Architect must iterate | Engineer (on reject) |
| `arch:approved` | Engineer approved; leaves are ready to sling | Engineer (on approve) |
| `arch:escalated` | 3 rounds exhausted; needs a human | Engineer (on round 3 fail) |

Round count is tracked as `arch:round:N` on the parent bead (label, not session
state) so it survives Architect/Engineer session death.

Child (leaf) beads carry `arch:leaf` and a back-reference to the parent via a
`bd dep add <leaf> <parent>` dependency ("leaf needs parent context"), so the
decomposition is reconstructable after any session dies.

## Architect role

**Trigger**: patrol loop, woken by `await-signal` on beads activity (same
exponential-backoff/effort-tuning pattern the Witness patrol uses), with a
periodic floor (e.g. hourly) so a quiet backlog still gets swept.

**Per cycle**:
1. **Intake** — find candidates: open beads with *no children*, short
   description (< ~200 chars), no acceptance criteria, and not already labelled
   `arch:*`. Tag them `arch:needs-decomposition`. (Humans can pre-tag too.)
2. **Pick one** `arch:needs-decomposition` (or `arch:changes-requested`) bead,
   claim it → `arch:decomposing`.
3. **Decompose** into child beads. Each child MUST have:
   - title,
   - description ≥ 200 chars with enough context to execute blind,
   - a size estimate (≤ 2h of polecat work),
   - testable acceptance criteria,
   - dependencies expressed correctly (`bd dep add X Y` = "X needs Y";
     temporal language inverts this — verify with `bd blocked`).
4. **Model selection** — use **jasper (Opus)** when decomposition needs design
   judgement (architecture, ambiguous scope, cross-cutting work); use
   **claude-sonnet** for straightforward "obvious sub-tasks" decomposition. The
   Architect role's *formula* runs on Sonnet by default; it escalates a single
   bead's decomposition to an Opus sub-agent (`gt sling ... --agent jasper`) only
   when it self-assesses the bead as judgement-heavy.
5. **Submit** — on `arch:changes-requested` beads, read the Engineer's feedback
   (see "Feedback channel") and revise. Set parent → `arch:pending-review`,
   bump `arch:round:N`.
6. **Never** sets a bead ready itself. That is the Engineer's gate.

## Engineer role

**Trigger**: patrol loop (separate session/role), woken on beads activity;
naturally lags the Architect by one cycle — the loop is async by design.

**Per cycle**, for each parent bead in `arch:pending-review`:
1. Read the parent and all its `arch:leaf` children.
2. Grade each child against the checklist:
   - **Small enough?** estimate ≤ 2h.
   - **Clear enough?** a polecat could execute without asking questions.
   - **Testable?** acceptance criteria are objectively verifiable.
   - **Complete?** the children together actually satisfy the parent.
   - **Dependencies sane?** (`bd blocked` shows the intended order).
3. **If all pass** → set children ready, label parent `arch:approved`, and mail
   the Mayor a `READY_TO_SLING` message listing the approved leaf bead IDs.
4. **If any fail** → label parent `arch:changes-requested`, write specific,
   itemised feedback (which child, what's wrong: too vague / too large / missing
   context / untestable), and notify the Architect.
5. **Round limit** — if the parent is already at `arch:round:3` and still fails,
   label `arch:escalated` and mail the Mayor for human intervention instead of
   bouncing again.

## Feedback channel (async, survives session death)

The hard constraint from the bead: communication must be **beads/mail, not
in-session**, and the loop must be **async** (Architect submits in cycle N,
Engineer reviews in cycle N+1).

Decision: feedback is persisted on the **parent bead** as structured notes
(`bd update <parent> --design "ROUND 2 FEEDBACK: ..."`), and a lightweight
`gt mail send` nudge tells the counterpart there's something to read. Mail is
the *doorbell*; the bead is the *source of truth*. This follows the town's
"nudge for routine, mail only when it must survive session death" hygiene — here
the durable content is in the bead, so the notification can even be a `gt nudge`.
We use mail (one Dolt commit) only for the Mayor-facing `READY_TO_SLING` and
`ESCALATED` signals, which must survive.

## Mayor's role (unchanged sling, new trigger)

- Receives `READY_TO_SLING` mail → slings the listed approved leaf beads to
  polecats, picking the per-bead model from the Architect's recorded estimate
  /complexity (Sonnet default, Haiku for trivial, Opus rarely).
- Receives `ESCALATED` mail → a human decides (re-scope, split differently, or
  drop the parent).
- Polecats implement leaf beads exactly as today — **no polecat change**.

## Why this shape

- **Discovery over tracking**: all state is labels/deps on beads. Either patrol
  can be killed and respawned and reconstruct the entire backlog state from
  `bd list --label arch:*`. Nothing lives in a session.
- **Adversarial gate**: the author cannot bless its own work — matches the
  Witness/Refinery gate on polecat code.
- **Bounded iteration**: 3 rounds then a human, so a pathological bead can't
  ping-pong forever and burn tokens.
- **Mechanism reuse**: both roles are ordinary patrol formulas using the
  existing `await-signal` / effort-tuning / agent-bead machinery the Witness and
  Deacon already use. No new runtime primitive is required.

## Where this lives (important — repo routing)

Gas Town **formula TOMLs are gitignored runtime state**
(`<town>/.beads/formulas/`, Dolt-backed) — they are *not* committed to any repo,
and they are *not* part of the `films_to_fly_to` application repo where this
polecat's worktree lives. Therefore:

- The **design** (this doc) is committed here, in the rig whose backlog motivated
  it, as the durable record.
- The **two formula TOMLs** are committed here under `docs/gastown/` as reference
  artifacts so they survive session death and can be installed into town runtime.
- The **installation / wiring work** (copy formulas into `<town>/.beads/formulas/`,
  register the two roles, start their sessions) is **`gt` infrastructure** and is
  filed as beads against the **gastown** rig — that is the repo a fix would be
  committed to, per the "which repo owns the code" rule.

## Follow-ups (filed as beads, not done here)

- gastown: install `mol-architect-patrol` + `mol-engineer-review` formulas and
  register Architect/Engineer roles (rig-level in films_to_fly_to or town-level).
- gastown: teach the Mayor's Deacon patrol to handle `READY_TO_SLING` /
  `ESCALATED` mail and sling approved leaves.
- gastown: add `arch:*` to the recognised label vocabulary / `bd` conventions.
- Decide role placement: rig-scoped (one Architect/Engineer per rig) vs.
  town-scoped (one pair serving all rigs). Start rig-scoped for films_to_fly_to.

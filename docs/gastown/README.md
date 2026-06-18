# Gas Town artifacts: Architect + Engineer decomposition roles

These files are **reference artifacts** for the autonomous backlog-decomposition
loop designed in [`../decisions/0004-architect-engineer-decomposition.md`](../decisions/0004-architect-engineer-decomposition.md)
(issue ftft-yjf).

| File | Purpose |
|---|---|
| `mol-architect-patrol.formula.toml` | Architect patrol — decomposes vague beads into executable leaves |
| `mol-engineer-review.formula.toml` | Engineer review — gates each decomposition; approve or bounce |

## Why they live here and not in town runtime

Gas Town formula TOMLs live in `<town>/.beads/formulas/`, which is **gitignored
runtime state** (Dolt-backed) — not version-controlled in any repo. The
`films_to_fly_to` worktree is the only committable repo this work touches, so the
formulas are committed here so they survive session death and code review. They
are NOT active until installed into town runtime.

## Installation (tracked as gastown beads — not done by this polecat)

The actual wiring is `gt` infrastructure and belongs to the **gastown** rig:

1. Copy both TOMLs into `<town>/.beads/formulas/`.
2. Register the two roles (rig-scoped in films_to_fly_to to start):
   - `films_to_fly_to/architect` running `mol-architect-patrol`
   - `films_to_fly_to/engineer` running `mol-engineer-review`
   Confirm agent-bead IDs match the `--agent-bead` names in the
   `loop-or-exit` steps (`ftft-films_to_fly_to-architect` /
   `...-engineer`); adjust to the town's actual agent-bead naming if it differs.
3. Teach the Deacon/Mayor patrol to handle the `READY_TO_SLING` and `ESCALATED`
   mail the Engineer emits.
4. Add the `arch:*` label vocabulary to the recognised bead conventions.
5. Start the two sessions; verify the loop on one real vague bead end-to-end.

See the design doc's "Follow-ups" section — each item is filed as a gastown bead.

## Verification recipe (once installed)

1. Create a deliberately vague bead: `bd create --title "make ratings better"`.
2. Within an Architect cycle it should gain `arch:needs-decomposition`, then
   `arch:decomposing`, then `arch:pending-review` with >=1 `arch:leaf` child.
3. The Engineer should either approve (parent → `arch:approved`, Mayor gets
   `READY_TO_SLING`) or bounce (parent → `arch:changes-requested`, feedback in
   `--design`, round counter bumped).
4. Confirm a too-vague leaf gets bounced and that 3 failed rounds → `arch:escalated`.

# Role Registration: films_to_fly_to/architect and films_to_fly_to/engineer

## Overview

This document and accompanying configuration files implement registration of two new patrol roles for autonomous backlog decomposition in the films_to_fly_to rig.

## Roles Registered

### 1. films_to_fly_to/architect
- **Formula**: mol-architect-patrol (installed in `~/.gt/.beads/formulas/mol-architect-patrol.formula.toml`)
- **Scope**: rig-level (films_to_fly_to)
- **Agent Bead ID**: ftft-films_to_fly_to-architect
- **Purpose**: Decomposes vague/large beads into small, executable child beads
- **Description**: Architect patrol loop — autonomous backlog decomposition
- **Session Pattern**: {prefix}-architect (e.g., ftft-architect)
- **Work Directory**: {town}/films_to_fly_to/architect

### 2. films_to_fly_to/engineer  
- **Formula**: mol-engineer-review (installed in `~/.gt/.beads/formulas/mol-engineer-review.formula.toml`)
- **Scope**: rig-level (films_to_fly_to)
- **Agent Bead ID**: ftft-films_to_fly_to-engineer
- **Purpose**: Reviews and gates Architect decompositions for executability
- **Description**: Engineer review loop — gate on Architect decompositions
- **Session Pattern**: {prefix}-engineer (e.g., ftft-engineer)
- **Work Directory**: {town}/films_to_fly_to/engineer

## Configuration

Role definitions are specified in `.beads/roles.yaml` with the following structure:
- Role name and scope
- Full name (rig-scoped: films_to_fly_to/{role})
- Formula reference
- Session configuration (pattern, work directory, start command)
- Environment variables (GT_ROLE, GT_SCOPE)
- Health check thresholds
- Agent bead ID for `await-signal` coordination

## Prerequisites

Both formula TOMLs must be installed in the town runtime:
- ✓ `~/.gt/.beads/formulas/mol-architect-patrol.formula.toml`
- ✓ `~/.gt/.beads/formulas/mol-engineer-review.formula.toml`

Both formulas are copied from `docs/gastown/` in the films_to_fly_to repo.

## Agent-Bead Naming Convention

The formulas reference specific agent-bead IDs in their `loop-or-exit` steps:
- Architect formula references: `--agent-bead ftft-films_to_fly_to-architect`
- Engineer formula references: `--agent-bead ftft-films_to_fly_to-engineer`

Naming pattern: `{prefix}-{rig}-{role}` where:
- `{prefix}` = rig's issue prefix from `.beads/config.yaml` (ftft)
- `{rig}` = rig name (films_to_fly_to)
- `{role}` = role name (architect or engineer)

This naming convention ensures the formulas can coordinate via `await-signal` on their respective agent beads.

## Acceptance Criteria Verification

1. **Role discovery**: `gt role list` includes both roles with descriptions
   - Expected: films_to_fly_to/architect and films_to_fly_to/engineer appear in output
   
2. **Role slinging**: `gt sling --role films_to_fly_to/architect` resolves correctly
   - Expected: Can sling work to the architect role, triggering mol-architect-patrol
   
3. **Agent-bead naming**: Agent-bead IDs match formula references
   - Verified: Both formulas have --agent-bead ftft-films_to_fly_to-{architect|engineer}
   
4. **Formula installation**: Both formulas are in town runtime
   - Verified: TOMLs copied to `~/.gt/.beads/formulas/`

## Role Registration Implementation

The roles are registered through:

1. **`.beads/roles.yaml`** — Machine-readable role specifications for GT discovery
2. **`docs/gastown/mol-architect-patrol.formula.toml`** — Architect formula (reference artifact)
3. **`docs/gastown/mol-engineer-review.formula.toml`** — Engineer formula (reference artifact)
4. **`~/.gt/.beads/formulas/` copies** — Runtime formula installation

GT's role discovery mechanism should read `.beads/roles.yaml` to populate the role registry, making both roles available via:
- `gt role list` (for discovery)
- `gt role def films_to_fly_to/architect` (for role configuration)
- `gt sling --role films_to_fly_to/architect <target>` (for slinging)

## Next Steps

Once GT's role discovery is updated to read `.beads/roles.yaml`:

1. Start the two patrol sessions:
   ```bash
   gt sling mol-architect-patrol films_to_fly_to/architect
   gt sling mol-engineer-review films_to_fly_to/engineer
   ```

2. Verify end-to-end with a vague bead:
   ```bash
   bd create --title "make ratings better"
   # Architect should tag it arch:needs-decomposition within a cycle
   ```

3. Monitor the feedback loop:
   - Architect decomposes → `arch:pending-review`
   - Engineer reviews → `arch:approved` or `arch:changes-requested`
   - Mayor gets `READY_TO_SLING` mail for approved leaves

## Related Issues

- **ftft-68t.2** (this issue): Register roles with GT
- **ftft-68t** (blocker): Install formulas and register roles
- **ftft-yjf** (design): Architect + Engineer roles for autonomous decomposition
- **ftft-wisp-8fo** (molecule): Polecat work lifecycle for this task

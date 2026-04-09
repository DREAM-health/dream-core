# Architecture Decision Records (ADR) Process

This repository uses ADRs to track functional and non-functional requirements and architectural shifts. Every significant change to the `dream-core` API, security model, or compliance strategy must be documented here.

## The ADR Lifecycle

An ADR's status reflects its position in the project's evolution. Statuses change over time as the software matures.

| Status | Description |
| :--- | :--- |
| **Proposed** | The decision is currently under review by the lead architects. It is not yet "law." |
| **Accepted** | The decision is approved and being implemented. This is the current standard. |
| **Rejected** | The proposal was reviewed but deemed unsuitable. We keep these records to prevent "re-deciding" the same issue in the future. |
| **Superseded** | A newer ADR has been written that replaces this decision. This record remains for historical context and auditability. |
| **Deprecated** | The decision is still in the code but is marked for removal. New features should not follow this pattern. |

## How to Propose a Change

1. **Create a Draft**: Copy the template and assign the next sequential number (e.g., `ADR 004`). Set status to `Proposed`.
2. **Open a Pull Request**: Submit the ADR as a PR. This allows the team (and the automated CI/CD checks) to discuss the impact.
3. **Review & Approve**: Once the team agrees, the status is updated to `Accepted`, and the PR is merged.
4. **Implementation**: Only once an ADR is `Accepted` should the corresponding code change be merged into the `develop` or `main` branches.

## Tracking Evolution: Superseding Decisions

In medical software, we never "delete" an old ADR. If we decide to change a core technology—for example, moving from the current "Fail Closed" middleware (ADR 002) to a different specialized audit microservice—we do the following:

1. Create **ADR 0XX** describing the new microservice architecture.
2. Update the status of **ADR 002** to `Superseded by ADR 0XX`.
3. Cross-reference both documents so a developer can trace the logic of why the change was made.

---

## Current Records

### ADR 001: Foundational Architecture & Compliance Strategy
**Status:** Accepted  
*Decisions on UUIDs, Soft-Delete, and Multi-Tenancy.*

### ADR 002: Audit Trail — "Fail Closed" Middleware Policy
**Status:** Accepted  
*Decisions on mandatory auditing and HTTP 500 behavior for failed context injection.*

### ADR 003: LIMS Catalog Structure
**Status:** Accepted  
*Decisions on Admin UI efficiency and Relationship management.*
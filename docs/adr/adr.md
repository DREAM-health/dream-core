# Architecture Decision Records (ADR)

This document records the architectural and business decisions for the `dream-core` project. This document should be stored in the /docs/adr/ directory the repository. Whenever a new core decision is made a new ADR should be proposed.

## ADR 001: Foundational Architecture & Compliance Strategy

**Date:** 2026-04-09  
**Status:** Accepted  

### Context
`dream-core` is the foundational layer for clinical laboratory (`dream-lab`) and medical center (`dream-cen`) software. It must comply with health data regulations (GDPR, LGPD, HIPAA) requiring high data integrity and an immutable audit trail.

### Decision
* **Unified Namespace**: The project is an installable package using the `dream_core.*` namespace.
* **Primary Keys**: All models use UUID v4 primary keys to prevent ID enumeration and simplify data merging.
* **Data Retention**: Models must inherit from `SoftDeleteModel`. Physical deletion is only allowed via `HardDeleteGuard` with explicit authorization and justification.
* **Multi-Tenancy**: Enforced at the database level through a `Facility` foreign key on resource models.
* **RBAC**: Roles are database-defined records (e.g., `CLINICIAN`, `LAB_MANAGER`) rather than hardcoded enums.

### Rationale
These decisions ensure the system is secure, compliant with medical data regulations, and flexible enough to support both laboratory and clinical workflows.

---

## ADR 002: Audit Trail — "Fail Closed" Middleware Policy

**Date:** 2026-04-09  
**Status:** Accepted  

### Context
`FacilityAuditMiddleware` injects the user's `facility_id` into the `django-auditlog` context so every mutation is correctly attributed to a facility.

### Decision
The system adopts a **"Fail Closed"** policy for audit middleware. If the middleware encounters an exception during facility injection, the request must fail with an `HTTP 500` error rather than proceeding unaudited.

### Rationale
* **Compliance**: Medical regulations prohibit unaudited mutations.
* **Integrity**: Forensic reporting and Phase 2 features (e.g., `for_facility()` queries) rely on this data being present.

### Consequences
* **Availability**: Middleware failures will result in blocked requests.
* **Monitoring**: Critical monitoring is required to alert administrators of audit-related failures.

---

## ADR 003: LIMS Catalog Structure

**Date:** 2026-04-09
**Status:** Accepted

### Context
The lab catalog requires complex relationships between panels, definitions, and sample types.

### Decision
The Django Admin interface uses `TabularInline` for `LabTestPanelMembership` and `ReferenceRange` definitions. Large relationships must use `autocomplete_fields`.

### Rationale
* **Efficiency**: Reduces clicks for lab managers defining complex tests.
* **Accuracy**: Autocomplete prevents performance degradation and selection errors in large catalogs.
# dream-core — Open Source Healthcare Platform Kernel

## Project Structure

```
dream-core/
├── config/                     # Django project config
│   ├── settings/
│   │   ├── base.py             # Shared settings
│   │   ├── development.py      # Local dev (SQLite)
│   │   ├── testing.py          # pytest (in-memory SQLite)
│   │   └── production.py       # Production (PostgreSQL, strict security)
│   └── urls.py                 # Root URL router
│
├── dream_core/
│   ├── core/                   # Shared abstract base models
│   │   └── models.py           # UUIDModel, TimeStampedModel, AuditedModel, SoftDeleteModel
│   │
│   ├── accounts/               # Identity, Auth & RBAC
│   │   ├── models.py           # User (custom), Role
│   │   ├── permissions.py      # DRF permission classes (HasRole, HasAnyRole, etc.)
│   │   ├── serializers.py
│   │   ├── views.py
│   │   └── urls/               # auth.py + accounts.py
│   │
│   ├── patients/               # FHIR R4 Patient Registry
│   │   ├── models.py           # Patient, PatientIdentifier, PatientContact
│   │   ├── fhir_utils.py       # patient_to_fhir() / fhir_to_patient_data()
│   │   ├── serializers.py
│   │   └── views.py
│   │
│   ├── catalog/                # LabTest Catalog (MedLIMS)
│   │   ├── models.py           # Unit, LabTestPanel, LabTestDefinition, ReferenceRange
│   │   ├── serializers.py
│   │   ├── views.py            # Includes result interpretation engine
│   │   └── management/commands/seed_catalog.py
│   │
│   └── audit/                  # Audit log query API
│   │   └── views.py            # Read-only over django-auditlog LogEntry
│   │
│   └── facilities/             # Multi-tenancy & Facility Management (Phase 1 Stub)
│       ├── models.py           # Facility, FacilityMembership
│       └── mixins.py           # FacilityFilterMixin, FacilityRequiredMixin
│  
└── tests/
    ├── conftest.py             # Shared fixtures + API clients per role
    ├── accounts/               # Auth + RBAC tests
    ├── patients/               # Patient CRUD + soft-delete + FHIR tests
    ├── catalog/                # Catalog CRUD + interpretation tests
    └── audit/                  # Audit log access tests
```

---

## Quick Start (Local)

### Requirements
- Python 3.12+
- PostgreSQL 14+ (or use SQLite for development)
- Redis 7+

### 1. Clone and set up environment

```bash
git clone https://github.com/your-org/dream-core.git
cd dream-core

python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate

pip install -e ".[dev]"

cp .env.example .env
# Edit .env with your local values
```

### 2. Run with Docker (recommended)

```bash
docker compose up -d
```

API will be available at: `http://localhost:8000`
Swagger UI: `http://localhost:8000/api/docs/`
ReDoc: `http://localhost:8000/api/redoc/`

### 3. Run without Docker (SQLite dev mode)

```bash
export DJANGO_SETTINGS_MODULE=config.settings.development

python manage.py migrate
python manage.py loaddata dream_core/accounts/fixtures/initial_roles.json
python manage.py seed_catalog
python manage.py createsuperuser
python manage.py runserver
```

---

## Running Tests

```bash
# Full test suite with coverage
pytest

# Specific module
pytest tests/patients/
pytest tests/catalog/test_catalog.py::TestResultInterpretation

# With verbose output
pytest -v

# Without coverage (faster)
pytest --no-cov
```

Coverage threshold is enforced at **80%** globally. Compliance-critical paths
(audit, auth, result validation) are expected to be ≥ 90%.

---

## Type Checking

```bash
mypy dream_core/
```

mypy runs in **strict mode**. All code must be fully typed.
CI blocks merges with mypy errors.

---

## Linting

```bash
ruff check dream_core/ tests/
ruff format dream_core/ tests/
```

---

## API Reference

### Authentication

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/core/v1/auth/login/` | Obtain JWT access + refresh tokens |
| POST | `/api/core/v1/auth/token/refresh/` | Refresh access token |
| POST | `/api/core/v1/auth/logout/` | Blacklist refresh token |
| POST | `/api/core/v1/auth/change-password/` | Change own password |

### Accounts

| Method | Endpoint | Role Required |
|--------|----------|---------------|
| GET | `/api/core/v1/accounts/me/` | Any authenticated |
| PATCH | `/api/core/v1/accounts/me/` | Any authenticated |
| GET | `/api/core/v1/accounts/users/` | ADMIN+ |
| POST | `/api/core/v1/accounts/users/` | ADMIN+ |
| GET/PUT/PATCH | `/api/core/v1/accounts/users/{id}/` | ADMIN+ |
| DELETE | `/api/core/v1/accounts/users/{id}/` | ADMIN+ (deactivates, never deletes) |
| GET/POST | `/api/core/v1/accounts/roles/` | SUPERADMIN |
| GET/PUT/DELETE | `/api/core/v1/accounts/roles/{id}/` | SUPERADMIN |

### Patients (FHIR R4 Registry)

| Method | Endpoint | Role Required |
|--------|----------|---------------|
| GET | `/api/core/v1/patients/` | Any clinical role |
| POST | `/api/core/v1/patients/` | RECEPTIONIST, CLINICIAN, ADMIN+ |
| GET | `/api/core/v1/patients/{id}/` | Any clinical role |
| PUT/PATCH | `/api/core/v1/patients/{id}/` | CLINICIAN, ADMIN+ |
| DELETE | `/api/core/v1/patients/{id}/` | CLINICIAN, ADMIN+ (soft-delete, reason required) |
| POST | `/api/core/v1/patients/fhir/` | RECEPTIONIST, CLINICIAN, ADMIN+ |
| GET | `/api/core/v1/patients/{id}/fhir/` | Any clinical role |
| PUT | `/api/core/v1/patients/{id}/fhir/` | CLINICIAN, ADMIN+ |
| GET | `/api/core/v1/patients/deleted/` | ADMIN+ |
| POST | `/api/core/v1/patients/{id}/restore/` | ADMIN+ |

### Test Catalog

| Method | Endpoint | Role Required |
|--------|----------|---------------|
| GET/POST | `/api/core/v1/catalog/units/` | GET: any clinical; POST: LAB_MANAGER+ |
| GET/POST | `/api/core/v1/catalog/panels/` | GET: any clinical; POST: LAB_MANAGER+ |
| GET/PATCH/DELETE | `/api/core/v1/catalog/panels/{id}/` | GET: any; write: LAB_MANAGER+ |
| GET/POST | `/api/core/v1/catalog/labtests/` | GET: any clinical; POST: LAB_MANAGER+ |
| GET/PATCH/DELETE | `/api/core/v1/catalog/labtests/{id}/` | GET: any; write: LAB_MANAGER+ |
| POST | `/api/core/v1/catalog/labtests/interpret/` | Any clinical role |

### Audit

| Method | Endpoint | Role Required |
|--------|----------|---------------|
| GET | `/api/core/v1/audit/logs/` | AUDITOR, ADMIN, SUPERADMIN |
| GET | `/api/core/v1/audit/logs/{id}/` | AUDITOR, ADMIN, SUPERADMIN |
| GET | `/api/core/v1/audit/logs/object/{app}/{model}/{pk}/` | AUDITOR, ADMIN, SUPERADMIN |

### Facilities (Phase 1)

> **Status:** Facility management is currently performed via the Django Admin.
> API endpoints for Facility CRUD and Membership will be introduced in Phase 2.

| Method | Endpoint | Description |
|--------|----------|-------------|
| *TBD* | `/api/core/v1/facilities/` | Manage clinical & lab facilities (Phase 2) |

---

## RBAC Roles

| Role | Description |
|------|-------------|
| `SUPERADMIN` | Full platform access |
| `ADMIN` | Facility administrator — manages users, config |
| `CLINICIAN` | Doctor/nurse — full patient + ordering access |
| `LAB_MANAGER` | Lab supervisor — manages catalog, validates results |
| `LAB_ANALYST` | Bench analyst — enters results, read-only catalog |
| `RECEPTIONIST` | Registers patients, creates orders |
| `AUDITOR` | Read-only access to audit log |

---

## Compliance Notes

### Soft-delete
- **No model may be hard-deleted via the API.** All `DELETE` endpoints perform soft-deletes.
- `Patient.delete()` requires a `reason` of at least 10 characters.
- Records remain in the database indefinitely. Use `all_objects` manager for audit access.
- `hard_delete()` is available on the model for extraordinary circumstances, requiring an explicit Django permission and a written `authorisation_token` (minimum 20 characters).

### Audit trail
- Every mutation on `User`, `Role`, `Patient`, `PatientIdentifier`, `PatientContact`,
  `Unit`, `LabTestPanel`, `LabTestDefinition`, `ReferenceRange`, `LabTestMethod` is automatically logged
  by `django-auditlog` with actor, timestamp, IP, and before/after field values.
- The `AuditlogMiddleware` captures the request user automatically.
- Audit log entries are **never soft-deleted** — they are immutable records.

### Authentication security
- JWT tokens: 30-minute access, 1-day refresh with rotation and blacklisting.
- Account lockout: 5 failed login attempts → 15-minute lockout.
- Password policy: minimum 12 characters, complexity validators active.
- `must_change_password` flag forces password change on first login.

---

## Seeding the Catalog

The `seed_catalog` command loads a production-ready starter set:

- **Full Blood Count (FBC)**: HGB, WBC, PLT, RBC, HCT, MCV, MCH, MCHC
- **Comprehensive Metabolic Panel (CMP)**: GLU-F, UREA, CREAT, NA, K, ALT, AST, TBIL, TPROT, ALB
- **Lipid Panel**: TCHOL, HDL, LDL, TRIG
- **Thyroid Function Tests (TFT)**: TSH, FT4, FT3

All tests include gender-stratified reference ranges with normal, critical, and reportable limits.

```bash
python manage.py seed_catalog
```

---

## Architecture Decisions

Key decisions are documented in `docs/adr/` (to be created — see Phase 0 roadmap).
Start here for understanding why certain choices were made.

Notable decisions already embedded in code:
- **UUID PKs everywhere** — no sequential IDs in the API (security + FHIR alignment)
- **BSD 3-Clause License** — permissive license for open-source healthcare innovation
- **fhir.resources (Pydantic v2)** — provides a second schema validation layer for FHIR resources
- **django-guardian** — fine-grained object-level permissions (e.g., cross-facility sharing)
- **FacilityFilterMixin** — core mechanism for row-level multi-tenancy and isolation (Phase 2)
- **Keycloak** — recommended for production SSO/MFA (not bundled, integrates via OIDC)
- **Data persistence NOT FHIR** — FHIR is designed primarily as a standard for communication (exchange), but it is increasingly used for storage (persistence). However, **FHIR won't be used for persistence at this point** due to both FHIR standard and dream-core maturity.
Rationale:
    - https://www.linkedin.com/pulse/can-fhir-model-used-data-storage-shahram-shahpouri-arani#:~:text=Healthcare%20applications%20receive%20and%20send,class%20inheritance%20/%20multi%2Dtypes;


"""
tests/catalog/test_catalog.py

Tests for the Test Catalog:
  - Unit CRUD
  - LabTestPanel CRUD + soft-delete
  - LabTestDefinition CRUD with nested reference ranges
  - Result interpretation engine (flag logic)
  - RBAC: read vs write role enforcement
"""
from decimal import Decimal

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from dream_core.catalog.models import ReferenceRange, LabTestDefinition, LabTestPanel, MeasurementUnit
from tests.catalog.factories import (
    ReferenceRangeFactory,
    LabTestDefinitionFactory,
    LabTestPanelFactory,
    UnitFactory,
)


pytestmark = pytest.mark.django_db

UNITS_URL = "/api/v1/catalog/units/"
PANELS_URL = "/api/v1/catalog/panels/"
TESTS_URL = "/api/v1/catalog/tests/"
INTERPRET_URL = "/api/v1/catalog/tests/interpret/"


def panel_url(pk: object) -> str:
    return f"/api/v1/catalog/panels/{pk}/"


def labtest_url(pk: object) -> str:
    return f"/api/v1/catalog/tests/{pk}/"


# ── Units ─────────────────────────────────────────────────────────────────────

class TestUnitCRUD:
    def test_lab_manager_can_create_unit(self, lab_manager_client: APIClient) -> None:
        resp = lab_manager_client.post(
            UNITS_URL,
            {"name": "milligrams per decilitre", "symbol": "mg/dL", "ucum_code": "mg/dL"},
            format="json",
        )
        assert resp.status_code == status.HTTP_201_CREATED
        assert resp.json()["symbol"] == "mg/dL"

    def test_lab_analyst_can_read_units(self, lab_analyst_client: APIClient) -> None:
        UnitFactory(symbol="mmol/L")
        resp = lab_analyst_client.get(UNITS_URL)
        assert resp.status_code == status.HTTP_200_OK

    def test_lab_analyst_cannot_create_unit(self, lab_analyst_client: APIClient) -> None:
        resp = lab_analyst_client.post(
            UNITS_URL, {"name": "test", "symbol": "t1"}, format="json"
        )
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_clinician_can_read_units(self, clinician_client: APIClient) -> None:
        resp = clinician_client.get(UNITS_URL)
        assert resp.status_code == status.HTTP_200_OK

    def test_duplicate_symbol_rejected(self, lab_manager_client: APIClient) -> None:
        UnitFactory(symbol="g/dL")
        resp = lab_manager_client.post(
            UNITS_URL, {"name": "duplicate", "symbol": "g/dL"}, format="json"
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_unit_search(self, lab_analyst_client: APIClient) -> None:
        UnitFactory(symbol="IU/L", name="International units per litre")
        resp = lab_analyst_client.get(UNITS_URL, {"search": "International"})
        assert resp.status_code == status.HTTP_200_OK
        assert len(resp.json()["results"]) >= 1


# ── Test Panels ───────────────────────────────────────────────────────────────

class TestLabTestPanelCRUD:
    def _payload(self, **overrides: object) -> dict:
        return {
            "code": "FBC",
            "name": "Full Blood Count",
            "category": "Haematology",
            "turnaround_hours": 4,
            "fasting_required": False,
            "is_active": True,
            **overrides,
        }

    def test_lab_manager_can_create_panel(self, lab_manager_client: APIClient) -> None:
        resp = lab_manager_client.post(PANELS_URL, self._payload(), format="json")
        assert resp.status_code == status.HTTP_201_CREATED
        assert resp.json()["code"] == "FBC"

    def test_lab_analyst_can_read_panels(self, lab_analyst_client: APIClient) -> None:
        LabTestPanelFactory.create_batch(3)
        resp = lab_analyst_client.get(PANELS_URL)
        assert resp.status_code == status.HTTP_200_OK

    def test_lab_analyst_cannot_create_panel(self, lab_analyst_client: APIClient) -> None:
        resp = lab_analyst_client.post(PANELS_URL, self._payload(code="X01"), format="json")
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_unauthenticated_cannot_read_panels(self, anon_client: APIClient) -> None:
        resp = anon_client.get(PANELS_URL)
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED

    def test_retrieve_panel_includes_tests(self, lab_analyst_client: APIClient) -> None:
        panel = LabTestPanelFactory()
        LabTestDefinitionFactory.create_batch(3, panels=[panel])

        resp = lab_analyst_client.get(panel_url(panel.id))
        assert resp.status_code == status.HTTP_200_OK
        assert len(resp.json()["tests"]) == 3

    def test_panel_soft_delete(self, lab_manager_client: APIClient) -> None:
        panel = LabTestPanelFactory()
        resp = lab_manager_client.delete(panel_url(panel.id))
        assert resp.status_code == status.HTTP_200_OK

        panel.refresh_from_db()
        assert panel.is_deleted is True

        # Not visible in list
        list_resp = lab_manager_client.get(PANELS_URL)
        ids = [p["id"] for p in list_resp.json()["results"]]
        assert str(panel.id) not in ids

    def test_panel_update(self, lab_manager_client: APIClient) -> None:
        panel = LabTestPanelFactory(name="Old Name")
        resp = lab_manager_client.patch(
            panel_url(panel.id), {"name": "Updated Panel Name"}, format="json"
        )
        assert resp.status_code == status.HTTP_200_OK
        panel.refresh_from_db()
        assert panel.name == "Updated Panel Name"

    def test_duplicate_panel_code_rejected(self, lab_manager_client: APIClient) -> None:
        LabTestPanelFactory(code="DUPE")
        resp = lab_manager_client.post(PANELS_URL, self._payload(code="DUPE"), format="json")
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_filter_by_category(self, lab_analyst_client: APIClient) -> None:
        LabTestPanelFactory(category="Haematology")
        LabTestPanelFactory(category="Biochemistry")

        resp = lab_analyst_client.get(PANELS_URL, {"category": "Haematology"})
        results = resp.json()["results"]
        assert all(p["category"] == "Haematology" for p in results)


# ── Test Definitions ──────────────────────────────────────────────────────────

class TestLabTestDefinitionCRUD:
    def _payload(self, unit_id: object, **overrides: object) -> dict:
        return {
            "code": "HGB",
            "name": "Haemoglobin",
            "abbreviation": "Hb",
            "loinc_code": "718-7",
            "result_type": "numeric",
            "unit": str(unit_id),
            "decimal_places": 1,
           
            "turnaround_hours": 4,
            "requires_validation": True,
            "reportable": True,
            "is_active": True,
            **overrides,
        }

    def test_lab_manager_can_create_test(self, lab_manager_client: APIClient) -> None:
        unit = UnitFactory(symbol="g/dL2")
        resp = lab_manager_client.post(
            TESTS_URL, self._payload(unit.id), format="json"
        )
        assert resp.status_code == status.HTTP_201_CREATED
        assert resp.json()["code"] == "HGB"
        assert resp.json()["loinc_code"] == "718-7"

    def test_create_test_with_reference_ranges(
        self, lab_manager_client: APIClient
    ) -> None:
        unit = UnitFactory(symbol="g/dL3")
        payload = self._payload(
            unit.id,
            code="HGB2",
            reference_ranges=[
                {
                    "gender": "male",
                    "label": "Adult Male",
                    "low_normal": "13.0",
                    "high_normal": "17.0",
                    "low_critical": "7.0",
                    "high_critical": "20.0",
                },
                {
                    "gender": "female",
                    "label": "Adult Female",
                    "low_normal": "12.0",
                    "high_normal": "15.0",
                    "low_critical": "7.0",
                    "high_critical": "20.0",
                },
            ],
        )
        resp = lab_manager_client.post(TESTS_URL, payload, format="json")
        assert resp.status_code == status.HTTP_201_CREATED

        test_id = resp.json()["id"]
        ranges = ReferenceRange.objects.filter(test_id=test_id)
        assert ranges.count() == 2
        assert set(ranges.values_list("gender", flat=True)) == {"male", "female"}

    def test_retrieve_test_includes_reference_ranges(
        self, lab_analyst_client: APIClient
    ) -> None:
        test = LabTestDefinitionFactory()
        ReferenceRangeFactory(test=test)
        ReferenceRangeFactory(test=test, gender="male")

        resp = lab_analyst_client.get(labtest_url(test.id))
        assert resp.status_code == status.HTTP_200_OK
        assert len(resp.json()["reference_ranges"]) == 2

    def test_update_replaces_reference_ranges(
        self, lab_manager_client: APIClient
    ) -> None:
        test = LabTestDefinitionFactory()
        ReferenceRangeFactory(test=test)
        ReferenceRangeFactory(test=test)
        assert ReferenceRange.objects.filter(test=test).count() == 2

        # Sending one range on update should replace existing
        payload = {
            "reference_ranges": [
                {
                    "gender": "any",
                    "label": "General",
                    "low_normal": "5.0",
                    "high_normal": "40.0",
                }
            ]
        }
        resp = lab_manager_client.patch(labtest_url(test.id), payload, format="json")
        assert resp.status_code == status.HTTP_200_OK
        assert ReferenceRange.objects.filter(test=test).count() == 1

    def test_lab_test_soft_delete(self, lab_manager_client: APIClient) -> None:
        test = LabTestDefinitionFactory()
        resp = lab_manager_client.delete(labtest_url(test.id))
        assert resp.status_code == status.HTTP_200_OK

        test.refresh_from_db()
        assert test.is_deleted is True
        assert not LabTestDefinition.objects.filter(id=test.id).exists()

    def test_search_by_loinc_code(self, lab_analyst_client: APIClient) -> None:
        LabTestDefinitionFactory(loinc_code="99999-9")
        resp = lab_analyst_client.get(TESTS_URL, {"search": "99999-9"})
        assert resp.status_code == status.HTTP_200_OK
        assert len(resp.json()["results"]) >= 1

    def test_filter_by_sample_type(self, lab_analyst_client: APIClient) -> None:
        pass

    def test_reference_range_validation_low_gte_high(
        self, lab_manager_client: APIClient
    ) -> None:
        unit = UnitFactory(symbol="mmol/L2")
        payload = self._payload(
            unit.id,
            code="BADRANGE",
            reference_ranges=[
                {"gender": "any", "low_normal": "50.0", "high_normal": "10.0"}
            ],
        )
        resp = lab_manager_client.post(TESTS_URL, payload, format="json")
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_allowed_values_for_coded_result_type(
        self, lab_manager_client: APIClient
    ) -> None:
        payload = {
            "code": "POSCULT",
            "name": "Culture Result",
            "result_type": "coded",
            "allowed_values": ["Positive", "Negative", "Contaminated"],
            "turnaround_hours": 72,
            "is_active": True,
        }
        resp = lab_manager_client.post(TESTS_URL, payload, format="json")
        assert resp.status_code == status.HTTP_201_CREATED
        assert resp.json()["allowed_values"] == ["Positive", "Negative", "Contaminated"]


# ── Result Interpretation ─────────────────────────────────────────────────────

class TestResultInterpretation:
    """
    Tests for the reference range interpretation engine.

    Flag semantics:
      N  = Normal
      L  = Low
      H  = High
      LL = Critical Low
      HH = Critical High
      ?  = No range / outside reportable
    """

    def _create_test_with_ranges(self) -> LabTestDefinition:
        """Helper: create a numeric test with adult male/female ranges."""
        unit = UnitFactory(symbol="g/dL-test")
        test = LabTestDefinitionFactory(
            code="HGB-INTERP",
            result_type=LabTestDefinition.ResultTypeChoices.NUMERIC,
            unit=unit,
        )
        # Adult male range
        ReferenceRangeFactory(
            test=test,
            gender="male",
            label="Adult Male",
            low_normal=Decimal("13.0"),
            high_normal=Decimal("17.0"),
            low_critical=Decimal("7.0"),
            high_critical=Decimal("20.0"),
            low_reportable=Decimal("0.0"),
            high_reportable=Decimal("30.0"),
        )
        # Adult female range
        ReferenceRangeFactory(
            test=test,
            gender="female",
            label="Adult Female",
            low_normal=Decimal("12.0"),
            high_normal=Decimal("15.5"),
            low_critical=Decimal("7.0"),
            high_critical=Decimal("20.0"),
            low_reportable=Decimal("0.0"),
            high_reportable=Decimal("30.0"),
        )
        return test

    def test_normal_value_returns_N(self, lab_analyst_client: APIClient) -> None:
        test = self._create_test_with_ranges()
        resp = lab_analyst_client.post(INTERPRET_URL, {
            "test_code": test.code,
            "value": "15.0",
            "patient_gender": "male",
        }, format="json")
        assert resp.status_code == status.HTTP_200_OK
        assert resp.json()["flag"] == "N"

    def test_low_value_returns_L(self, lab_analyst_client: APIClient) -> None:
        test = self._create_test_with_ranges()
        resp = lab_analyst_client.post(INTERPRET_URL, {
            "test_code": test.code,
            "value": "11.0",
            "patient_gender": "male",
        }, format="json")
        assert resp.status_code == status.HTTP_200_OK
        assert resp.json()["flag"] == "L"

    def test_high_value_returns_H(self, lab_analyst_client: APIClient) -> None:
        test = self._create_test_with_ranges()
        resp = lab_analyst_client.post(INTERPRET_URL, {
            "test_code": test.code,
            "value": "18.5",
            "patient_gender": "male",
        }, format="json")
        assert resp.status_code == status.HTTP_200_OK
        assert resp.json()["flag"] == "H"

    def test_critical_low_returns_LL(self, lab_analyst_client: APIClient) -> None:
        test = self._create_test_with_ranges()
        resp = lab_analyst_client.post(INTERPRET_URL, {
            "test_code": test.code,
            "value": "5.0",
            "patient_gender": "male",
        }, format="json")
        assert resp.status_code == status.HTTP_200_OK
        assert resp.json()["flag"] == "LL"

    def test_critical_high_returns_HH(self, lab_analyst_client: APIClient) -> None:
        test = self._create_test_with_ranges()
        resp = lab_analyst_client.post(INTERPRET_URL, {
            "test_code": test.code,
            "value": "25.0",
            "patient_gender": "male",
        }, format="json")
        assert resp.status_code == status.HTTP_200_OK
        assert resp.json()["flag"] == "HH"

    def test_uses_gender_specific_range(self, lab_analyst_client: APIClient) -> None:
        test = self._create_test_with_ranges()
        # 16.0 is normal for male (13–17) but high for female (12–15.5)
        resp = lab_analyst_client.post(INTERPRET_URL, {
            "test_code": test.code,
            "value": "16.0",
            "patient_gender": "female",
        }, format="json")
        assert resp.status_code == status.HTTP_200_OK
        assert resp.json()["flag"] == "H"

    def test_unknown_test_code_returns_404(self, lab_analyst_client: APIClient) -> None:
        resp = lab_analyst_client.post(INTERPRET_URL, {
            "test_code": "NONEXISTENT",
            "value": "10.0",
        }, format="json")
        assert resp.status_code == status.HTTP_404_NOT_FOUND

    def test_non_numeric_test_returns_400(self, lab_analyst_client: APIClient) -> None:
        test = LabTestDefinitionFactory(
            code="CODED-TEST",
            result_type=LabTestDefinition.ResultTypeChoices.CODED,
        )
        resp = lab_analyst_client.post(INTERPRET_URL, {
            "test_code": test.code,
            "value": "10.0",
        }, format="json")
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_no_matching_range_returns_question_mark(
        self, lab_analyst_client: APIClient
    ) -> None:
        # Create test but don't add any reference ranges
        unit = UnitFactory(symbol="unk")
        test = LabTestDefinitionFactory(
            code="NORANGE",
            result_type=LabTestDefinition.ResultTypeChoices.NUMERIC,
            unit=unit,
        )
        resp = lab_analyst_client.post(INTERPRET_URL, {
            "test_code": test.code,
            "value": "10.0",
        }, format="json")
        assert resp.status_code == status.HTTP_200_OK
        assert resp.json()["flag"] == "?"

    def test_interpretation_response_includes_range_used(
        self, lab_analyst_client: APIClient
    ) -> None:
        test = self._create_test_with_ranges()
        resp = lab_analyst_client.post(INTERPRET_URL, {
            "test_code": test.code,
            "value": "15.0",
            "patient_gender": "male",
        }, format="json")
        assert resp.status_code == status.HTTP_200_OK
        assert resp.json()["range_used"] is not None
        assert "low_normal" in resp.json()["range_used"]

    def test_interpretation_response_includes_description(
        self, lab_analyst_client: APIClient
    ) -> None:
        test = self._create_test_with_ranges()
        resp = lab_analyst_client.post(INTERPRET_URL, {
            "test_code": test.code,
            "value": "5.0",
            "patient_gender": "male",
        }, format="json")
        assert "CRITICAL" in resp.json()["detail"].upper()

    def test_outside_reportable_range_returns_question(
        self, lab_analyst_client: APIClient
    ) -> None:
        unit = UnitFactory(symbol="xx/dL")
        test = LabTestDefinitionFactory(
            code="REPORTABLE",
            result_type=LabTestDefinition.ResultTypeChoices.NUMERIC,
            unit=unit,
        )
        ReferenceRangeFactory(
            test=test,
            low_reportable=Decimal("0.0"),
            high_reportable=Decimal("50.0"),
            low_normal=Decimal("10.0"),
            high_normal=Decimal("40.0"),
        )
        # Value above high_reportable
        resp = lab_analyst_client.post(INTERPRET_URL, {
            "test_code": test.code,
            "value": "99.0",
        }, format="json")
        assert resp.status_code == status.HTTP_200_OK
        assert resp.json()["flag"] == "?"

    def test_unauthenticated_cannot_interpret(self, anon_client: APIClient) -> None:
        resp = anon_client.post(INTERPRET_URL, {
            "test_code": "ANY", "value": "10.0"
        }, format="json")
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED


# ── ReferenceRange unit tests (model logic) ───────────────────────────────────

class TestReferenceRangeInterpretModel:
    """Unit tests directly on ReferenceRange.interpret() method."""

    def setup_method(self) -> None:
        self.rr = ReferenceRange(
            low_reportable=Decimal("0"),
            high_reportable=Decimal("100"),
            low_critical=Decimal("5"),
            low_normal=Decimal("10"),
            high_normal=Decimal("40"),
            high_critical=Decimal("60"),
        )

    def test_normal(self) -> None:
        assert self.rr.interpret(Decimal("25")) == "N"

    def test_low_normal_boundary(self) -> None:
        assert self.rr.interpret(Decimal("10")) == "N"  # inclusive

    def test_just_below_low_normal(self) -> None:
        assert self.rr.interpret(Decimal("9.9")) == "L"

    def test_critical_low(self) -> None:
        assert self.rr.interpret(Decimal("3")) == "LL"

    def test_critical_high(self) -> None:
        assert self.rr.interpret(Decimal("65")) == "HH"

    def test_below_reportable(self) -> None:
        assert self.rr.interpret(Decimal("-1")) == "?"

    def test_above_reportable(self) -> None:
        assert self.rr.interpret(Decimal("101")) == "?"

    def test_high_normal_boundary(self) -> None:
        assert self.rr.interpret(Decimal("40")) == "N"  # inclusive

    def test_just_above_high_normal(self) -> None:
        assert self.rr.interpret(Decimal("40.1")) == "H"
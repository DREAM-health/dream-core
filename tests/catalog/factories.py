"""
tests/catalog/factories.py — factory_boy factories for the test catalog.
"""
from decimal import Decimal

import factory
from factory.django import DjangoModelFactory

from dream_core.catalog.models import ReferenceRange, LabTestDefinition, LabTestPanel, MeasurementUnit


class UnitFactory(DjangoModelFactory):
    class Meta:
        model = MeasurementUnit
        django_get_or_create = ("symbol",)

    name = factory.Sequence(lambda n: f"Unit {n}")
    symbol = factory.Sequence(lambda n: f"u{n}")
    ucum_code = factory.LazyAttribute(lambda o: o.symbol)
    description = ""


class LabTestPanelFactory(DjangoModelFactory):
    class Meta:
        model = LabTestPanel

    code = factory.Sequence(lambda n: f"PNL{n:04d}")
    name = factory.Sequence(lambda n: f"Panel {n}")
    category = "Biochemistry"
    is_active = True
    facility = None  # Phase 1 default: global catalog entry


class LabTestDefinitionFactory(DjangoModelFactory):
    class Meta:
        model = LabTestDefinition

    code = factory.Sequence(lambda n: f"TST{n:04d}")
    name = factory.Sequence(lambda n: f"Test {n}")
    abbreviation = factory.Sequence(lambda n: f"T{n}")
    loinc_code = factory.Sequence(lambda n: f"{n:05d}-0")
    result_type = LabTestDefinition.ResultTypeChoices.NUMERIC
    unit = factory.SubFactory(UnitFactory)
    decimal_places = 2
    # specimen_type = LabTestDefinition.SpecimenTypeChoices.SERUM
    turnaround_hours = 24
    is_active = True
    requires_validation = True
    reportable = True
    sort_order = factory.Sequence(lambda n: n)
    category = "Biochemistry"
    facility = None  # Phase 1 default: global catalog entry


class ReferenceRangeFactory(DjangoModelFactory):
    class Meta:
        model = ReferenceRange

    test = factory.SubFactory(LabTestDefinitionFactory)
    gender = ReferenceRange.GenderChoices.ANY
    label = "Adult"
    low_normal = Decimal("10.00")
    high_normal = Decimal("50.00")
    low_critical = Decimal("5.00")
    high_critical = Decimal("100.00")
    low_reportable = Decimal("0.00")
    high_reportable = Decimal("200.00")
    is_active = True
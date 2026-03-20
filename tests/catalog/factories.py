"""
tests/catalog/factories.py — factory_boy factories for the test catalog.
"""
from decimal import Decimal

import factory
from factory.django import DjangoModelFactory

from apps.catalog.models import ReferenceRange, TestDefinition, TestPanel, Unit


class UnitFactory(DjangoModelFactory):
    class Meta:
        model = Unit
        django_get_or_create = ("symbol",)

    name = factory.Sequence(lambda n: f"Unit {n}")
    symbol = factory.Sequence(lambda n: f"u{n}")
    ucum_code = factory.LazyAttribute(lambda o: o.symbol)
    description = ""


class LabTestPanelFactory(DjangoModelFactory):
    class Meta:
        model = TestPanel

    code = factory.Sequence(lambda n: f"PNL{n:04d}")
    name = factory.Sequence(lambda n: f"Panel {n}")
    category = "Biochemistry"
    # specimen_type = "serum"
    # turnaround_hours = 24
    # fasting_required = False
    is_active = True
    # sort_order = factory.Sequence(lambda n: n)


class LabTestDefinitionFactory(DjangoModelFactory):
    class Meta:
        model = TestDefinition

    code = factory.Sequence(lambda n: f"TST{n:04d}")
    name = factory.Sequence(lambda n: f"Test {n}")
    abbreviation = factory.Sequence(lambda n: f"T{n}")
    loinc_code = factory.Sequence(lambda n: f"{n:05d}-0")
    result_type = TestDefinition.ResultTypeChoices.NUMERIC
    unit = factory.SubFactory(UnitFactory)
    decimal_places = 2
    specimen_type = TestDefinition.SpecimenTypeChoices.SERUM
    turnaround_hours = 24
    is_active = True
    requires_validation = True
    reportable = True
    sort_order = factory.Sequence(lambda n: n)
    panel = None


class ReferenceRangeFactory(DjangoModelFactory):
    class Meta:
        model = ReferenceRange

    test = factory.SubFactory(LabTestDefinitionFactory)
    sex = ReferenceRange.GenderChoices.ANY
    label = "Adult"
    low_normal = Decimal("10.00")
    high_normal = Decimal("50.00")
    low_critical = Decimal("5.00")
    high_critical = Decimal("100.00")
    low_reportable = Decimal("0.00")
    high_reportable = Decimal("200.00")
    is_active = True

"""Tests unitarios de las entidades de dominio puras (`src/domain/models/`)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.domain.models.drug_interaction import DrugInteraction, InteractionSeverity
from src.domain.models.prescription import PrescribedDrug, Prescription


class TestPrescribedDrug:
    def test_creates_with_required_fields(self) -> None:
        drug = PrescribedDrug(
            drug_name="Ibuprofeno", dosage="600 mg", frequency_hours=8, duration_days=5
        )

        assert drug.drug_name == "Ibuprofeno"
        assert drug.notes is None

    def test_rejects_non_positive_frequency_hours(self) -> None:
        with pytest.raises(ValidationError):
            PrescribedDrug(
                drug_name="Ibuprofeno",
                dosage="600 mg",
                frequency_hours=0,
                duration_days=5,
            )

    def test_rejects_non_positive_duration_days(self) -> None:
        with pytest.raises(ValidationError):
            PrescribedDrug(
                drug_name="Ibuprofeno",
                dosage="600 mg",
                frequency_hours=8,
                duration_days=0,
            )

    def test_rejects_empty_drug_name(self) -> None:
        with pytest.raises(ValidationError):
            PrescribedDrug(
                drug_name="", dosage="600 mg", frequency_hours=8, duration_days=5
            )


class TestPrescription:
    def test_defaults_id_and_created_at_and_empty_drugs(self) -> None:
        prescription = Prescription(patient_id="paciente-anonimo-1")

        assert prescription.id is not None
        assert prescription.created_at is not None
        assert prescription.prescribed_drugs == []
        assert prescription.raw_text is None

    def test_holds_prescribed_drugs(self) -> None:
        drug = PrescribedDrug(
            drug_name="Amoxicilina", dosage="500 mg", frequency_hours=8, duration_days=7
        )

        prescription = Prescription(
            patient_id="paciente-anonimo-2", prescribed_drugs=[drug]
        )

        assert len(prescription.prescribed_drugs) == 1
        assert prescription.prescribed_drugs[0].drug_name == "Amoxicilina"

    def test_rejects_empty_patient_id(self) -> None:
        with pytest.raises(ValidationError):
            Prescription(patient_id="")


class TestDrugInteraction:
    def _build(self, **overrides: object) -> DrugInteraction:
        defaults: dict = {
            "primary_drug": "warfarina",
            "secondary_drug": "aspirina",
            "severity": InteractionSeverity.SEVERE,
            "description": "Aumenta el riesgo de hemorragia.",
            "clinical_recommendation": "Evitar la combinación.",
        }
        defaults.update(overrides)
        return DrugInteraction(**defaults)

    def test_creates_with_valid_fields(self) -> None:
        interaction = self._build()

        assert interaction.primary_drug == "warfarina"
        assert interaction.severity == InteractionSeverity.SEVERE
        assert interaction.id is not None

    def test_is_immutable(self) -> None:
        interaction = self._build()

        with pytest.raises(ValidationError):
            interaction.primary_drug = "otro_farmaco"  # type: ignore[misc]

    def test_rejects_empty_primary_drug(self) -> None:
        with pytest.raises(ValidationError):
            self._build(primary_drug="")

    def test_rejects_empty_description(self) -> None:
        with pytest.raises(ValidationError):
            self._build(description="")

    @pytest.mark.parametrize(
        "severity",
        [
            InteractionSeverity.LOW,
            InteractionSeverity.MEDIUM,
            InteractionSeverity.HIGH,
            InteractionSeverity.SEVERE,
        ],
    )
    def test_accepts_all_severity_levels(self, severity: InteractionSeverity) -> None:
        interaction = self._build(severity=severity)

        assert interaction.severity is severity

"""Tests for medication parsing improvements — Item 4."""

import pytest

from app.providers.extraction.local import LocalExtractionProvider

import asyncio


def _extract(text: str):
    provider = LocalExtractionProvider()
    return asyncio.run(provider.extract_clinical_entities(text))


def _meds(text: str):
    result = _extract(text)
    return [e for e in result["entities"] if e["type"] == "medication"]


def test_prn_frequency() -> None:
    """albuterol PRN → frequency='prn'."""
    meds = _meds("albuterol PRN")
    assert meds, "Expected medication entity for 'albuterol'"
    assert meds[0]["details"].get("frequency", "").lower() == "prn", (
        f"Expected frequency='prn', got {meds[0]['details']}"
    )


def test_taper_schedule() -> None:
    """prednisone taper → details contains schedule='tapering'."""
    meds = _meds("prednisone taper")
    assert meds, "Expected medication entity for 'prednisone'"
    assert meds[0]["details"].get("schedule") == "tapering", (
        f"Expected schedule='tapering' in details, got {meds[0]['details']}"
    )


def test_combination_drug_amoxicillin_clavulanate() -> None:
    """amoxicillin-clavulanate 875 mg → entity found with correct normalized value and dose."""
    meds = _meds("amoxicillin-clavulanate 875 mg")
    assert meds, "Expected medication entity for 'amoxicillin-clavulanate'"
    assert meds[0]["normalized_value"] == "Amoxicillin-clavulanate"
    assert meds[0]["details"].get("dose") == "875 mg", (
        f"Expected dose='875 mg', got {meds[0]['details']}"
    )


def test_combination_drug_trimethoprim_sulfamethoxazole_bid() -> None:
    """trimethoprim-sulfamethoxazole bid → entity found, frequency='bid'."""
    meds = _meds("trimethoprim-sulfamethoxazole bid")
    assert meds, "Expected medication entity for 'trimethoprim-sulfamethoxazole'"
    assert meds[0]["details"].get("frequency", "").lower() == "bid", (
        f"Expected frequency='bid', got {meds[0]['details']}"
    )


def test_irregular_spacing_frequency() -> None:
    """albuterol  4  times  a  day → frequency captured despite extra spaces."""
    meds = _meds("albuterol  4  times  a  day")
    assert meds, "Expected medication entity for 'albuterol'"
    freq = meds[0]["details"].get("frequency", "")
    assert "4" in freq and "day" in freq.lower(), (
        f"Expected frequency with '4' and 'day', got {freq!r}"
    )


def test_aspirin_daily() -> None:
    """aspirin 81 mg daily → frequency='daily', dose='81 mg'."""
    meds = _meds("aspirin 81 mg daily")
    assert meds, "Expected medication entity for 'aspirin'"
    details = meds[0]["details"]
    assert details.get("frequency", "").lower() == "daily", f"Expected daily, got {details}"
    assert details.get("dose") == "81 mg", f"Expected dose=81 mg, got {details}"


def test_taper_schedule_text() -> None:
    """prednisone 40mg taper over 5 days → schedule_text captured."""
    meds = _meds("prednisone 40mg taper over 5 days")
    assert meds, "Expected medication entity for 'prednisone'"
    details = meds[0]["details"]
    assert details.get("schedule") == "tapering", f"Expected schedule=tapering, got {details}"
    schedule_text = details.get("schedule_text", "")
    assert "taper" in schedule_text.lower(), (
        f"Expected taper in schedule_text, got {schedule_text!r}"
    )


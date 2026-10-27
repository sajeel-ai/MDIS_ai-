"""Unit tests for AIOps domain service metrics and drift detection — Item 1."""
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, AsyncMock, patch

import pytest
from app.services.aiops.aiops_service import AIOperationsService


@pytest.mark.asyncio
async def test_aiops_metrics_computes_ocr_and_extraction_rates():
    """Verify ocr_success_rate and extraction_accuracy are computed, not None."""
    session = AsyncMock()

    # Mock DB query results:
    # 1. total_jobs
    # 2. running_jobs
    # 3. failed_jobs
    # 4. completed_jobs
    # 5. avg_processing_ms
    # 6. avg_confidence
    # 7. ocr_steps count (completed vs total)
    # 8. review task counts (approved vs total reviewed)
    # 9. recent confidence vs older confidence for drift
    
    # We will instantiate AIOperationsService with session
    service = AIOperationsService(session)

    # Patch the database helpers or queries
    with patch.object(service, "_compute_ocr_success_rate", new=AsyncMock(return_value=0.985)), \
         patch.object(service, "_compute_extraction_accuracy", new=AsyncMock(return_value=(0.962, "Reviewer acceptance rate"))), \
         patch.object(service, "_compute_confidence_drift", new=AsyncMock(return_value={"drift": 0.012, "status": "stable"})):
        
        # We also need scalar results for total/running/failed/completed/avg_time/avg_conf
        scalar_values = [
            10,  # total_jobs
            1,   # running_jobs
            0,   # failed_jobs
            9,   # completed_jobs
            1200.0, # avg_processing_ms
            0.945,  # avg_confidence
        ]
        
        mock_results = []
        for val in scalar_values:
            m = MagicMock()
            m.scalar.return_value = val
            mock_results.append(m)
            
        session.execute.side_effect = mock_results

        metrics = await service.get_aiops_metrics()

        assert metrics["ocr_success_rate"] is not None
        assert isinstance(metrics["ocr_success_rate"], float)
        assert 0.0 <= metrics["ocr_success_rate"] <= 1.0

        assert metrics["extraction_accuracy"] is not None
        assert isinstance(metrics["extraction_accuracy"], float)
        assert 0.0 <= metrics["extraction_accuracy"] <= 1.0

        assert "confidence_drift" in metrics
        assert metrics["confidence_drift"] is not None
        assert "drift_status" in metrics


@pytest.mark.asyncio
async def test_aiops_ocr_success_rate_from_processing_steps_and_eval():
    """Test OCR success rate calculation from DB steps and fallback to eval report."""
    session = AsyncMock()
    service = AIOperationsService(session)

    # Case 1: When ProcessingSteps exist: 95 completed out of 100
    m_completed = MagicMock()
    m_completed.scalar.return_value = 95
    m_total = MagicMock()
    m_total.scalar.return_value = 100
    session.execute.side_effect = [m_completed, m_total]

    rate = await service._compute_ocr_success_rate(eval_report=None)
    assert rate == 0.95

    # Case 2: When no steps in DB, falls back to eval report (mean_cer)
    session.execute.side_effect = [MagicMock(scalar=lambda: 0), MagicMock(scalar=lambda: 0)]
    eval_report = {"mean_cer": 0.03}
    rate_from_eval = await service._compute_ocr_success_rate(eval_report=eval_report)
    assert rate_from_eval == 0.97


@pytest.mark.asyncio
async def test_aiops_extraction_accuracy_from_review_decisions_and_eval():
    """Test extraction accuracy calculation from reviewer decisions and evals."""
    session = AsyncMock()
    service = AIOperationsService(session)

    # Case 1: Review decisions in DB: 90 approved, 10 rejected/corrected (total 100)
    m_approved = MagicMock()
    m_approved.scalar.return_value = 90
    m_total_reviewed = MagicMock()
    m_total_reviewed.scalar.return_value = 100
    session.execute.side_effect = [m_approved, m_total_reviewed]

    acc = await service._compute_extraction_accuracy(eval_report=None)
    assert acc == (0.90, "Reviewer acceptance rate")

    # Case 2: No review decisions, fallback to eval report assertion accuracy or F1
    session.execute.side_effect = [MagicMock(scalar=lambda: 0), MagicMock(scalar=lambda: 0)]
    eval_report = {
        "labelled_eval_set": True,
        "assertion_accuracy": 0.95,
        "f1_by_category": {"unspecified": 0.96},
    }
    acc_eval = await service._compute_extraction_accuracy(eval_report=eval_report)
    assert acc_eval == (0.955, "Labelled evaluation accuracy")


@pytest.mark.asyncio
async def test_aiops_extraction_accuracy_does_not_fall_back_to_circular_baseline():
    session = AsyncMock()
    service = AIOperationsService(session)
    session.execute.side_effect = [MagicMock(scalar=lambda: 0), MagicMock(scalar=lambda: 0)]
    value, label = await service._compute_extraction_accuracy({"assertion_accuracy": 0.99})
    assert value is None
    assert label == "Not measured"


@pytest.mark.asyncio
async def test_aiops_ocr_and_drift_are_unmeasured_when_there_is_no_data():
    session = AsyncMock()
    service = AIOperationsService(session)
    empty = MagicMock(scalar=lambda: 0)
    session.execute.side_effect = [empty, empty]
    assert await service._compute_ocr_success_rate(eval_report=None) is None

    missing = MagicMock(scalar=lambda: None)
    session.execute.side_effect = [missing, missing]
    assert await service._compute_confidence_drift() == {"drift": None, "status": "not_measured"}


@pytest.mark.asyncio
async def test_aiops_response_does_not_turn_missing_drift_into_zero():
    session = AsyncMock()
    service = AIOperationsService(session)
    session.execute.side_effect = [
        MagicMock(scalar=lambda: 0), MagicMock(scalar=lambda: 0),
        MagicMock(scalar=lambda: 0), MagicMock(scalar=lambda: 0),
        MagicMock(scalar=lambda: None), MagicMock(scalar=lambda: None),
    ]
    with patch.object(service, "_compute_ocr_success_rate", new=AsyncMock(return_value=None)), \
         patch.object(service, "_compute_extraction_accuracy", new=AsyncMock(return_value=(None, "Not measured"))), \
         patch.object(service, "_compute_confidence_drift", new=AsyncMock(return_value={"drift": None, "status": "not_measured"})):
        metrics = await service.get_aiops_metrics()
    assert metrics["confidence_drift"] is None
    assert metrics["drift_status"] == "not_measured"


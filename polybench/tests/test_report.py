import pytest
from polybench.db import get_session
from polybench.report.html import generate_report
from polybench.models import BenchmarkRun, TaskResult, Sample
from sqlmodel import select

def test_generate_report_not_found(tmp_db):
    with get_session() as session:
        with pytest.raises(ValueError) as excinfo:
            generate_report(session, "invalid-run-id", "dummy.html")
        assert "not found" in str(excinfo.value)

def test_generate_report_success(tmp_db, tmp_path):
    out_file = tmp_path / "report.html"
    
    with get_session() as session:
        # Create a run
        run = BenchmarkRun(
            id="test-run-123",
            model="claude-3-5-sonnet-latest",
            provider="mock",
            samples_per_task=1,
            k=1,
            temperature=0.2,
            total_tasks=1,
            pass_at_k=1.0
        )
        session.add(run)
        
        # Create task result
        res = TaskResult(
            run_id="test-run-123",
            task_id="python/task1",
            language="python",
            difficulty="easy",
            samples_generated=1,
            samples_passed=1,
            task_pass_at_k=1.0
        )
        session.add(res)
        session.commit()
        session.refresh(res)
        
        # Create sample
        sample = Sample(
            task_result_id=res.id,
            sample_index=0,
            raw_output="raw text",
            extracted_code="def test(): pass",
            passed=True,
            failure_kind=None,
            exit_code=0,
            stdout="stdout",
            stderr="stderr",
            runtime_ms=12,
            timed_out=False
        )
        session.add(sample)
        session.commit()
        
        # Now run generate_report
        generate_report(session, "test-run-123", str(out_file))
        
    assert out_file.exists()
    content = out_file.read_text(encoding="utf-8")
    assert "test-run-123" in content
    assert "claude-3-5-sonnet-latest" in content

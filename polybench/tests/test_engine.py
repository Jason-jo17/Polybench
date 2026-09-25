from polybench.engine import run_benchmark, RunConfig
from polybench.sandbox.runner import SandboxResult
from polybench.db import get_session
from polybench.models import BenchmarkRun


class FakeSandboxRunner:
    def run(self, code, task):
        return SandboxResult(
            exit_code=0, stdout="pass", stderr="", runtime_ms=10, timed_out=False
        )


def test_run_benchmark(tmp_db, sample_task, mock_provider):
    runner = FakeSandboxRunner()
    cfg = RunConfig(model="test", provider="mock", n=2, k=1, temperature=0.0, lang=None)
    with get_session() as session:
        run_record = BenchmarkRun(
            model=cfg.model,
            provider=cfg.provider,
            samples_per_task=cfg.n,
            k=cfg.k,
            temperature=cfg.temperature,
            total_tasks=1,
            pass_at_k=0.0,
            status="PENDING",
        )
        session.add(run_record)
        session.commit()
        run_id = run_record.id

        run_record = run_benchmark(
            run_id, cfg, [sample_task], mock_provider, runner, session
        )
        assert run_record.total_tasks == 1
        assert run_record.pass_at_k == 1.0

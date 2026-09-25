from sqlmodel import Session, select
from jinja2 import Environment, PackageLoader, select_autoescape
from polybench.models import BenchmarkRun, TaskResult, Sample

def generate_report(session: Session, run_id: str, out_path: str) -> None:
    run = session.get(BenchmarkRun, run_id)
    if not run:
        raise ValueError(f"Run {run_id} not found")
        
    results = session.exec(select(TaskResult).where(TaskResult.run_id == run_id)).all()
    samples = session.exec(select(Sample).join(TaskResult).where(TaskResult.run_id == run_id)).all()
    
    env = Environment(
        loader=PackageLoader("polybench.report", "templates"),
        autoescape=select_autoescape()
    )
    
    template = env.get_template("report.html.j2")
    html = template.render(run=run, results=results, samples=samples)
    
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)

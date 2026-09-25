from typing import NamedTuple
from polybench.schemas import Language


class ExecSpec(NamedTuple):
    image: str
    code_file: str
    test_file: str
    test_cmd: list[str]


SPECS = {
    Language.python: ExecSpec(
        image="polybench-python:local",
        code_file="solution.py",
        test_file="test_solution.py",
        test_cmd=["python", "-m", "pytest", "-q", "test_solution.py"],
    ),
    Language.javascript: ExecSpec(
        image="polybench-node:local",
        code_file="solution.js",
        test_file="test_solution.mjs",
        test_cmd=["node", "--test", "test_solution.mjs"],
    ),
    Language.go: ExecSpec(
        image="polybench-go:local",
        code_file="solution.go",
        test_file="solution_test.go",
        test_cmd=["go", "test", "./..."],
    ),
    Language.rust: ExecSpec(
        image="polybench-rust:local",
        code_file="solution.rs",
        test_file="solution_test.rs",
        # solution_test.rs uses include!("solution.rs") so we compile it alone.
        test_cmd=[
            "sh",
            "-c",
            "rustc --test solution_test.rs -o /tmp/rusttest 2>&1 && /tmp/rusttest",
        ],
    ),
}

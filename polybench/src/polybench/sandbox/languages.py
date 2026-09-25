from typing import NamedTuple

from polybench.schemas import Language


class ExecSpec(NamedTuple):
    image: str
    code_file: str
    test_file: str
    test_cmd: list[str]
    # Extra files written next to the code, e.g. the go.mod that `go test` requires.
    extra_files: dict[str, str] = {}
    # Overrides policy.TMPFS. Compiled languages must execute the test binary they
    # build, so their /tmp can't be noexec. This doesn't widen what generated code
    # can do: it already runs arbitrary code inside the same container limits.
    tmpfs: str | None = None
    # Shell command that compiles the tests before they run. It runs outside the
    # task's time limit, so slow compilers don't count against the code under test.
    build: str | None = None


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
        # Start from the standard-library cache pre-built into the image
        # (sandbox/Dockerfile.go) instead of compiling it on every run.
        # One compile job and few threads: the toolchain otherwise exceeds the
        # sandbox's process limit (threads count towards it) and fails at random.
        build=(
            "cp -r /opt/gocache /tmp/gocache"
            " && GOMAXPROCS=2 go test -c -p 1 -o /tmp/solution.test ."
        ),
        test_cmd=["/tmp/solution.test"],
        extra_files={"go.mod": "module solution\n\ngo 1.22\n"},
        tmpfs="/tmp:rw,size=256m,exec",
    ),
    Language.rust: ExecSpec(
        image="polybench-rust:local",
        code_file="solution.rs",
        test_file="solution_test.rs",
        # solution_test.rs uses include!("solution.rs") so we compile it alone.
        # Compiler errors stay on stderr, where the failure classifier looks.
        build="rustc --test solution_test.rs -o /tmp/rusttest",
        test_cmd=["/tmp/rusttest"],
        tmpfs="/tmp:rw,size=128m,exec",
    ),
}

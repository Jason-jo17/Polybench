# Security policy

PolyBench runs code written by language models, so the sandbox is its most security-sensitive part. Reports of any way generated code could affect the host are especially welcome.

## Reporting a vulnerability

**Please don't open a public issue for security problems.** Report them privately through GitHub: go to the repository's **Security** tab and choose **Report a vulnerability**. Only the maintainers can see the report.

Please include:

- what an attacker could do, and under what conditions
- steps or a proof of concept to reproduce it, such as a task file or model output that triggers it
- the PolyBench commit, your operating system, and your Docker version

You can expect an acknowledgement within a week. Once a fix is available, you'll be credited in the advisory unless you ask not to be.

## What's in scope

- **Sandbox escapes**: generated code reading or writing host files, reaching the network, or exceeding the memory, CPU, process or time limits set in `polybench/src/polybench/sandbox/policy.py`.
- **Code execution on the host**: any path where model output is run outside the sandbox, for example through `exec`, `eval` or shell interpolation.
- **Authentication bypass**: getting past `POLYBENCH_DASHBOARD_PASSWORD` on the API or the dashboard.
- **Secret exposure**: API keys leaking through logs, API responses, reports or the dashboard.

## What's out of scope

- Default development credentials in `docker-compose.yml` (tracked publicly in [#18](https://github.com/Jason-jo17/Polybench/issues/18)).
- Attacks that require someone who already controls the host or the `.env` file.
- Models scoring well by gaming weak tests. That's a benchmark-quality problem, so open a normal issue.

## Supported versions

PolyBench hasn't had a release yet. Security fixes go to `main`.

NETWORK = "none"  # --network none
MEMORY = "256m"  # --memory
CPUS = "1.0"  # --cpus
PIDS_LIMIT = 64  # --pids-limit
READ_ONLY = True  # --read-only root fs
TMPFS = "/tmp:rw,size=64m,noexec"  # only writable mount
USER = "10001:10001"  # non-root --user
# The task's time limit is enforced inside the container with `timeout`, which
# exits 124 (coreutils) or 143 (busybox, used by the Alpine-based Go image).
TIMEOUT_EXIT_CODES = frozenset({124, 143})
# Extra time the outer `docker run` gets for container start-up, which is slow
# when several containers start at once (especially on Docker Desktop). It never
# counts against the code under test; it only catches a stalled Docker.
STARTUP_ALLOWANCE_S = 60
CAP_DROP = "ALL"  # --cap-drop ALL

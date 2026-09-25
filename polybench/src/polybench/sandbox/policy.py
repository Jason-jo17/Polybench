NETWORK = "none"          # --network none
MEMORY = "256m"           # --memory
CPUS = "1.0"              # --cpus
PIDS_LIMIT = 64           # --pids-limit
READ_ONLY = True          # --read-only root fs
TMPFS = "/tmp:rw,size=64m,noexec"   # only writable mount
USER = "10001:10001"      # non-root --user
WALL_CLOCK_BUFFER_S = 5   # add to task timeout before SIGKILL
CAP_DROP = "ALL"          # --cap-drop ALL

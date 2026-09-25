"""Building the sandbox images. Shared by `polybench setup`, `polybench run` and
the API worker, so a fresh deployment builds its images before its first run."""

import hashlib
import subprocess
import threading
from collections.abc import Callable

from polybench.config import PROJECT_ROOT

IMAGES = {
    "polybench-python:local": "Dockerfile.python",
    "polybench-node:local": "Dockerfile.node",
    "polybench-go:local": "Dockerfile.go",
    "polybench-rust:local": "Dockerfile.rust",
}
SANDBOX_DIR = PROJECT_ROOT / "sandbox"
_LABEL = "polybench.dockerfile-sha256"
# Two runs starting at once shouldn't build the same image twice.
_build_lock = threading.Lock()


class ImageBuildError(RuntimeError):
    pass


def docker_available() -> bool:
    try:
        return subprocess.run(["docker", "info"], capture_output=True).returncode == 0
    except OSError:
        return False


def _built_from(tag: str) -> str | None:
    """The Dockerfile hash an image was built from ('' if unlabelled), or None if
    the image doesn't exist."""
    res = subprocess.run(
        [
            "docker",
            "image",
            "inspect",
            "--format",
            f'{{{{ index .Config.Labels "{_LABEL}" }}}}',
            tag,
        ],
        capture_output=True,
        text=True,
    )
    return res.stdout.strip() if res.returncode == 0 else None


def ensure_images(
    log: Callable[[str], None] = lambda _: None, *, stream_output: bool = False
) -> None:
    """Build each sandbox image that is missing or older than its Dockerfile.

    Images are labelled with their Dockerfile's hash, so fixes to a Dockerfile
    reach people who built the image before. Raises ImageBuildError on failure.
    """
    with _build_lock:
        for tag, dockerfile in IMAGES.items():
            path = SANDBOX_DIR / dockerfile
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            current = _built_from(tag)
            if current == digest:
                continue
            log(
                f"{'Building' if current is None else 'Rebuilding (Dockerfile changed)'} {tag}…"
            )
            build = subprocess.run(
                [
                    "docker",
                    "build",
                    "-t",
                    tag,
                    "--label",
                    f"{_LABEL}={digest}",
                    "-f",
                    str(path),
                    str(SANDBOX_DIR),
                ],
                capture_output=not stream_output,
                text=True,
            )
            if build.returncode != 0:
                detail = "" if stream_output else f"\n{(build.stderr or '')[-2000:]}"
                raise ImageBuildError(f"Couldn't build {tag} from {path}.{detail}")
            log(f"Built {tag}")

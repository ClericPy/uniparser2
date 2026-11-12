"""Run the release gates, build the artifacts, and (only when asked) publish.

    uv version --bump patch        # then write the CHANGELOG section for it
    uv run python tools/release.py       # gates + build; prints the publish command
    UV_PUBLISH_TOKEN=... uv run python tools/release.py --publish

This is a local development tool, not part of the package: it lives outside `src/` and is not
included in the sdist or the wheel. It never reads or stores a credential; `--publish` requires
`UV_PUBLISH_TOKEN` in the environment. The default mode only builds, so publishing stays an
explicitly authorized action.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"

GATES = (
    ("uv", "lock", "--check"),
    ("uv", "run", "ruff", "format", "--check"),
    ("uv", "run", "ruff", "check"),
    ("uv", "run", "mypy"),
    ("uv", "run", "pytest", "--cov=uniparser2.core", "--cov-fail-under=95"),
    ("uv", "run", "up2", "conformance", "--check"),
)


class ReleaseError(RuntimeError):
    """A release step refused to continue."""


def run(*args: str) -> None:
    """Run a command in the repository, failing the release when it fails."""
    print(f"$ {' '.join(args)}", flush=True)
    try:
        subprocess.run(args, cwd=ROOT, check=True)  # noqa: S603  fixed argv, no shell
    except subprocess.CalledProcessError as exc:
        raise ReleaseError(f"command failed ({exc.returncode}): {' '.join(args)}") from exc


def capture(*args: str) -> str:
    """Run a command and return its stripped stdout."""
    try:
        done = subprocess.run(  # noqa: S603  fixed argv, no shell
            args, cwd=ROOT, check=True, capture_output=True, text=True
        )
    except subprocess.CalledProcessError as exc:
        raise ReleaseError(f"command failed ({exc.returncode}): {' '.join(args)}") from exc
    return done.stdout.strip()


def _smoke(wheel: Path, version: str) -> None:
    """Install the wheel into a throwaway venv and run one core chain."""
    with tempfile.TemporaryDirectory(prefix="up2-release-") as tmp:
        venv = Path(tmp) / "venv"
        run("uv", "venv", "--python", sys.executable, str(venv))
        python = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        run(
            "uv",
            "pip",
            "install",
            "--python",
            str(python),
            "--offline",
            "--no-deps",
            str(wheel),
        )
        code = (
            "import sys\n"
            "import uniparser2 as up2\n"
            "assert up2.__version__ == sys.argv[1], (up2.__version__, sys.argv[1])\n"
            "outcome = up2.eval_field(up2.compile_field([['py', 'upper']]), 'ok')\n"
            "assert outcome.value == 'OK', outcome\n"
            "print('smoke ok')\n"
        )
        print(capture(str(python), "-I", "-c", code, version))


def _release(args: argparse.Namespace) -> int:
    version = capture("uv", "version", "--short")
    print(f"== release {version}")

    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    if f"## [{version}]" not in changelog:
        raise ReleaseError(f"CHANGELOG.md has no '## [{version}]' section; write it first")

    dirty = capture("git", "status", "--porcelain")
    if dirty:
        print("warning: the working tree has uncommitted changes:")
        for line in dirty.splitlines():
            print(f"  {line}")
        if args.publish and not args.allow_dirty:
            raise ReleaseError("publish from a clean tree, or pass --allow-dirty")

    if args.publish and not os.environ.get("UV_PUBLISH_TOKEN"):
        raise ReleaseError("UV_PUBLISH_TOKEN is not set")

    for gate in GATES:
        run(*gate)

    run("uv", "build")

    wheels = sorted(DIST.glob(f"uniparser2-{version}-*.whl"))
    sdists = sorted(DIST.glob(f"uniparser2-{version}.tar.gz"))
    if len(wheels) != 1 or len(sdists) != 1:
        raise ReleaseError(f"expected one wheel and one sdist for {version} in dist/")

    with zipfile.ZipFile(wheels[0]) as archive:
        metadata = archive.read(f"uniparser2-{version}.dist-info/METADATA").decode("utf-8")
    if not any(line.strip() == f"Version: {version}" for line in metadata.splitlines()):
        raise ReleaseError("the wheel metadata does not carry the version")

    _smoke(wheels[0], version)

    files = [str(path.relative_to(ROOT)) for path in (wheels[0], sdists[0])]
    print(f"built {wheels[0].name} and {sdists[0].name}")

    if not args.publish:
        print("next: set UV_PUBLISH_TOKEN and run:")
        print(f"  uv publish {' '.join(Path(f).as_posix() for f in files)}")
        return 0

    run("uv", "publish", *files)
    print(f"published {version}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the release gates, build, and optionally publish to PyPI."
    )
    parser.add_argument(
        "--publish", action="store_true", help="upload the built files (needs UV_PUBLISH_TOKEN)"
    )
    parser.add_argument(
        "--allow-dirty", action="store_true", help="publish even with uncommitted changes"
    )
    args = parser.parse_args()
    try:
        return _release(args)
    except ReleaseError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

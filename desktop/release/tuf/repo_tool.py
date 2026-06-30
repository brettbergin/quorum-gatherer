"""TUF repository tooling for releases.

tufup persists its repo config (`.tufup-repo-config`) in the CURRENT WORKING DIRECTORY,
so all operations run from a stable `--workdir` (which holds the config + repo/ + keys/).
In CI the workdir state (config + published metadata) is restored from the gh-pages branch
and the private signing keys come from a secret; here it's just a local directory.

  * init — one-time (maintainer): create signing keys + initial metadata.
           Commit the public `repo/metadata/root.json` into the app and keep keys secret.
  * add  — per release (CI): add a built bundle as a new version + publish signed metadata.

Usage:
  python desktop/release/tuf/repo_tool.py init --workdir <dir>
  python desktop/release/tuf/repo_tool.py add  --workdir <dir> --bundle <dist/app> --version 0.2.0
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from tufup.repo import Repository

# CI sets a per-platform app name (e.g. quorum-gatherer-macos) so target archives from
# different OSes don't collide on the shared targets release.
APP_NAME = os.environ.get("QUORUM_TUF_APP_NAME", "quorum-gatherer")
APP_VERSION_ATTR = "quorum_core.__version__"


def init(workdir: Path) -> None:
    workdir.mkdir(parents=True, exist_ok=True)
    os.chdir(workdir)
    repo = Repository(
        app_name=APP_NAME,
        app_version_attr=APP_VERSION_ATTR,
        repo_dir=str(workdir / "repo"),
        keys_dir=str(workdir / "keys"),
    )
    repo.initialize()
    repo.save_config()
    print(f"initialized TUF repo in {workdir}")
    print(f"public root: {workdir / 'repo' / 'metadata' / 'root.json'}  <-- bundle with the app")


def add(workdir: Path, bundle_dir: Path, version: str) -> None:
    os.chdir(workdir)
    repo = Repository.from_config()
    repo.add_bundle(new_bundle_dir=str(bundle_dir), new_version=version, skip_patch=True)
    repo.publish_changes(private_key_dirs=[str(repo.keys_dir)])
    print(f"published {APP_NAME} v{version}")


def main() -> None:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    sp_init = sub.add_parser("init")
    sp_init.add_argument("--workdir", required=True, type=Path)
    sp_add = sub.add_parser("add")
    sp_add.add_argument("--workdir", required=True, type=Path)
    sp_add.add_argument("--bundle", required=True, type=Path)
    sp_add.add_argument("--version", required=True)
    args = p.parse_args()
    if args.cmd == "init":
        init(args.workdir)
    else:
        add(args.workdir, args.bundle, args.version)


if __name__ == "__main__":
    main()

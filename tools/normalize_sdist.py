from __future__ import annotations

import argparse
import gzip
import os
import stat
import tarfile
import tempfile
from collections.abc import Sequence
from pathlib import Path


_OWNER_PAX_KEYS = frozenset({"uid", "gid", "uname", "gname"})


def verify_sdist(path: Path) -> None:
    with tarfile.open(path, "r:gz") as archive:
        for member in archive:
            ownership = (member.uid, member.gid, member.uname, member.gname)
            if ownership != (0, 0, "", ""):
                raise ValueError(
                    f"non-neutral owner metadata in {path}: "
                    f"{member.name} has {ownership!r}"
                )


def normalize_sdist(path: Path) -> None:
    original_mode = stat.S_IMODE(path.stat().st_mode)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w+b",
            dir=path.parent,
            prefix=f".{path.name}.",
            delete=False,
        ) as raw_destination:
            temporary_path = Path(raw_destination.name)
            with tarfile.open(path, "r:gz") as source:
                with gzip.GzipFile(
                    filename="",
                    mode="wb",
                    fileobj=raw_destination,
                    mtime=0,
                ) as compressed:
                    with tarfile.open(
                        fileobj=compressed,
                        mode="w|",
                        format=tarfile.PAX_FORMAT,
                    ) as destination:
                        for member in source:
                            member.uid = 0
                            member.gid = 0
                            member.uname = ""
                            member.gname = ""
                            member.pax_headers = {
                                key: value
                                for key, value in member.pax_headers.items()
                                if key not in _OWNER_PAX_KEYS
                            }
                            payload = source.extractfile(member) if member.isfile() else None
                            try:
                                destination.addfile(member, payload)
                            finally:
                                if payload is not None:
                                    payload.close()
            raw_destination.flush()
            os.fsync(raw_destination.fileno())

        os.chmod(temporary_path, original_mode)
        verify_sdist(temporary_path)
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Remove user and machine ownership metadata from Python sdists."
    )
    parser.add_argument("archives", nargs="+", type=Path)
    args = parser.parse_args(argv)
    for archive in args.archives:
        normalize_sdist(archive)
        print(f"normalized {archive}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

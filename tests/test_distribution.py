from __future__ import annotations

import gzip
import io
import tarfile
import tempfile
import unittest
from pathlib import Path

from tools.normalize_sdist import normalize_sdist, verify_sdist


class DistributionTests(unittest.TestCase):
    def test_normalize_sdist_removes_owner_metadata_and_preserves_content(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "package.tar.gz"
            payload = b"release data\n"
            with archive.open("wb") as raw:
                with gzip.GzipFile(
                    filename="personal-build.tar.gz",
                    mode="wb",
                    fileobj=raw,
                    mtime=1_777_777_777,
                ) as compressed:
                    with tarfile.open(fileobj=compressed, mode="w|") as destination:
                        member = tarfile.TarInfo("package/README.md")
                        member.size = len(payload)
                        member.mode = 0o640
                        member.uid = 501
                        member.gid = 20
                        member.uname = "localuser"
                        member.gname = "localgroup"
                        destination.addfile(member, io.BytesIO(payload))

            normalize_sdist(archive)
            verify_sdist(archive)

            with tarfile.open(archive, "r:gz") as normalized:
                members = normalized.getmembers()
                self.assertEqual(1, len(members))
                member = members[0]
                self.assertEqual((0, 0, "", ""), (
                    member.uid,
                    member.gid,
                    member.uname,
                    member.gname,
                ))
                self.assertEqual(0o640, member.mode)
                extracted = normalized.extractfile(member)
                self.assertIsNotNone(extracted)
                self.assertEqual(payload, extracted.read())  # type: ignore[union-attr]

            header = archive.read_bytes()[:64]
            self.assertNotIn(b"personal-build", header)

    def test_verify_sdist_rejects_non_neutral_owner_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "package.tar.gz"
            with tarfile.open(archive, "w:gz") as destination:
                member = tarfile.TarInfo("package/")
                member.type = tarfile.DIRTYPE
                member.uid = 501
                member.uname = "localuser"
                destination.addfile(member)

            with self.assertRaisesRegex(ValueError, "non-neutral owner metadata"):
                verify_sdist(archive)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import errno
import os
import stat
from pathlib import Path


DirectoryIdentity = tuple[int, int]
FileIdentity = tuple[int, int]


def close_best_effort(descriptor: int) -> None:
    if descriptor >= 0:
        try:
            os.close(descriptor)
        except OSError:
            pass


def directory_flags() -> int:
    required = ("O_DIRECTORY", "O_NOFOLLOW")
    if any(not hasattr(os, name) for name in required):
        raise OSError(errno.ENOTSUP, "secure descriptor walks are not supported")
    return (
        os.O_RDONLY
        | os.O_DIRECTORY
        | os.O_NOFOLLOW
        | getattr(os, "O_CLOEXEC", 0)
    )


def directory_identity(descriptor: int) -> DirectoryIdentity:
    observed = os.fstat(descriptor)
    return observed.st_dev, observed.st_ino


def file_identity(descriptor: int) -> FileIdentity:
    observed = os.fstat(descriptor)
    return observed.st_dev, observed.st_ino


def same_directory(left_fd: int, right_fd: int) -> bool:
    return directory_identity(left_fd) == directory_identity(right_fd)


def _walk_absolute_directory(path: Path) -> int:
    if not path.is_absolute():
        raise ValueError("descriptor walk requires an absolute path")
    current_fd = os.open(os.sep, directory_flags())
    try:
        for component in path.parts[1:]:
            next_fd = os.open(
                component,
                directory_flags(),
                dir_fd=current_fd,
            )
            os.close(current_fd)
            current_fd = next_fd
        result = current_fd
        current_fd = -1
        return result
    finally:
        close_best_effort(current_fd)


def _open_resolved_directory(
    resolved: Path,
    expected_identity: DirectoryIdentity | None = None,
) -> int:
    expected = os.stat(resolved, follow_symlinks=False)
    if not stat.S_ISDIR(expected.st_mode):
        raise NotADirectoryError(errno.ENOTDIR, "not a directory", str(resolved))
    expected_identity = expected_identity or (expected.st_dev, expected.st_ino)
    descriptor = _walk_absolute_directory(resolved)
    if directory_identity(descriptor) != expected_identity:
        close_best_effort(descriptor)
        raise OSError(
            errno.ESTALE,
            "directory changed while being opened",
            str(resolved),
        )
    return descriptor


def open_directory(path: Path) -> tuple[int, Path]:
    expected = os.stat(path)
    if not stat.S_ISDIR(expected.st_mode):
        raise NotADirectoryError(errno.ENOTDIR, "not a directory", str(path))
    resolved = path.resolve(strict=True)
    descriptor = _open_resolved_directory(
        resolved,
        (expected.st_dev, expected.st_ino),
    )
    return descriptor, resolved


def open_regular_file(path: Path) -> tuple[int, int, Path]:
    expected = os.stat(path)
    if not stat.S_ISREG(expected.st_mode):
        raise OSError(errno.EINVAL, "not a regular file", str(path))
    resolved = path.resolve(strict=True)
    parent_fd = _open_resolved_directory(resolved.parent)
    file_fd: int | None = None
    try:
        file_fd = os.open(
            resolved.name,
            os.O_RDONLY
            | os.O_NOFOLLOW
            | os.O_NONBLOCK
            | getattr(os, "O_CLOEXEC", 0),
            dir_fd=parent_fd,
        )
        observed = os.fstat(file_fd)
        if not stat.S_ISREG(observed.st_mode):
            raise OSError(errno.EINVAL, "not a regular file", str(path))
        if (observed.st_dev, observed.st_ino) != (expected.st_dev, expected.st_ino):
            raise OSError(errno.ESTALE, "file changed while being opened", str(path))
        result = file_fd
        file_fd = None
        return result, parent_fd, resolved
    except Exception:
        close_best_effort(parent_fd)
        raise
    finally:
        if file_fd is not None:
            close_best_effort(file_fd)


def directory_is_within(
    directory_fd: int,
    ancestor: DirectoryIdentity,
) -> bool:
    current_fd = os.dup(directory_fd)
    try:
        while True:
            if directory_identity(current_fd) == ancestor:
                return True
            parent_fd = os.open("..", directory_flags(), dir_fd=current_fd)
            if same_directory(current_fd, parent_fd):
                os.close(parent_fd)
                return False
            os.close(current_fd)
            current_fd = parent_fd
    finally:
        close_best_effort(current_fd)

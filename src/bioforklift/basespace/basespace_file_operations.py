import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import List, Optional

import requests
from tqdm import tqdm

from .basespace_exceptions import (
    BaseSpaceDownloadError,
)
from bioforklift.forklift_logging import setup_logger

logger = setup_logger(__name__)


def stream_to_disk(
    response: requests.Response,
    destination: Path,
    expected_size: Optional[int] = None,
    chunk_size: int = 1024 * 1024,
    progress: bool = True,
) -> None:
    """
    Stream the content of an HTTP response body to a destination file.
    First, streams to a temporary file in the destination's directory, then
    renames it into place once the full body is written. A disrupted
    stream will only ever leave the temp file (which will get cleaned up).
    It will never leave a truncated file at the final path.

    Args:
        response: The `requests.Response` object to stream content from.
        destination: Path to save the streamed content.
        expected_size: Expected byte length (the file's `Size`); skipped if None.
        chunk_size: The size of each chunk to read from the response.
        progress: If True (default), draw the tqdm progress bar on a TTY. Set False to disable.
    """

    # Only draw the animated bar on a real terminal; tqdm defaults to stderr, so the
    # bar and the stdout log handler stay on separate streams and don't clobber each other.
    show_bar = progress and sys.stderr.isatty()

    # Create a temporary file in the same directory as the destination
    tmp_file = tempfile.NamedTemporaryFile(
        dir=destination.parent,
        prefix=f".tmp.{destination.name}.",
        delete=False,
    )
    tmp_path = Path(tmp_file.name)

    try:
        bytes_written = 0
        bar = tqdm(
            total=expected_size,
            desc=destination.name,
            unit="B",
            unit_scale=True,
            unit_divisor=1024,
            disable=not show_bar,
            leave=False,
        )
        with tmp_file as outfile, bar:
            for chunk in response.iter_content(chunk_size=chunk_size):
                if chunk:
                    outfile.write(chunk)
                    bytes_written += len(chunk)
                    bar.update(len(chunk))

        if expected_size is not None and bytes_written != expected_size:
            raise BaseSpaceDownloadError(
                f"Incomplete download for `{destination.name}`: wrote {bytes_written} byte(s), "
                f"expected {expected_size}."
            )

        os.replace(tmp_path, destination)
    except BaseException:
        # Clean up the partial temp file on any failure (including interrupts).
        tmp_path.unlink(missing_ok=True)
        raise


def concatenate_files(
    sources: List[Path],
    destination: Path,
    expected_total_size: Optional[int] = None,
) -> None:
    """
    Byte-concatenate `sources` into `destination` in order.
    Writes to a temp file in the destination's directory and renames it into place, so an
    interrupted concatenation never leaves a truncated file at the final path.

    Args:
        sources: The files to concatenate, in output order.
        destination: Path to write the concatenated output to.
        expected_total_size: Combined byte length the output must match; skipped if None.

    Raises:
        BaseSpaceDownloadError: If `expected_total_size` is given and the output does not match it.
    """

    # Write to a temp file in the destination dir, then atomically rename.
    tmp_file = tempfile.NamedTemporaryFile(
        dir=destination.parent,
        prefix=f".tmp.{destination.name}.",
        delete=False,
    )
    tmp_path = Path(tmp_file.name)

    try:
        with tmp_file as outfile:
            for source_path in sources:
                with open(source_path, "rb") as infile:
                    shutil.copyfileobj(infile, outfile, 1024 * 1024)

        # Verify the concatenated output matches the combined size the API reported.
        if expected_total_size is not None:
            bytes_written = tmp_path.stat().st_size
            if bytes_written != expected_total_size:
                raise BaseSpaceDownloadError(
                    f"Concatenated size mismatch for `{destination.name}`: wrote {bytes_written} "
                    f"byte(s), expected {expected_total_size}."
                )

        os.replace(tmp_path, destination)
    except BaseException:
        # Clean up the partial temp file on any failure (including interrupts).
        tmp_path.unlink(missing_ok=True)
        raise

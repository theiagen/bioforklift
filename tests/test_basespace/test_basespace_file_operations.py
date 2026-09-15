from pathlib import Path
from unittest.mock import MagicMock

import pytest
import requests

from bioforklift.basespace.basespace_file_operations import (
    concatenate_files,
    stream_to_disk,
)
from bioforklift.basespace.basespace_exceptions import BaseSpaceDownloadError


class TestStreamToDisk:
    def test_writes_bytes_single_chunk(self, tmp_path):
        response = MagicMock()
        response.iter_content.return_value = [b"DATA"]
        destination = tmp_path / "Sample_R1.fastq.gz"

        stream_to_disk(response, destination, progress=False)

        assert destination.read_bytes() == b"DATA"
        # The temp file was renamed into place; nothing else is left behind.
        assert list(tmp_path.iterdir()) == [destination]

    def test_size_match_succeeds_across_chunks(self, tmp_path):
        response = MagicMock()
        response.iter_content.return_value = [b"DA", b"TA"]  # 4 bytes == expected_size
        destination = tmp_path / "Sample_R1.fastq.gz"

        stream_to_disk(response, destination, expected_size=4, progress=False)

        assert destination.read_bytes() == b"DATA"

    def test_size_mismatch_raises_and_cleans_up(self, tmp_path):
        # A completed-but-short body (bytes written != expected_size) raises and leaves nothing.
        response = MagicMock()
        response.iter_content.return_value = [b"SHORT"]  # 5 bytes != 10
        destination = tmp_path / "Sample_R1.fastq.gz"

        with pytest.raises(BaseSpaceDownloadError, match="Incomplete download"):
            stream_to_disk(response, destination, expected_size=10, progress=False)

        assert not destination.exists()
        assert list(tmp_path.iterdir()) == []

    def test_interrupted_stream_leaves_no_partial_file(self, tmp_path):
        # A stream that drops mid-download must not leave a truncated file at the final
        # path, nor a leftover temp file in the destination directory.
        def broken_stream(chunk_size=None):
            yield b"PARTIAL"
            raise requests.ConnectionError("stream dropped mid-download")

        response = MagicMock()
        response.iter_content.side_effect = broken_stream
        destination = tmp_path / "Sample_R1.fastq.gz"

        with pytest.raises(requests.ConnectionError):
            stream_to_disk(response, destination, progress=False)

        assert not destination.exists()
        assert list(tmp_path.iterdir()) == []


class TestConcatenateFiles:
    def test_concatenates_in_order(self, tmp_path):
        first = tmp_path / "a.fastq.gz"
        first.write_bytes(b"11")
        second = tmp_path / "b.fastq.gz"
        second.write_bytes(b"22")
        destination = tmp_path / "out.fastq.gz"

        concatenate_files([first, second], destination)

        assert destination.read_bytes() == b"1122"

    def test_size_match_succeeds(self, tmp_path):
        first = tmp_path / "a.fastq.gz"
        first.write_bytes(b"11")
        second = tmp_path / "b.fastq.gz"
        second.write_bytes(b"22")
        destination = tmp_path / "out.fastq.gz"

        concatenate_files([first, second], destination, expected_total_size=4)

        assert destination.read_bytes() == b"1122"

    def test_size_mismatch_raises_and_cleans_up(self, tmp_path):
        # Sources are 4 bytes on disk but the expected total says 99 -> mismatch must raise and
        # leave no output or temp file behind (only the source files remain).
        first = tmp_path / "a.fastq.gz"
        first.write_bytes(b"XX")
        second = tmp_path / "b.fastq.gz"
        second.write_bytes(b"XX")
        destination = tmp_path / "out.fastq.gz"

        with pytest.raises(BaseSpaceDownloadError, match="Concatenated size mismatch"):
            concatenate_files([first, second], destination, expected_total_size=99)

        assert not destination.exists()
        assert sorted(path.name for path in tmp_path.iterdir()) == ["a.fastq.gz", "b.fastq.gz"]

    def test_missing_source_leaves_no_partial_file(self, tmp_path):
        # A missing source aborts the merge; no output and no temp file are left behind.
        first = tmp_path / "a.fastq.gz"
        first.write_bytes(b"11")
        missing = tmp_path / "missing.fastq.gz"
        destination = tmp_path / "out.fastq.gz"

        with pytest.raises(FileNotFoundError):
            concatenate_files([first, missing], destination)

        assert not destination.exists()
        assert sorted(path.name for path in tmp_path.iterdir()) == ["a.fastq.gz"]

    def test_removes_sources_after_verified_size(self, tmp_path):
        # A verified output means the sources are redundant, so only the output is left behind.
        first = tmp_path / "a.fastq.gz"
        first.write_bytes(b"11")
        second = tmp_path / "b.fastq.gz"
        second.write_bytes(b"22")
        destination = tmp_path / "out.fastq.gz"

        concatenate_files([first, second], destination, expected_total_size=4)

        assert destination.read_bytes() == b"1122"
        assert list(tmp_path.iterdir()) == [destination]

    def test_keeps_sources_when_remove_sources_false(self, tmp_path):
        first = tmp_path / "a.fastq.gz"
        first.write_bytes(b"11")
        second = tmp_path / "b.fastq.gz"
        second.write_bytes(b"22")
        destination = tmp_path / "out.fastq.gz"

        concatenate_files(
            [first, second], destination, expected_total_size=4, remove_sources=False
        )

        assert destination.read_bytes() == b"1122"
        assert sorted(path.name for path in tmp_path.iterdir()) == [
            "a.fastq.gz",
            "b.fastq.gz",
            "out.fastq.gz",
        ]

    def test_keeps_sources_when_no_expected_size(self, tmp_path):
        # No expected size means no verification ran, so the sources are never deleted.
        first = tmp_path / "a.fastq.gz"
        first.write_bytes(b"11")
        second = tmp_path / "b.fastq.gz"
        second.write_bytes(b"22")
        destination = tmp_path / "out.fastq.gz"

        concatenate_files([first, second], destination)

        assert destination.read_bytes() == b"1122"
        assert sorted(path.name for path in tmp_path.iterdir()) == [
            "a.fastq.gz",
            "b.fastq.gz",
            "out.fastq.gz",
        ]

    def test_does_not_remove_destination_when_source_is_destination(self, tmp_path):
        # A source already carrying the output name is overwritten in place by the rename;
        # cleanup must not then delete the verified output.
        destination = tmp_path / "Sample_R1.fastq.gz"
        destination.write_bytes(b"11")
        second = tmp_path / "b.fastq.gz"
        second.write_bytes(b"22")

        concatenate_files([destination, second], destination, expected_total_size=4)

        assert destination.read_bytes() == b"1122"
        assert list(tmp_path.iterdir()) == [destination]

    def test_unlink_failure_does_not_raise(self, tmp_path, monkeypatch):
        # The output is already in place, so a source that can't be deleted is warned about
        # rather than raised on.
        first = tmp_path / "a.fastq.gz"
        first.write_bytes(b"11")
        second = tmp_path / "b.fastq.gz"
        second.write_bytes(b"22")
        destination = tmp_path / "out.fastq.gz"

        def raise_oserror(self, missing_ok=False):
            raise OSError("permission denied")

        monkeypatch.setattr(Path, "unlink", raise_oserror)

        concatenate_files([first, second], destination, expected_total_size=4)

        assert destination.read_bytes() == b"1122"
        assert sorted(path.name for path in tmp_path.iterdir()) == [
            "a.fastq.gz",
            "b.fastq.gz",
            "out.fastq.gz",
        ]

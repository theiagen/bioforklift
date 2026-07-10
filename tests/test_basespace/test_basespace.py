from unittest.mock import MagicMock

from bioforklift.basespace import BaseSpace


class TestBaseSpace:
    def test_wiring_shares_single_endpoints_instance(self, mock_client):
        # The facade must expose client/methods/endpoints, with endpoints shared
        # between the facade and its methods (one BaseSpaceEndpoints per BaseSpace).
        bs = BaseSpace.from_client(mock_client)

        assert bs.client is mock_client
        assert bs.endpoints.client is bs.client
        assert bs.methods.endpoints is bs.endpoints
        assert bs.methods.endpoints.client is bs.client
        assert callable(bs.fetch_sample_fastqs)

    def test_fetch_sample_fastqs_delegates_to_methods(self, mock_client, tmp_path):
        # The top-level alias must forward args to methods.fetch_sample_fastqs and
        # return its result unchanged.
        bs = BaseSpace.from_client(mock_client)
        expected = [("SampleA_R1.fastq.gz", tmp_path / "SampleA_R1.fastq.gz")]
        bs.methods.fetch_sample_fastqs = MagicMock(return_value=expected)
        bs.fetch_sample_fastqs = bs.methods.fetch_sample_fastqs

        result = bs.fetch_sample_fastqs(
            "collA",
            ["SampleA"],
            dest_dir=tmp_path,
            dry_run=True,
        )

        assert result is expected
        bs.methods.fetch_sample_fastqs.assert_called_once_with(
            "collA",
            ["SampleA"],
            dest_dir=tmp_path,
            dry_run=True,
        )

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
        # The top-level aliases must forward to the matching methods. Bound-method
        # equality holds (same __self__ + __func__), so this pins the `_wire` aliasing
        # without re-doing the wiring inside the test.
        assert bs.fetch_sample_fastqs == bs.methods.fetch_sample_fastqs
        assert bs.build_sample_sheet == bs.methods.build_sample_sheet

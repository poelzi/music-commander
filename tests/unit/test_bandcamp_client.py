"""Unit tests for BandcampClient."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


class TestStreamGet:
    """Tests for BandcampClient.stream_get()."""

    def test_calls_request_with_stream_true(self) -> None:
        """stream_get should delegate to _request with stream=True."""
        from music_commander.bandcamp.client import BandcampClient

        client = BandcampClient.__new__(BandcampClient)
        client._session = MagicMock()
        client._limiter = MagicMock()

        mock_response = MagicMock()
        with patch.object(client, "_request", return_value=mock_response) as mock_req:
            result = client.stream_get("https://example.com/file.zip")

        mock_req.assert_called_once_with("GET", "https://example.com/file.zip", stream=True)
        assert result is mock_response

    def test_passes_extra_kwargs(self) -> None:
        """stream_get should forward additional kwargs to _request."""
        from music_commander.bandcamp.client import BandcampClient

        client = BandcampClient.__new__(BandcampClient)
        client._session = MagicMock()
        client._limiter = MagicMock()

        with patch.object(client, "_request", return_value=MagicMock()) as mock_req:
            client.stream_get("https://example.com/file.zip", timeout=60)

        mock_req.assert_called_once_with(
            "GET", "https://example.com/file.zip", stream=True, timeout=60
        )

    def test_stream_kwarg_always_true(self) -> None:
        """Even if caller passes stream=False, it should be overridden to True."""
        from music_commander.bandcamp.client import BandcampClient

        client = BandcampClient.__new__(BandcampClient)
        client._session = MagicMock()
        client._limiter = MagicMock()

        with patch.object(client, "_request", return_value=MagicMock()) as mock_req:
            client.stream_get("https://example.com/file.zip", stream=False)

        # stream=True should be the final value since we set it after kwargs
        call_kwargs = mock_req.call_args
        assert call_kwargs.kwargs["stream"] is True

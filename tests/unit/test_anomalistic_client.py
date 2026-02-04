"""Unit tests for the Anomalistic portal REST API client."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests
from music_commander.anomalistic.client import AnomaListicClient

from music_commander.exceptions import AnomaListicConnectionError, AnomaListicError


def _make_response(
    json_data: list | dict,
    status_code: int = 200,
    headers: dict | None = None,
) -> MagicMock:
    """Create a mock requests.Response."""
    resp = MagicMock(spec=requests.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.headers = headers or {}
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = requests.HTTPError(response=resp)
    return resp


class TestFetchCategories:
    """Tests for fetch_categories()."""

    def test_single_page(self):
        client = AnomaListicClient()
        categories = [
            {"id": 9, "name": "DarkPsy", "slug": "darkpsy", "count": 50},
            {"id": 21, "name": "Anomalistic Records", "slug": "anomalistic-records", "count": 30},
        ]
        resp = _make_response(categories, headers={"X-WP-TotalPages": "1"})

        with patch.object(client._session, "get", return_value=resp) as mock_get:
            result = client.fetch_categories()

        assert len(result) == 2
        assert result[0]["id"] == 9
        mock_get.assert_called_once()

    def test_multiple_pages(self):
        client = AnomaListicClient()
        page1 = [{"id": i, "name": f"Cat{i}", "slug": f"cat{i}", "count": 1} for i in range(100)]
        page2 = [{"id": 100, "name": "Cat100", "slug": "cat100", "count": 1}]

        resp1 = _make_response(page1, headers={"X-WP-TotalPages": "2"})
        resp2 = _make_response(page2, headers={"X-WP-TotalPages": "2"})

        with patch.object(client._session, "get", side_effect=[resp1, resp2]):
            result = client.fetch_categories()

        assert len(result) == 101

    def test_empty_categories(self):
        client = AnomaListicClient()
        resp = _make_response([], headers={"X-WP-TotalPages": "0"})

        with patch.object(client._session, "get", return_value=resp):
            result = client.fetch_categories()

        assert result == []


class TestFetchPostsPage:
    """Tests for fetch_posts_page()."""

    def test_returns_posts_and_total_pages(self):
        client = AnomaListicClient()
        posts = [{"id": 1, "title": {"rendered": "Test"}}]
        resp = _make_response(posts, headers={"X-WP-TotalPages": "3"})

        with patch.object(client._session, "get", return_value=resp) as mock_get:
            result_posts, total_pages = client.fetch_posts_page(page=2)

        assert len(result_posts) == 1
        assert total_pages == 3
        call_kwargs = mock_get.call_args
        assert call_kwargs[1]["params"]["page"] == 2
        assert call_kwargs[1]["params"]["per_page"] == 100

    def test_missing_total_pages_header(self):
        client = AnomaListicClient()
        posts = [{"id": 1}]
        resp = _make_response(posts, headers={})

        with patch.object(client._session, "get", return_value=resp):
            _, total_pages = client.fetch_posts_page()

        assert total_pages == 1


class TestIterReleases:
    """Tests for iter_releases() pagination."""

    def test_single_page(self):
        client = AnomaListicClient()
        posts = [{"id": i} for i in range(5)]
        resp = _make_response(posts, headers={"X-WP-TotalPages": "1"})

        with patch.object(client._session, "get", return_value=resp):
            result = list(client.iter_releases())

        assert len(result) == 5

    def test_multiple_pages(self):
        client = AnomaListicClient()
        page1 = [{"id": i} for i in range(100)]
        page2 = [{"id": i} for i in range(100, 178)]

        resp1 = _make_response(page1, headers={"X-WP-TotalPages": "2"})
        resp2 = _make_response(page2, headers={"X-WP-TotalPages": "2"})

        with patch.object(client._session, "get", side_effect=[resp1, resp2]):
            result = list(client.iter_releases())

        assert len(result) == 178

    def test_empty_response_stops(self):
        client = AnomaListicClient()
        resp = _make_response([], headers={"X-WP-TotalPages": "1"})

        with patch.object(client._session, "get", return_value=resp):
            result = list(client.iter_releases())

        assert result == []

    def test_three_pages(self):
        client = AnomaListicClient()
        page1 = [{"id": i} for i in range(100)]
        page2 = [{"id": i} for i in range(100, 200)]
        page3 = [{"id": i} for i in range(200, 278)]

        resp1 = _make_response(page1, headers={"X-WP-TotalPages": "3"})
        resp2 = _make_response(page2, headers={"X-WP-TotalPages": "3"})
        resp3 = _make_response(page3, headers={"X-WP-TotalPages": "3"})

        with patch.object(client._session, "get", side_effect=[resp1, resp2, resp3]):
            result = list(client.iter_releases())

        assert len(result) == 278


class TestRetryLogic:
    """Tests for retry and backoff in _request()."""

    @patch("music_commander.anomalistic.client.time.sleep")
    def test_retry_on_429(self, mock_sleep):
        client = AnomaListicClient()
        rate_limited = _make_response([], status_code=429, headers={})
        success = _make_response([{"id": 1}], headers={"X-WP-TotalPages": "1"})

        with patch.object(client._session, "get", side_effect=[rate_limited, success]):
            result = client.fetch_categories()

        assert len(result) == 1
        mock_sleep.assert_called_once()

    @patch("music_commander.anomalistic.client.time.sleep")
    def test_retry_on_503(self, mock_sleep):
        client = AnomaListicClient()
        unavailable = _make_response([], status_code=503, headers={})
        success = _make_response([{"id": 1}], headers={"X-WP-TotalPages": "1"})

        with patch.object(client._session, "get", side_effect=[unavailable, success]):
            result = client.fetch_categories()

        assert len(result) == 1

    @patch("music_commander.anomalistic.client.time.sleep")
    def test_retry_respects_retry_after_header(self, mock_sleep):
        client = AnomaListicClient()
        rate_limited = _make_response([], status_code=429, headers={"Retry-After": "5"})
        success = _make_response([{"id": 1}], headers={"X-WP-TotalPages": "1"})

        with patch.object(client._session, "get", side_effect=[rate_limited, success]):
            client.fetch_categories()

        mock_sleep.assert_called_once_with(5.0)

    @patch("music_commander.anomalistic.client.time.sleep")
    def test_max_retries_exceeded_raises(self, mock_sleep):
        client = AnomaListicClient()
        rate_limited = _make_response([], status_code=429, headers={})

        with (
            patch.object(client._session, "get", return_value=rate_limited),
            pytest.raises(AnomaListicError, match="Rate limited"),
        ):
            client.fetch_categories()

    @patch("music_commander.anomalistic.client.time.sleep")
    def test_connection_error_retries(self, mock_sleep):
        client = AnomaListicClient()
        success = _make_response([{"id": 1}], headers={"X-WP-TotalPages": "1"})

        with patch.object(
            client._session,
            "get",
            side_effect=[requests.ConnectionError("fail"), success],
        ):
            result = client.fetch_categories()

        assert len(result) == 1
        mock_sleep.assert_called_once()

    @patch("music_commander.anomalistic.client.time.sleep")
    def test_connection_error_max_retries(self, mock_sleep):
        client = AnomaListicClient()

        with (
            patch.object(
                client._session,
                "get",
                side_effect=requests.ConnectionError("fail"),
            ),
            pytest.raises(AnomaListicConnectionError, match="failed after"),
        ):
            client.fetch_categories()


class TestUserAgent:
    """Tests for client configuration."""

    def test_user_agent_header(self):
        client = AnomaListicClient()
        assert client._session.headers["User-Agent"] == "music-commander/0.1"

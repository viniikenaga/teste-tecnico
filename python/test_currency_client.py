"""Testes unitários para currency_client.py (pytest + responses)."""
from __future__ import annotations

import sqlite3
import time

import pytest
import responses

import currency_client
from currency_client import BASE_URL, CurrencyClientError, get_rate


@pytest.fixture(autouse=True)
def isolate_cache(tmp_path, monkeypatch):
    """Garante que cada teste use um cache SQLite isolado e não durma de verdade."""
    cache_path = tmp_path / "rate_cache.db"
    monkeypatch.setattr(currency_client, "CACHE_DB_PATH", cache_path)
    monkeypatch.setattr(currency_client.time, "sleep", lambda _seconds: None)
    yield


@responses.activate
def test_get_rate_success():
    responses.add(responses.GET, BASE_URL, json={"rate": 5.42}, status=200)

    rate = get_rate("USD")

    assert rate == 5.42
    assert len(responses.calls) == 1


@responses.activate
def test_get_rate_uses_cache_within_ttl():
    responses.add(responses.GET, BASE_URL, json={"rate": 5.10}, status=200)

    first = get_rate("EUR")
    second = get_rate("EUR")

    assert first == second == 5.10
    assert len(responses.calls) == 1  # segunda chamada veio do cache, sem nova requisição


@responses.activate
def test_get_rate_ignores_expired_cache(monkeypatch):
    responses.add(responses.GET, BASE_URL, json={"rate": 5.10}, status=200)
    responses.add(responses.GET, BASE_URL, json={"rate": 5.30}, status=200)

    first = get_rate("GBP")

    # Simula expiração do cache (janela de validade de 1h).
    conn = sqlite3.connect(str(currency_client.CACHE_DB_PATH))
    conn.execute("UPDATE rate_cache SET fetched_at = ? WHERE moeda = 'GBP'", (time.time() - 3601,))
    conn.commit()
    conn.close()

    second = get_rate("GBP")

    assert first == 5.10
    assert second == 5.30
    assert len(responses.calls) == 2


@responses.activate
def test_get_rate_retries_on_http_500_then_succeeds():
    responses.add(responses.GET, BASE_URL, status=500)
    responses.add(responses.GET, BASE_URL, status=500)
    responses.add(responses.GET, BASE_URL, json={"rate": 6.0}, status=200)

    rate = get_rate("JPY")

    assert rate == 6.0
    assert len(responses.calls) == 3


@responses.activate
def test_get_rate_raises_after_exhausting_retries():
    responses.add(responses.GET, BASE_URL, status=500)
    responses.add(responses.GET, BASE_URL, status=500)
    responses.add(responses.GET, BASE_URL, status=500)

    with pytest.raises(CurrencyClientError):
        get_rate("CNY")

    assert len(responses.calls) == 3


@responses.activate
def test_get_rate_does_not_retry_on_4xx():
    responses.add(responses.GET, BASE_URL, status=404, json={"error": "moeda desconhecida"})

    with pytest.raises(CurrencyClientError):
        get_rate("XXX")

    assert len(responses.calls) == 1


@responses.activate
def test_get_rate_bypasses_cache_when_disabled():
    responses.add(responses.GET, BASE_URL, json={"rate": 1.0}, status=200)
    responses.add(responses.GET, BASE_URL, json={"rate": 1.0}, status=200)

    get_rate("ARS", use_cache=False)
    get_rate("ARS", use_cache=False)

    assert len(responses.calls) == 2

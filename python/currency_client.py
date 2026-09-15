"""Cliente para a API de cotação de moedas (conversão para BRL).

Endpoint fictício de teste: https://api.exemplo.com/v1/rates
"""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import requests

BASE_URL = "https://api.exemplo.com/v1/rates"
TIMEOUT_SECONDS = 5
MAX_RETRIES = 3
BACKOFF_SECONDS = (1, 2, 4)

BASE_DIR = Path(__file__).resolve().parent
CACHE_DB_PATH = BASE_DIR / "rate_cache.db"
CACHE_TTL_SECONDS = 60 * 60  # 1 hora


class CurrencyClientError(Exception):
    """Erro genérico ao obter a taxa de câmbio."""


def _get_cache_connection(db_path: Path | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path if db_path is not None else CACHE_DB_PATH))
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS rate_cache (
            moeda TEXT PRIMARY KEY,
            rate REAL NOT NULL,
            fetched_at REAL NOT NULL
        )
        """
    )
    conn.commit()
    return conn


def _get_cached_rate(moeda_origem: str, db_path: Path | None = None) -> float | None:
    conn = _get_cache_connection(db_path)
    try:
        row = conn.execute(
            "SELECT rate, fetched_at FROM rate_cache WHERE moeda = ?", (moeda_origem,)
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        return None

    rate, fetched_at = row
    if time.time() - fetched_at > CACHE_TTL_SECONDS:
        return None
    return rate


def _store_cached_rate(moeda_origem: str, rate: float, db_path: Path | None = None) -> None:
    conn = _get_cache_connection(db_path)
    try:
        conn.execute(
            "INSERT INTO rate_cache (moeda, rate, fetched_at) VALUES (?, ?, ?) "
            "ON CONFLICT(moeda) DO UPDATE SET rate = excluded.rate, fetched_at = excluded.fetched_at",
            (moeda_origem, rate, time.time()),
        )
        conn.commit()
    finally:
        conn.close()


def _fetch_rate_from_api(moeda_origem: str) -> float:
    """Faz a chamada HTTP à API com retry exponencial (1s/2s/4s) em erros 5xx/conexão/timeout."""
    last_exception: Exception | None = None

    for attempt in range(MAX_RETRIES):
        try:
            response = requests.get(
                BASE_URL, params={"base": moeda_origem, "target": "BRL"}, timeout=TIMEOUT_SECONDS
            )
        except requests.exceptions.Timeout as exc:
            last_exception = exc
        except requests.exceptions.ConnectionError as exc:
            last_exception = exc
        else:
            if response.status_code == 200:
                data = response.json()
                try:
                    return float(data["rate"])
                except (KeyError, TypeError, ValueError) as exc:
                    raise CurrencyClientError(
                        f"Resposta da API em formato inesperado: {data}"
                    ) from exc

            if 400 <= response.status_code < 500:
                # Erro do cliente (ex: moeda inválida): não adianta repetir a chamada.
                raise CurrencyClientError(
                    f"Erro {response.status_code} ao consultar taxa para {moeda_origem}: {response.text}"
                )

            # 5xx: erro do servidor, elegível para retry.
            last_exception = CurrencyClientError(
                f"Erro {response.status_code} do servidor ao consultar taxa para {moeda_origem}"
            )

        if attempt < MAX_RETRIES - 1:
            time.sleep(BACKOFF_SECONDS[attempt])

    raise CurrencyClientError(
        f"Falha ao obter taxa de câmbio para {moeda_origem} após {MAX_RETRIES} tentativas: {last_exception}"
    ) from last_exception


def get_rate(moeda_origem: str, use_cache: bool = True) -> float:
    """Retorna a taxa de conversão atualizada de `moeda_origem` para BRL.

    Consulta primeiro um cache local (SQLite) com validade de 1 hora; em caso
    de cache expirado ou ausente, consulta a API REST com retry exponencial
    (até 3 tentativas, backoff de 1s/2s/4s) para erros de conexão, timeout e
    status 5xx. Erros 4xx são propagados imediatamente, sem retry.

    Args:
        moeda_origem: Código ISO da moeda de origem (ex.: "USD", "EUR").
        use_cache: Se True (default), utiliza/atualiza o cache local de 1h.

    Returns:
        A taxa de conversão de `moeda_origem` para BRL.

    Raises:
        CurrencyClientError: Se a API retornar erro 4xx, ou se todas as
            tentativas de retry falharem por timeout/conexão/erro 5xx.
    """
    moeda_origem = moeda_origem.strip().upper()

    if use_cache:
        cached = _get_cached_rate(moeda_origem)
        if cached is not None:
            return cached

    rate = _fetch_rate_from_api(moeda_origem)

    if use_cache:
        _store_cached_rate(moeda_origem, rate)

    return rate

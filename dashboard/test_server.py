"""Testes unitários para os endpoints de server.py (pytest + Flask test client)."""
from __future__ import annotations

import sqlite3

import pytest

import server

SCHEMA_SQL = """
CREATE TABLE cotacoes (
    codigo INTEGER PRIMARY KEY,
    cliente TEXT,
    criacao DATETIME,
    origem TEXT,
    destino TEXT,
    paisorigem TEXT,
    paisdestino TEXT,
    lane TEXT,
    modal TEXT,
    lclfcl TEXT,
    operador TEXT,
    carrier TEXT,
    vendedor TEXT,
    status TEXT,
    validade DATETIME,
    department TEXT,
    criador TEXT,
    cntr_peso REAL
);
"""


@pytest.fixture
def client(tmp_path):
    db_path = tmp_path / "cotacoes.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript(SCHEMA_SQL)
    conn.execute(
        "INSERT INTO cotacoes (codigo, cliente, criacao, lane, vendedor, status) "
        "VALUES (1, 'Acme', '2022-01-01', 'ASIA-BR', 'Joao', 'APROVADO')"
    )
    conn.commit()
    conn.close()

    server.app.config["DB_PATH"] = str(db_path)
    server.app.config["TESTING"] = True
    with server.app.test_client() as test_client:
        yield test_client


def test_cotacoes_valid_page_returns_200(client):
    response = client.get("/api/cotacoes?page=1&per_page=10")
    assert response.status_code == 200
    assert response.get_json()["total"] == 1


def test_cotacoes_invalid_page_returns_400(client):
    response = client.get("/api/cotacoes?page=abc")
    assert response.status_code == 400
    assert "erro" in response.get_json()


def test_cotacoes_invalid_per_page_returns_400(client):
    response = client.get("/api/cotacoes?per_page=abc")
    assert response.status_code == 400

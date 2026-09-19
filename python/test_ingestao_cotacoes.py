"""Testes unitários para ingestao_cotacoes.py (pytest)."""
from __future__ import annotations

import json
import sqlite3

import pytest

import ingestao_cotacoes as ic

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
def db_conn():
    conn = sqlite3.connect(":memory:")
    conn.executescript(SCHEMA_SQL)
    yield conn
    conn.close()


@pytest.fixture(autouse=True)
def _quiet_logger():
    ic.logger.handlers.clear()
    ic.logger.addHandler(ic.logging.NullHandler())


def test_normalize_csv_row_maps_columns():
    row = {
        "quote_id": "101",
        "customer": "Acme",
        "creation_date": "2022-03-10",
        "trade_lane": "ASIA-BR",
        "sales_rep": "Joao Silva",
        "quote_status": "APROVADO",
        "weight_kg": "1200.5",
    }
    result = ic.normalize_csv_row(row)
    assert result["codigo"] == 101
    assert result["cliente"] == "Acme"
    assert result["criacao"] == "2022-03-10"
    assert result["lane"] == "ASIA-BR"
    assert result["vendedor"] == "Joao Silva"
    assert result["status"] == "APROVADO"
    assert result["cntr_peso"] == 1200.5


def test_normalize_json_shipment_maps_nested_fields():
    shipment = {
        "qid": "202",
        "cust": "Globex",
        "cdate": "2022/04/01",
        "route": {"oport": "Santos", "dport": "Rotterdam", "lane": "BR-EU"},
        "cargo": {"mode": "MARITIMO", "wt": "800"},
        "parties": {"sales": "Maria Souza"},
        "status": {"stat": "ESTUDO"},
    }
    result = ic.normalize_json_shipment(shipment)
    assert result["codigo"] == 202
    assert result["cliente"] == "Globex"
    assert result["criacao"] == "2022-04-01"
    assert result["lane"] == "BR-EU"
    assert result["vendedor"] == "Maria Souza"
    assert result["status"] == "ESTUDO"
    assert result["cntr_peso"] == 800.0


def test_to_datetime_str_accepts_alternate_formats():
    assert ic._to_datetime_str("2022-01-05") == "2022-01-05"
    assert ic._to_datetime_str("2022/01/05") == "2022-01-05"
    assert ic._to_datetime_str("05/01/2022") == "2022-01-05"


def test_insert_records_is_idempotent(db_conn):
    record = {col: None for col in ic.SCHEMA_COLUMNS}
    record["codigo"] = 1

    inserted, skipped = ic.insert_records(db_conn, [record])
    assert (inserted, skipped) == (1, 0)

    inserted, skipped = ic.insert_records(db_conn, [record])
    assert (inserted, skipped) == (0, 1)


def test_read_csv_file_skips_only_the_invalid_row(tmp_path):
    """Uma linha com dado inválido não deve derrubar o arquivo inteiro."""
    csv_path = tmp_path / "fornecedor_a.csv"
    csv_path.write_text(
        "quote_id,customer,weight_kg\n"
        "1,Acme,100\n"
        "2,Globex,nao-e-um-numero\n"
        "3,Initech,300\n",
        encoding="utf-8",
    )

    records = ic.read_csv_file(csv_path)

    assert [r["codigo"] for r in records] == [1, 3]


def test_read_json_file_skips_only_the_invalid_shipment(tmp_path):
    json_path = tmp_path / "fornecedor_b.json"
    json_path.write_text(
        json.dumps(
            {
                "shipments": [
                    {"qid": "1", "cust": "Acme", "cargo": {"wt": "100"}},
                    {"qid": "2", "cust": "Globex", "cargo": {"wt": "invalido"}},
                    {"qid": "3", "cust": "Initech", "cargo": {"wt": "300"}},
                ]
            }
        ),
        encoding="utf-8",
    )

    records = ic.read_json_file(json_path)

    assert [r["codigo"] for r in records] == [1, 3]

#!/usr/bin/env python3
"""Pipeline de ingestão de cotações de fornecedores (CSV/JSON) no banco cotacoes.db.

Uso:
    python ingestao_cotacoes.py --dir /caminho/para/arquivos [--db cotacoes.db]

Agendável via cron ou Task Scheduler sem alterações de código: todos os
caminhos são recebidos por argumento ou resolvidos de forma relativa ao
próprio script (nenhum caminho absoluto é fixado no código).
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import logging.handlers
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DB_PATH = BASE_DIR.parent / "cotacoes.db"

SCHEMA_COLUMNS = [
    "codigo", "cliente", "criacao", "origem", "destino", "paisorigem",
    "paisdestino", "lane", "modal", "lclfcl", "operador", "carrier",
    "vendedor", "status", "validade", "department", "criador", "cntr_peso",
]

# Fornecedor A: CSV plano, colunas em inglês.
CSV_COLUMN_MAP = {
    "quote_id": "codigo",
    "customer": "cliente",
    "creation_date": "criacao",
    "origin_port": "origem",
    "destination_port": "destino",
    "origin_country": "paisorigem",
    "destination_country": "paisdestino",
    "trade_lane": "lane",
    "transport_mode": "modal",
    "container_type": "lclfcl",
    "operator_name": "operador",
    "shipping_carrier": "carrier",
    "sales_rep": "vendedor",
    "quote_status": "status",
    "valid_until": "validade",
    "dept": "department",
    "created_by": "criador",
    "weight_kg": "cntr_peso",
}

logger = logging.getLogger("ingestao_cotacoes")


def setup_logging(log_dir: Path) -> None:
    """Configura logging estruturado com rotação (até 5 MB, 3 backups)."""
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "ingestao_cotacoes.log"

    formatter = logging.Formatter(
        fmt="[%(asctime)s] [%(levelname)s] [%(filename)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)


def _to_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(float(value))


def _to_real(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _to_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _to_datetime_str(value: Any) -> str | None:
    """Normaliza datas para o formato DATETIME (YYYY-MM-DD)."""
    if value is None or value == "":
        return None
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    logger.warning("Formato de data não reconhecido: %s", text)
    return text


def normalize_csv_row(row: dict[str, str]) -> dict[str, Any]:
    """Mapeia uma linha do CSV do fornecedor A para o schema de `cotacoes`."""
    mapped = {CSV_COLUMN_MAP[k]: v for k, v in row.items() if k in CSV_COLUMN_MAP}
    return {
        "codigo": _to_int(mapped.get("codigo")),
        "cliente": _to_text(mapped.get("cliente")),
        "criacao": _to_datetime_str(mapped.get("criacao")),
        "origem": _to_text(mapped.get("origem")),
        "destino": _to_text(mapped.get("destino")),
        "paisorigem": _to_text(mapped.get("paisorigem")),
        "paisdestino": _to_text(mapped.get("paisdestino")),
        "lane": _to_text(mapped.get("lane")),
        "modal": _to_text(mapped.get("modal")),
        "lclfcl": _to_text(mapped.get("lclfcl")),
        "operador": _to_text(mapped.get("operador")),
        "carrier": _to_text(mapped.get("carrier")),
        "vendedor": _to_text(mapped.get("vendedor")),
        "status": _to_text(mapped.get("status")),
        "validade": _to_datetime_str(mapped.get("validade")),
        "department": _to_text(mapped.get("department")),
        "criador": _to_text(mapped.get("criador")),
        "cntr_peso": _to_real(mapped.get("cntr_peso")),
    }


def normalize_json_shipment(shipment: dict[str, Any]) -> dict[str, Any]:
    """Mapeia um registro aninhado do fornecedor B para o schema de `cotacoes`."""
    route = shipment.get("route", {}) or {}
    cargo = shipment.get("cargo", {}) or {}
    parties = shipment.get("parties", {}) or {}
    status = shipment.get("status", {}) or {}

    return {
        "codigo": _to_int(shipment.get("qid")),
        "cliente": _to_text(shipment.get("cust")),
        "criacao": _to_datetime_str(shipment.get("cdate")),
        "origem": _to_text(route.get("oport")),
        "destino": _to_text(route.get("dport")),
        "paisorigem": _to_text(route.get("ocountry")),
        "paisdestino": _to_text(route.get("dcountry")),
        "lane": _to_text(route.get("lane")),
        "modal": _to_text(cargo.get("mode")),
        "lclfcl": _to_text(cargo.get("ctype")),
        "operador": _to_text(parties.get("op")),
        "carrier": _to_text(parties.get("carr")),
        "vendedor": _to_text(parties.get("sales")),
        "status": _to_text(status.get("stat")),
        "validade": _to_datetime_str(status.get("valid")),
        "department": _to_text(shipment.get("dept")),
        "criador": _to_text(parties.get("creator")),
        "cntr_peso": _to_real(cargo.get("wt")),
    }


def read_csv_file(path: Path) -> list[dict[str, Any]]:
    """Lê e normaliza o CSV, pulando linhas individualmente inválidas (não descarta o arquivo todo)."""
    records = []
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for line_num, row in enumerate(reader, start=2):  # linha 1 é o cabeçalho
            try:
                records.append(normalize_csv_row(row))
            except (ValueError, TypeError) as exc:
                logger.warning(
                    "Linha %d de %s ignorada (dado inválido): %s", line_num, path.name, exc
                )
    return records


def read_json_file(path: Path) -> list[dict[str, Any]]:
    """Lê e normaliza o JSON, pulando registros individualmente inválidos (não descarta o arquivo todo)."""
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    shipments = data.get("shipments", [])

    records = []
    for index, shipment in enumerate(shipments, start=1):
        try:
            records.append(normalize_json_shipment(shipment))
        except (ValueError, TypeError) as exc:
            logger.warning(
                "Registro %d de %s ignorado (dado inválido): %s", index, path.name, exc
            )
    return records


def get_existing_codes(conn: sqlite3.Connection) -> set[int]:
    cursor = conn.execute("SELECT codigo FROM cotacoes")
    return {row[0] for row in cursor.fetchall()}


def insert_records(conn: sqlite3.Connection, records: Iterable[dict[str, Any]]) -> tuple[int, int]:
    """Insere registros novos de forma idempotente (por `codigo`). Retorna (inseridos, ignorados)."""
    existing = get_existing_codes(conn)
    columns = ", ".join(SCHEMA_COLUMNS)
    placeholders = ", ".join(f":{c}" for c in SCHEMA_COLUMNS)
    insert_sql = f"INSERT INTO cotacoes ({columns}) VALUES ({placeholders})"

    inserted, skipped = 0, 0
    for record in records:
        codigo = record.get("codigo")
        if codigo is None:
            logger.warning("Registro sem código válido ignorado: %s", record)
            skipped += 1
            continue
        if codigo in existing:
            skipped += 1
            continue
        conn.execute(insert_sql, record)
        existing.add(codigo)
        inserted += 1
    conn.commit()
    return inserted, skipped


def move_to_processed(path: Path, processed_dir: Path) -> Path:
    processed_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    destination = processed_dir / f"{path.stem}_{timestamp}{path.suffix}"
    shutil.move(str(path), str(destination))
    return destination


def discover_input_files(directory: Path) -> list[Path]:
    files = list(directory.glob("*.csv")) + list(directory.glob("*.json"))
    return sorted(files)


def process_file(conn: sqlite3.Connection, path: Path) -> tuple[int, int]:
    try:
        if path.suffix.lower() == ".csv":
            records = read_csv_file(path)
        elif path.suffix.lower() == ".json":
            records = read_json_file(path)
        else:
            logger.warning("Extensão não suportada, ignorando arquivo: %s", path.name)
            return 0, 0
    except (OSError, json.JSONDecodeError, csv.Error) as exc:
        logger.error("Falha ao ler arquivo %s: %s", path.name, exc)
        return 0, 0

    inserted, skipped = insert_records(conn, records)
    logger.info(
        "Arquivo %s processado: %d registro(s) inserido(s), %d duplicado(s)/inválido(s) ignorado(s).",
        path.name, inserted, skipped,
    )
    return inserted, skipped


def run(input_dir: Path, db_path: Path, processed_dir: Path | None, move_processed: bool) -> None:
    logger.info("Iniciando pipeline de ingestão. Diretório: %s | Banco: %s", input_dir, db_path)

    if not input_dir.exists():
        logger.error("Diretório de entrada não encontrado: %s", input_dir)
        raise SystemExit(1)

    files = discover_input_files(input_dir)
    if not files:
        logger.info("Nenhum arquivo .csv/.json novo encontrado em %s.", input_dir)
        return

    conn = sqlite3.connect(str(db_path))
    total_inserted = total_skipped = 0
    try:
        for path in files:
            inserted, skipped = process_file(conn, path)
            total_inserted += inserted
            total_skipped += skipped
            if move_processed:
                try:
                    destination = move_to_processed(path, processed_dir or (input_dir / "processados"))
                    logger.info("Arquivo movido para %s", destination)
                except OSError as exc:
                    logger.error("Falha ao mover arquivo %s para processados: %s", path.name, exc)
    finally:
        conn.close()

    logger.info(
        "Pipeline concluído. Total inserido: %d | Total ignorado (duplicado/inválido): %d",
        total_inserted, total_skipped,
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ingestão idempotente de cotações (CSV/JSON) em cotacoes.db."
    )
    parser.add_argument(
        "--dir", required=True, type=Path,
        help="Diretório contendo os arquivos .csv/.json a serem ingeridos.",
    )
    parser.add_argument(
        "--db", default=DEFAULT_DB_PATH, type=Path,
        help=f"Caminho do banco SQLite (default: {DEFAULT_DB_PATH}).",
    )
    parser.add_argument(
        "--processados-dir", default=None, type=Path,
        help="Diretório de destino dos arquivos processados (default: <dir>/processados).",
    )
    parser.add_argument(
        "--no-move", action="store_true",
        help="Não move os arquivos processados para o diretório de processados.",
    )
    parser.add_argument(
        "--log-dir", default=BASE_DIR / "logs", type=Path,
        help="Diretório para os arquivos de log (default: <script_dir>/logs).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    setup_logging(args.log_dir)
    run(
        input_dir=args.dir,
        db_path=args.db,
        processed_dir=args.processados_dir,
        move_processed=not args.no_move,
    )


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Servidor Flask do dashboard de cotações.

Uso:
    python server.py [--db ../cotacoes.db] [--port 5000]
"""
from __future__ import annotations

import argparse
import calendar
import sqlite3
from datetime import date, datetime
from pathlib import Path

from flask import Flask, g, jsonify, request

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DB_PATH = BASE_DIR.parent / "cotacoes.db"

FORECAST_MIN_POINTS = 3
FORECAST_HORIZON_MONTHS = 3
FORECAST_SES_ALPHA = 0.3

app = Flask(__name__, static_folder=str(BASE_DIR), static_url_path="")
app.config["DB_PATH"] = str(DEFAULT_DB_PATH)

STATUS_TOGGLE_MAP = {
    "aprovadas": "APROVADO",
    "reprovadas": "REJEITADO",
    "estudo": "ESTUDO",
}

ALLOWED_TABLE_COLUMNS = {
    "codigo", "cliente", "criacao", "status", "modal",
    "paisorigem", "paisdestino", "vendedor", "lane",
}


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = sqlite3.connect(app.config["DB_PATH"])
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(_exception=None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


def build_filters(args) -> tuple[str, list]:
    """Monta a cláusula WHERE e os parâmetros a partir dos filtros da querystring."""
    clauses = []
    params: list = []

    lane = args.get("lane")
    if lane:
        clauses.append("lane = ?")
        params.append(lane)

    vendedor = args.get("vendedor")
    if vendedor:
        clauses.append("vendedor = ?")
        params.append(vendedor)

    data_inicio = args.get("data_inicio")
    if data_inicio:
        clauses.append("criacao >= ?")
        params.append(data_inicio)

    data_fim = args.get("data_fim")
    if data_fim:
        clauses.append("criacao <= ?")
        params.append(data_fim)

    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return where_sql, params


def simple_exponential_smoothing(y: list[float], alpha: float) -> float:
    """Suavização exponencial simples (Holt, sem tendência/sazonalidade).

    Escolhida em vez de extrapolar uma regressão linear porque o horizonte de
    projeção (meses) é muito maior que a janela observada (dias): extrapolar
    uma tendência linear tão além dos dados observados diverge rapidamente e
    é um erro clássico de previsão. SES produz uma projeção estável (nível),
    dando mais peso às observações recentes, sem assumir uma tendência que
    não pode ser confirmada com tão poucos pontos.
    """
    level = y[0]
    for value in y[1:]:
        level = alpha * value + (1 - alpha) * level
    return level


def add_months(d: date, months: int) -> date:
    month_index = d.month - 1 + months
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    return date(year, month, 1)


def build_forecast(db: sqlite3.Connection, where_sql: str, params: list) -> dict:
    """Projeta a demanda dos próximos meses a partir do histórico diário,
    usando Suavização Exponencial Simples (ver `simple_exponential_smoothing`)."""
    rows = db.execute(
        f"""
        SELECT date(criacao) AS dia, COUNT(*) AS quantidade
        FROM cotacoes
        {where_sql}
        GROUP BY dia
        ORDER BY dia
        """,
        params,
    ).fetchall()

    historico = [{"data": r["dia"], "quantidade": r["quantidade"]} for r in rows]

    if len(historico) < FORECAST_MIN_POINTS:
        return {
            "metodo": "suavizacao_exponencial_simples",
            "suficiente": False,
            "pontos_historico": len(historico),
            "meses": [],
        }

    y = [h["quantidade"] for h in historico]
    nivel_projetado = simple_exponential_smoothing(y, FORECAST_SES_ALPHA)

    # Meses reais: agrega o histórico observado por mês calendário.
    meses_reais: dict[str, int] = {}
    for h in historico:
        chave = h["data"][:7]
        meses_reais[chave] = meses_reais.get(chave, 0) + h["quantidade"]

    ultimo_dia = datetime.strptime(historico[-1]["data"], "%Y-%m-%d").date()
    mes_seguinte = add_months(date(ultimo_dia.year, ultimo_dia.month, 1), 1)

    meses_projetados: dict[str, float] = {}
    for offset in range(FORECAST_HORIZON_MONTHS):
        ano_mes = add_months(mes_seguinte, offset)
        chave = ano_mes.strftime("%Y-%m")
        dias_no_mes = calendar.monthrange(ano_mes.year, ano_mes.month)[1]
        meses_projetados[chave] = nivel_projetado * dias_no_mes

    meses = [
        {"mes": chave, "label": _format_mes_label(chave), "quantidade": valor, "tipo": "real"}
        for chave, valor in sorted(meses_reais.items())
    ] + [
        {"mes": chave, "label": _format_mes_label(chave), "quantidade": round(valor), "tipo": "projecao"}
        for chave, valor in sorted(meses_projetados.items())
    ]

    return {
        "metodo": "suavizacao_exponencial_simples",
        "suficiente": True,
        "pontos_historico": len(historico),
        "media_diaria_projetada": round(nivel_projetado, 2),
        "meses": meses,
    }


MESES_PT = [
    "Jan", "Fev", "Mar", "Abr", "Mai", "Jun",
    "Jul", "Ago", "Set", "Out", "Nov", "Dez",
]


def _format_mes_label(chave_ano_mes: str) -> str:
    ano, mes = chave_ano_mes.split("-")
    return f"{MESES_PT[int(mes) - 1]}/{ano}"


@app.route("/api/forecast")
def api_forecast():
    db = get_db()
    where_sql, params = build_filters(request.args)
    return jsonify(build_forecast(db, where_sql, params))


@app.route("/api/filtros")
def api_filtros():
    db = get_db()
    lanes = [r["lane"] for r in db.execute("SELECT DISTINCT lane FROM cotacoes ORDER BY lane")]
    vendedores = [r["vendedor"] for r in db.execute("SELECT DISTINCT vendedor FROM cotacoes ORDER BY vendedor")]
    return jsonify({"lanes": lanes, "vendedores": vendedores})


@app.route("/api/summary")
def api_summary():
    db = get_db()
    where_sql, params = build_filters(request.args)

    total = db.execute(f"SELECT COUNT(*) AS n FROM cotacoes {where_sql}", params).fetchone()["n"]

    top_vendedores = db.execute(
        f"""
        SELECT vendedor, COUNT(*) AS aprovadas
        FROM cotacoes
        {where_sql}{' AND' if where_sql else 'WHERE'} status = 'APROVADO'
        GROUP BY vendedor
        ORDER BY aprovadas DESC
        LIMIT 10
        """,
        params,
    ).fetchall()

    status_toggle = request.args.get("status_toggle", "aprovadas")
    status_value = STATUS_TOGGLE_MAP.get(status_toggle, "APROVADO")
    volume_mensal = db.execute(
        f"""
        SELECT CAST(strftime('%m', criacao) AS INTEGER) AS mes, COUNT(*) AS quantidade
        FROM cotacoes
        {where_sql}{' AND' if where_sql else 'WHERE'} status = ?
        GROUP BY mes
        ORDER BY mes
        """,
        params + [status_value],
    ).fetchall()

    status_distribution = db.execute(
        f"""
        SELECT status, COUNT(*) AS quantidade
        FROM cotacoes
        {where_sql}{' AND' if where_sql else 'WHERE'} status IN ('APROVADO', 'REJEITADO', 'ESTUDO', 'SEGUNDA OPCAO')
        GROUP BY status
        """,
        params,
    ).fetchall()

    lane_distribution = db.execute(
        f"""
        SELECT lane, COUNT(*) AS quantidade
        FROM cotacoes
        {where_sql}
        GROUP BY lane
        ORDER BY quantidade DESC
        """,
        params,
    ).fetchall()

    return jsonify({
        "total_cotacoes": total,
        "top_vendedores": [dict(r) for r in top_vendedores],
        "volume_mensal": [dict(r) for r in volume_mensal],
        "status_distribution": [dict(r) for r in status_distribution],
        "lane_distribution": [dict(r) for r in lane_distribution],
    })


@app.route("/api/cotacoes")
def api_cotacoes():
    db = get_db()
    where_sql, params = build_filters(request.args)

    page = max(int(request.args.get("page", 1)), 1)
    per_page = min(max(int(request.args.get("per_page", 15)), 1), 100)
    offset = (page - 1) * per_page

    total = db.execute(f"SELECT COUNT(*) AS n FROM cotacoes {where_sql}", params).fetchone()["n"]

    rows = db.execute(
        f"""
        SELECT codigo, cliente, criacao, status, modal, paisorigem, paisdestino, vendedor, lane
        FROM cotacoes
        {where_sql}
        ORDER BY criacao DESC, codigo DESC
        LIMIT ? OFFSET ?
        """,
        params + [per_page, offset],
    ).fetchall()

    return jsonify({
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": max((total + per_page - 1) // per_page, 1),
        "items": [dict(r) for r in rows],
    })


@app.route("/")
def index():
    return app.send_static_file("index.html")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Servidor do dashboard de cotações.")
    parser.add_argument("--db", default=DEFAULT_DB_PATH, type=Path, help="Caminho do banco SQLite.")
    parser.add_argument("--port", default=5000, type=int, help="Porta HTTP.")
    parser.add_argument("--host", default="127.0.0.1", help="Host de bind.")
    parser.add_argument("--debug", action="store_true", help="Ativa modo debug do Flask.")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    app.config["DB_PATH"] = str(args.db)
    app.run(host=args.host, port=args.port, debug=args.debug)

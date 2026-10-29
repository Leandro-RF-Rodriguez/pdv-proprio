"""Servidor central do PDV (Fase 2).

Recebe produtos e vendas enviados por um ou mais PDVs e guarda tudo num
banco próprio (dados/central.db). É IDEMPOTENTE: se o mesmo registro chegar duas
vezes (identificado pelo uuid), ele ignora a repetição em vez de duplicar.

Rodar com:  python3 -m servidor.central   (a partir da raiz do projeto)
Fica escutando em http://127.0.0.1:5001

Segurança: defina PDV_SYNC_TOKEN (mesmo valor no PDV) para exigir o token em
/sync/*. Obrigatório antes de expor o servidor fora desta máquina.
"""

import hmac
import os
import sqlite3
from contextlib import closing

from flask import Flask, abort, jsonify, request

PASTA_DADOS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dados")
BANCO_CENTRAL = os.path.join(PASTA_DADOS, "central.db")
TOKEN = os.environ.get("PDV_SYNC_TOKEN")

SCHEMA = """
CREATE TABLE IF NOT EXISTS produtos (
    uuid TEXT PRIMARY KEY,
    codigo TEXT,
    descricao TEXT,
    preco_centavos INTEGER,
    ativo INTEGER,
    criado_em TEXT,
    atualizado_em TEXT
);
CREATE TABLE IF NOT EXISTS vendas (
    uuid TEXT PRIMARY KEY,
    total_centavos INTEGER,
    status TEXT,
    criado_em TEXT
);
CREATE TABLE IF NOT EXISTS itens_venda (
    venda_uuid TEXT,
    produto_uuid TEXT,
    quantidade REAL,
    preco_unit_centavos INTEGER,
    subtotal_centavos INTEGER
);
CREATE TABLE IF NOT EXISTS pagamentos (
    venda_uuid TEXT,
    forma TEXT,
    valor_centavos INTEGER
);
"""

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # recusa corpos gigantes


def conectar():
    conexao = sqlite3.connect(BANCO_CENTRAL)
    conexao.row_factory = sqlite3.Row
    return conexao


def inicializar():
    os.makedirs(PASTA_DADOS, exist_ok=True)
    with closing(conectar()) as conexao:
        conexao.executescript(SCHEMA)


def _lista_recebida():
    """Corpo JSON validado: lista de objetos, cada um com uuid. Senão, 400."""
    dados = request.get_json(silent=True)
    if not isinstance(dados, list) or not all(isinstance(d, dict) and d.get("uuid") for d in dados):
        abort(400, "Esperado: lista JSON de registros com 'uuid'.")
    return dados


@app.before_request
def _exigir_token():
    if TOKEN and request.path.startswith("/sync/"):
        enviado = request.headers.get("Authorization", "").removeprefix("Bearer ")
        if not hmac.compare_digest(enviado, TOKEN):
            abort(401)


@app.route("/sync/produtos", methods=["POST"])
def sync_produtos():
    produtos = _lista_recebida()
    with closing(conectar()) as conexao, conexao:
        # INSERT OR REPLACE pelo uuid: cria ou atualiza, nunca duplica.
        conexao.executemany(
            """INSERT OR REPLACE INTO produtos
               (uuid, codigo, descricao, preco_centavos, ativo, criado_em, atualizado_em)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            [
                (p["uuid"], p.get("codigo"), p.get("descricao"), p.get("preco_centavos"),
                 p.get("ativo"), p.get("criado_em"), p.get("atualizado_em"))
                for p in produtos
            ],
        )
    return jsonify({"recebidos": len(produtos)}), 200


@app.route("/sync/vendas", methods=["POST"])
def sync_vendas():
    vendas = _lista_recebida()
    novas = 0
    with closing(conectar()) as conexao, conexao:
        for v in vendas:
            inserida = conexao.execute(
                "INSERT OR IGNORE INTO vendas (uuid, total_centavos, status, criado_em) VALUES (?, ?, ?, ?)",
                (v["uuid"], v.get("total_centavos"), v.get("status"), v.get("criado_em")),
            ).rowcount
            if not inserida:
                continue  # idempotência: já temos esta venda
            conexao.executemany(
                """INSERT INTO itens_venda
                   (venda_uuid, produto_uuid, quantidade, preco_unit_centavos, subtotal_centavos)
                   VALUES (?, ?, ?, ?, ?)""",
                [
                    (v["uuid"], i.get("produto_uuid"), i.get("quantidade"),
                     i.get("preco_unit_centavos"), i.get("subtotal_centavos"))
                    for i in v.get("itens", [])
                ],
            )
            conexao.executemany(
                "INSERT INTO pagamentos (venda_uuid, forma, valor_centavos) VALUES (?, ?, ?)",
                [(v["uuid"], pg.get("forma"), pg.get("valor_centavos")) for pg in v.get("pagamentos", [])],
            )
            novas += 1
    return jsonify({"novas": novas, "ignoradas": len(vendas) - novas}), 200


@app.route("/status", methods=["GET"])
def status():
    with closing(conectar()) as conexao:
        prod, vend, total = conexao.execute(
            """SELECT (SELECT COUNT(*) FROM produtos), (SELECT COUNT(*) FROM vendas),
                      (SELECT COALESCE(SUM(total_centavos), 0) FROM vendas)"""
        ).fetchone()
    return jsonify({"produtos": prod, "vendas": vend, "total_vendido_centavos": total})


if __name__ == "__main__":
    inicializar()
    app.run(host="127.0.0.1", port=5001)

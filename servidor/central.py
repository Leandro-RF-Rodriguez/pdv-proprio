"""Servidor central do PDV (Fase 2).

Recebe produtos e vendas enviados por um ou mais PDVs e guarda tudo num
banco próprio (dados/central.db). É IDEMPOTENTE: se o mesmo registro chegar duas
vezes (identificado pelo uuid), ele ignora a repetição em vez de duplicar.

Rodar com:  python3 -m servidor.central   (a partir da raiz do projeto)
Fica escutando em http://127.0.0.1:5001
"""

import os
import sqlite3
from flask import Flask, request, jsonify

PASTA_DADOS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dados")
BANCO_CENTRAL = os.path.join(PASTA_DADOS, "central.db")

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


def conectar():
    conexao = sqlite3.connect(BANCO_CENTRAL)
    conexao.row_factory = sqlite3.Row
    return conexao


def inicializar():
    os.makedirs(PASTA_DADOS, exist_ok=True)
    conexao = conectar()
    conexao.executescript(SCHEMA)
    conexao.close()


@app.route("/sync/produtos", methods=["POST"])
def sync_produtos():
    produtos = request.get_json() or []
    conexao = conectar()
    recebidos = 0
    for p in produtos:
        # INSERT OR REPLACE pelo uuid: cria ou atualiza, nunca duplica.
        conexao.execute(
            """INSERT OR REPLACE INTO produtos
               (uuid, codigo, descricao, preco_centavos, ativo, criado_em, atualizado_em)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                p["uuid"], p.get("codigo"), p.get("descricao"),
                p.get("preco_centavos"), p.get("ativo"),
                p.get("criado_em"), p.get("atualizado_em"),
            ),
        )
        recebidos += 1
    conexao.commit()
    conexao.close()
    return jsonify({"recebidos": recebidos}), 200


@app.route("/sync/vendas", methods=["POST"])
def sync_vendas():
    vendas = request.get_json() or []
    conexao = conectar()
    novas, ignoradas = 0, 0
    for v in vendas:
        existe = conexao.execute(
            "SELECT 1 FROM vendas WHERE uuid = ?", (v["uuid"],)
        ).fetchone()
        if existe:
            ignoradas += 1  # idempotência: já temos esta venda
            continue
        conexao.execute(
            "INSERT INTO vendas (uuid, total_centavos, status, criado_em) VALUES (?, ?, ?, ?)",
            (v["uuid"], v.get("total_centavos"), v.get("status"), v.get("criado_em")),
        )
        for item in v.get("itens", []):
            conexao.execute(
                """INSERT INTO itens_venda
                   (venda_uuid, produto_uuid, quantidade, preco_unit_centavos, subtotal_centavos)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    v["uuid"], item.get("produto_uuid"), item.get("quantidade"),
                    item.get("preco_unit_centavos"), item.get("subtotal_centavos"),
                ),
            )
        for pg in v.get("pagamentos", []):
            conexao.execute(
                "INSERT INTO pagamentos (venda_uuid, forma, valor_centavos) VALUES (?, ?, ?)",
                (v["uuid"], pg.get("forma"), pg.get("valor_centavos")),
            )
        novas += 1
    conexao.commit()
    conexao.close()
    return jsonify({"novas": novas, "ignoradas": ignoradas}), 200


@app.route("/status", methods=["GET"])
def status():
    conexao = conectar()
    prod = conexao.execute("SELECT COUNT(*) FROM produtos").fetchone()[0]
    vend = conexao.execute("SELECT COUNT(*) FROM vendas").fetchone()[0]
    total = conexao.execute("SELECT COALESCE(SUM(total_centavos), 0) FROM vendas").fetchone()[0]
    conexao.close()
    return jsonify({"produtos": prod, "vendas": vend, "total_vendido_centavos": total})


if __name__ == "__main__":
    inicializar()
    app.run(host="127.0.0.1", port=5001)

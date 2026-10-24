import sqlite3
import uuid
from datetime import datetime
from flask import Flask, request, jsonify

app = Flask(__name__)

def conectar():
    conexao = sqlite3.connect("pdv.db")
    conexao.row_factory = sqlite3.Row  # permite acessar colunas pelo nome
    return conexao

def agora():
    return datetime.now().isoformat(timespec="seconds")

@app.route("/produtos", methods=["GET"])
def listar_produtos():
    conexao = conectar()
    linhas = conexao.execute(
        "SELECT * FROM produtos WHERE ativo = 1 ORDER BY descricao"
    ).fetchall()
    conexao.close()
    return jsonify([dict(linha) for linha in linhas])

@app.route("/produtos", methods=["POST"])
def cadastrar_produto():
    dados = request.get_json()
    if not dados or "descricao" not in dados:
        return jsonify({"erro": "descricao é obrigatória"}), 400

    momento = agora()
    conexao = conectar()
    cursor = conexao.execute(
        """INSERT INTO produtos
           (uuid, codigo, descricao, preco, ativo, criado_em, atualizado_em)
           VALUES (?, ?, ?, ?, 1, ?, ?)""",
        (
            str(uuid.uuid4()),
            dados.get("codigo"),
            dados["descricao"],
            dados.get("preco", 0),
            momento,
            momento,
        ),
    )
    conexao.commit()
    novo_id = cursor.lastrowid
    conexao.close()
    return jsonify({"id": novo_id, "mensagem": "Produto cadastrado"}), 201

if __name__ == "__main__":
    app.run(debug=True, port=5000)

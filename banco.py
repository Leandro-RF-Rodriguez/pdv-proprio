"""Camada de acesso ao banco de dados (SQLite).

Mantém toda a conversa com o banco separada da interface.
Regra importante: valores em dinheiro andam sempre em CENTAVOS (inteiro).
Ex.: R$ 5,50 vira 550. A conversão para texto só acontece na exibição.
"""

import os
import sqlite3
import sys
import uuid
from datetime import datetime


def _caminho_recurso(nome):
    """Acha um arquivo que acompanha o app (ex.: schema.sql).

    Quando empacotado pelo PyInstaller, os recursos ficam em sys._MEIPASS.
    Rodando pelo código-fonte, ficam na pasta deste arquivo.
    """
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, nome)


# Onde guardar o banco:
# - empacotado (executável): numa pasta fixa no perfil do usuário
# - rodando o código: na própria pasta do projeto (facilita o desenvolvimento)
if getattr(sys, "frozen", False):
    PASTA_DADOS = os.path.join(os.path.expanduser("~"), ".pdv_proprio")
else:
    PASTA_DADOS = os.path.dirname(os.path.abspath(__file__))

CAMINHO_BANCO = os.path.join(PASTA_DADOS, "pdv.db")


def inicializar():
    """Cria a pasta de dados e o banco (a partir do schema) se ainda não existirem."""
    os.makedirs(PASTA_DADOS, exist_ok=True)
    if not os.path.exists(CAMINHO_BANCO):
        conexao = sqlite3.connect(CAMINHO_BANCO)
        with open(_caminho_recurso("schema.sql"), "r", encoding="utf-8") as arquivo:
            conexao.executescript(arquivo.read())
        conexao.close()
    _migrar()


def _coluna_existe(conexao, tabela, coluna):
    colunas = [linha[1] for linha in conexao.execute(f"PRAGMA table_info({tabela})").fetchall()]
    return coluna in colunas


def _migrar():
    """Migrações leves: adiciona colunas novas sem apagar dados existentes."""
    conexao = conectar()
    for tabela in ("produtos", "vendas"):
        if not _coluna_existe(conexao, tabela, "sincronizado"):
            conexao.execute(
                f"ALTER TABLE {tabela} ADD COLUMN sincronizado INTEGER NOT NULL DEFAULT 0"
            )
    conexao.commit()
    conexao.close()


class CodigoDuplicado(Exception):
    """Lançada quando se tenta cadastrar um código de barras já usado."""


class CaixaJaAberto(Exception):
    """Lançada ao tentar abrir um caixa com outro já aberto."""


# ---------- Conversão de dinheiro ----------
def para_centavos(valor_reais):
    """Converte reais (float ou texto '5,50') para centavos inteiros."""
    if isinstance(valor_reais, str):
        valor_reais = valor_reais.replace(",", ".")
    return round(float(valor_reais) * 100)


def formatar_reais(centavos):
    """Converte centavos (inteiro) para texto '5,50'."""
    return f"{centavos / 100:.2f}".replace(".", ",")


# ---------- Infra ----------
def conectar():
    conexao = sqlite3.connect(CAMINHO_BANCO)
    conexao.row_factory = sqlite3.Row  # acessar colunas pelo nome
    return conexao


def agora():
    return datetime.now().isoformat(timespec="seconds")


# ---------- Produtos ----------
def listar_produtos():
    """Retorna os produtos ativos, em ordem alfabética."""
    conexao = conectar()
    linhas = conexao.execute(
        "SELECT * FROM produtos WHERE ativo = 1 ORDER BY descricao COLLATE NOCASE"
    ).fetchall()
    conexao.close()
    return [dict(linha) for linha in linhas]


def cadastrar_produto(descricao, codigo=None, preco_centavos=0):
    """Insere um produto novo e devolve o id gerado.

    Lança CodigoDuplicado se o código de barras já existir.
    """
    momento = agora()
    conexao = conectar()
    try:
        cursor = conexao.execute(
            """INSERT INTO produtos
               (uuid, codigo, descricao, preco_centavos, ativo, criado_em, atualizado_em)
               VALUES (?, ?, ?, ?, 1, ?, ?)""",
            (str(uuid.uuid4()), codigo, descricao, preco_centavos, momento, momento),
        )
        conexao.commit()
        novo_id = cursor.lastrowid
    except sqlite3.IntegrityError:
        # Único campo UNIQUE que o usuário controla é o código.
        raise CodigoDuplicado(codigo)
    finally:
        conexao.close()
    return novo_id


def buscar_produto_por_codigo(codigo):
    """Retorna o produto ativo com esse código, ou None."""
    conexao = conectar()
    linha = conexao.execute(
        "SELECT * FROM produtos WHERE codigo = ? AND ativo = 1", (codigo,)
    ).fetchone()
    conexao.close()
    return dict(linha) if linha else None


# ---------- Vendas ----------
def registrar_venda(itens, pagamentos, sessao_id=None):
    """Grava uma venda inteira de forma ATÔMICA.

    itens: lista de {produto_id, quantidade, preco_unit_centavos}
    pagamentos: lista de {forma, valor_centavos}

    Ou grava tudo (venda + itens + pagamentos), ou nada (rollback).
    Devolve (venda_id, total_centavos).
    """
    total = sum(round(i["quantidade"] * i["preco_unit_centavos"]) for i in itens)
    momento = agora()
    conexao = conectar()
    try:
        cursor = conexao.execute(
            """INSERT INTO vendas (uuid, sessao_id, total_centavos, status, criado_em)
               VALUES (?, ?, ?, 'concluida', ?)""",
            (str(uuid.uuid4()), sessao_id, total, momento),
        )
        venda_id = cursor.lastrowid

        for item in itens:
            subtotal = round(item["quantidade"] * item["preco_unit_centavos"])
            conexao.execute(
                """INSERT INTO itens_venda
                   (venda_id, produto_id, quantidade, preco_unit_centavos, subtotal_centavos)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    venda_id,
                    item["produto_id"],
                    item["quantidade"],
                    item["preco_unit_centavos"],
                    subtotal,
                ),
            )

        for pagamento in pagamentos:
            conexao.execute(
                "INSERT INTO pagamentos (venda_id, forma, valor_centavos) VALUES (?, ?, ?)",
                (venda_id, pagamento["forma"], pagamento["valor_centavos"]),
            )

        conexao.commit()  # confirma tudo de uma vez
    except Exception:
        conexao.rollback()  # qualquer erro desfaz a venda inteira
        raise
    finally:
        conexao.close()

    return venda_id, total


# ---------- Caixa ----------
def sessao_aberta():
    """Retorna a sessão de caixa aberta (sem fechamento), ou None."""
    conexao = conectar()
    linha = conexao.execute(
        "SELECT * FROM sessoes_caixa WHERE fechado_em IS NULL ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conexao.close()
    return dict(linha) if linha else None


def abrir_caixa(operador, abertura_centavos=0):
    """Abre uma sessão de caixa. Lança CaixaJaAberto se já houver uma aberta."""
    if sessao_aberta():
        raise CaixaJaAberto()
    momento = agora()
    conexao = conectar()
    cursor = conexao.execute(
        """INSERT INTO sessoes_caixa (uuid, operador, abertura_centavos, aberto_em)
           VALUES (?, ?, ?, ?)""",
        (str(uuid.uuid4()), operador, abertura_centavos, momento),
    )
    conexao.commit()
    sessao_id = cursor.lastrowid
    conexao.close()
    return sessao_id


def registrar_movimento_caixa(sessao_id, tipo, valor_centavos, motivo=None):
    """tipo: 'sangria' (retira dinheiro) ou 'suprimento' (coloca dinheiro)."""
    momento = agora()
    conexao = conectar()
    conexao.execute(
        """INSERT INTO movimentos_caixa
           (uuid, sessao_id, tipo, valor_centavos, motivo, criado_em)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (str(uuid.uuid4()), sessao_id, tipo, valor_centavos, motivo, momento),
    )
    conexao.commit()
    conexao.close()


def resumo_caixa(sessao_id):
    """Resumo financeiro de uma sessão de caixa (tudo em centavos)."""
    conexao = conectar()
    sessao = dict(
        conexao.execute(
            "SELECT * FROM sessoes_caixa WHERE id = ?", (sessao_id,)
        ).fetchone()
    )
    suprimentos = conexao.execute(
        "SELECT COALESCE(SUM(valor_centavos), 0) FROM movimentos_caixa "
        "WHERE sessao_id = ? AND tipo = 'suprimento'",
        (sessao_id,),
    ).fetchone()[0]
    sangrias = conexao.execute(
        "SELECT COALESCE(SUM(valor_centavos), 0) FROM movimentos_caixa "
        "WHERE sessao_id = ? AND tipo = 'sangria'",
        (sessao_id,),
    ).fetchone()[0]
    vendas_dinheiro = conexao.execute(
        """SELECT COALESCE(SUM(p.valor_centavos), 0)
           FROM pagamentos p JOIN vendas v ON v.id = p.venda_id
           WHERE v.sessao_id = ? AND v.status = 'concluida' AND p.forma = 'Dinheiro'""",
        (sessao_id,),
    ).fetchone()[0]
    vendas_total = conexao.execute(
        "SELECT COALESCE(SUM(total_centavos), 0) FROM vendas "
        "WHERE sessao_id = ? AND status = 'concluida'",
        (sessao_id,),
    ).fetchone()[0]
    conexao.close()

    # O que deve haver na gaveta: só dinheiro entra/sai dela.
    esperado = sessao["abertura_centavos"] + suprimentos + vendas_dinheiro - sangrias
    return {
        "abertura": sessao["abertura_centavos"],
        "suprimentos": suprimentos,
        "sangrias": sangrias,
        "vendas_dinheiro": vendas_dinheiro,
        "vendas_total": vendas_total,
        "esperado_gaveta": esperado,
    }


def fechar_caixa(sessao_id, fechamento_centavos):
    """Fecha a sessão gravando o valor contado na gaveta."""
    momento = agora()
    conexao = conectar()
    conexao.execute(
        "UPDATE sessoes_caixa SET fechado_em = ?, fechamento_centavos = ? WHERE id = ?",
        (momento, fechamento_centavos, sessao_id),
    )
    conexao.commit()
    conexao.close()


# ---------- Relatório ----------
def relatorio_dia(data=None):
    """Resumo das vendas de um dia (padrão: hoje). Valores em centavos."""
    if data is None:
        data = datetime.now().strftime("%Y-%m-%d")
    conexao = conectar()
    qtd, total = conexao.execute(
        "SELECT COUNT(*), COALESCE(SUM(total_centavos), 0) FROM vendas "
        "WHERE status = 'concluida' AND substr(criado_em, 1, 10) = ?",
        (data,),
    ).fetchone()
    por_forma = conexao.execute(
        """SELECT p.forma, SUM(p.valor_centavos)
           FROM pagamentos p JOIN vendas v ON v.id = p.venda_id
           WHERE v.status = 'concluida' AND substr(v.criado_em, 1, 10) = ?
           GROUP BY p.forma ORDER BY p.forma""",
        (data,),
    ).fetchall()
    conexao.close()
    return {
        "data": data,
        "qtd": qtd,
        "total": total,
        "por_forma": [(linha[0], linha[1]) for linha in por_forma],
    }


# ---------- Sincronização (Fase 2) ----------
def produtos_pendentes():
    """Produtos ainda não enviados ao servidor central."""
    conexao = conectar()
    linhas = conexao.execute("SELECT * FROM produtos WHERE sincronizado = 0").fetchall()
    conexao.close()
    return [dict(linha) for linha in linhas]


def vendas_pendentes():
    """Vendas pendentes, já com seus itens e pagamentos prontos para enviar."""
    conexao = conectar()
    vendas = [
        dict(linha)
        for linha in conexao.execute(
            "SELECT * FROM vendas WHERE sincronizado = 0 AND status = 'concluida'"
        ).fetchall()
    ]
    for venda in vendas:
        venda["itens"] = [
            dict(linha)
            for linha in conexao.execute(
                """SELECT iv.quantidade, iv.preco_unit_centavos, iv.subtotal_centavos,
                          p.uuid AS produto_uuid
                   FROM itens_venda iv JOIN produtos p ON p.id = iv.produto_id
                   WHERE iv.venda_id = ?""",
                (venda["id"],),
            ).fetchall()
        ]
        venda["pagamentos"] = [
            dict(linha)
            for linha in conexao.execute(
                "SELECT forma, valor_centavos FROM pagamentos WHERE venda_id = ?",
                (venda["id"],),
            ).fetchall()
        ]
    conexao.close()
    return vendas


def marcar_produto_sincronizado(uuid_produto):
    conexao = conectar()
    conexao.execute("UPDATE produtos SET sincronizado = 1 WHERE uuid = ?", (uuid_produto,))
    conexao.commit()
    conexao.close()


def marcar_venda_sincronizada(uuid_venda):
    conexao = conectar()
    conexao.execute("UPDATE vendas SET sincronizado = 1 WHERE uuid = ?", (uuid_venda,))
    conexao.commit()
    conexao.close()


def contar_pendentes():
    conexao = conectar()
    produtos = conexao.execute(
        "SELECT COUNT(*) FROM produtos WHERE sincronizado = 0"
    ).fetchone()[0]
    vendas = conexao.execute(
        "SELECT COUNT(*) FROM vendas WHERE sincronizado = 0 AND status = 'concluida'"
    ).fetchone()[0]
    conexao.close()
    return {"produtos": produtos, "vendas": vendas}


# ---------- Produtos: editar e excluir ----------
def atualizar_produto(produto_id, descricao, codigo, preco_centavos):
    """Altera um produto existente. Lança CodigoDuplicado se o código colidir."""
    momento = agora()
    conexao = conectar()
    try:
        conexao.execute(
            """UPDATE produtos
               SET descricao = ?, codigo = ?, preco_centavos = ?,
                   sincronizado = 0, atualizado_em = ?
               WHERE id = ?""",
            (descricao, codigo, preco_centavos, momento, produto_id),
        )
        conexao.commit()
    except sqlite3.IntegrityError:
        raise CodigoDuplicado(codigo)
    finally:
        conexao.close()


def inativar_produto(produto_id):
    """Exclusão lógica: marca ativo = 0 (não apaga o histórico de vendas)."""
    momento = agora()
    conexao = conectar()
    conexao.execute(
        "UPDATE produtos SET ativo = 0, sincronizado = 0, atualizado_em = ? WHERE id = ?",
        (momento, produto_id),
    )
    conexao.commit()
    conexao.close()


# ---------- Histórico de vendas ----------
def listar_vendas(limite=200):
    """Vendas concluídas, mais recentes primeiro, com resumo de itens e formas."""
    conexao = conectar()
    linhas = conexao.execute(
        """SELECT v.id, v.total_centavos, v.criado_em,
                  (SELECT COUNT(*) FROM itens_venda WHERE venda_id = v.id) AS qtd_itens,
                  (SELECT GROUP_CONCAT(forma, ', ') FROM pagamentos WHERE venda_id = v.id) AS formas
           FROM vendas v
           WHERE v.status = 'concluida'
           ORDER BY v.id DESC
           LIMIT ?""",
        (limite,),
    ).fetchall()
    conexao.close()
    return [dict(linha) for linha in linhas]

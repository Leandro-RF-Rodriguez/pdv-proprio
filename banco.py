"""Camada de acesso ao banco de dados (SQLite).

Mantém toda a conversa com o banco separada da interface.
Regra importante: valores em dinheiro andam sempre em CENTAVOS (inteiro).
Ex.: R$ 5,50 vira 550. A conversão para texto só acontece na exibição.
"""

import hashlib
import os
import secrets
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
    _garantir_master()


def _coluna_existe(conexao, tabela, coluna):
    colunas = [linha[1] for linha in conexao.execute(f"PRAGMA table_info({tabela})").fetchall()]
    return coluna in colunas


def _migrar():
    """Migrações leves: adiciona colunas e tabelas novas sem apagar dados."""
    conexao = conectar()
    # Marca de sincronização (Fase 2)
    for tabela in ("produtos", "vendas"):
        if not _coluna_existe(conexao, tabela, "sincronizado"):
            conexao.execute(
                f"ALTER TABLE {tabela} ADD COLUMN sincronizado INTEGER NOT NULL DEFAULT 0"
            )
    # Campos do produto adicionados na Fase 3 (fiscais + estoque/custo/categoria)
    colunas_produto = {
        "codigo_interno": "TEXT", "categoria": "TEXT",
        "custo_centavos": "INTEGER DEFAULT 0", "estoque": "REAL DEFAULT 0",
        "controla_estoque": "INTEGER DEFAULT 0",
        "unidade": "TEXT DEFAULT 'UN'", "tipo_item": "TEXT DEFAULT '00'",
        "ncm": "TEXT", "cest": "TEXT", "cfop": "TEXT",
        "origem": "TEXT DEFAULT '0'", "cst": "TEXT",
        "aliquota_icms": "REAL DEFAULT 0", "aliquota_aprox": "REAL DEFAULT 0",
    }
    for coluna, tipo in colunas_produto.items():
        if not _coluna_existe(conexao, "produtos", coluna):
            conexao.execute(f"ALTER TABLE produtos ADD COLUMN {coluna} {tipo}")
    # Usuários e papéis
    conexao.execute(
        """CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uuid TEXT NOT NULL UNIQUE,
            login TEXT NOT NULL UNIQUE,
            senha_hash TEXT NOT NULL,
            papel TEXT NOT NULL DEFAULT 'operador',
            ativo INTEGER NOT NULL DEFAULT 1,
            criado_em TEXT NOT NULL
        )"""
    )
    # Configuração fiscal (uma linha só, id = 1) — dados sensíveis
    conexao.execute(
        """CREATE TABLE IF NOT EXISTS config_fiscal (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            razao_social TEXT, cnpj TEXT, ie TEXT, uf TEXT,
            ambiente TEXT DEFAULT 'homologacao',
            certificado_caminho TEXT, certificado_senha TEXT,
            csc TEXT, csc_id TEXT,
            atualizado_em TEXT
        )"""
    )
    # Cadastro detalhado: colunas extras de usuários e da empresa/config fiscal
    for coluna in ("nome", "email"):
        if not _coluna_existe(conexao, "usuarios", coluna):
            conexao.execute(f"ALTER TABLE usuarios ADD COLUMN {coluna} TEXT")
    for coluna in (
        "nome_fantasia", "im", "crt", "cep", "logradouro", "numero",
        "complemento", "bairro", "municipio", "cod_municipio",
        "telefone", "email", "serie", "proximo_numero",
    ):
        if not _coluna_existe(conexao, "config_fiscal", coluna):
            conexao.execute(f"ALTER TABLE config_fiscal ADD COLUMN {coluna} TEXT")
    conexao.commit()
    conexao.close()


class CodigoDuplicado(Exception):
    """Lançada quando se tenta cadastrar um código de barras já usado."""


class CaixaJaAberto(Exception):
    """Lançada ao tentar abrir um caixa com outro já aberto."""


class LoginDuplicado(Exception):
    """Lançada ao criar um usuário com login já existente."""


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


# Colunas do produto preenchidas pelo cadastro/edição (fora uuid, ativo, datas).
COLUNAS_PRODUTO = [
    "codigo", "codigo_interno", "descricao", "categoria", "unidade", "tipo_item",
    "preco_centavos", "custo_centavos", "estoque", "controla_estoque",
    "ncm", "cest", "cfop", "origem", "cst", "aliquota_icms", "aliquota_aprox",
]

_PADROES_PRODUTO = {
    "codigo": None, "codigo_interno": None, "descricao": None, "categoria": None,
    "unidade": "UN", "tipo_item": "00", "preco_centavos": 0, "custo_centavos": 0,
    "estoque": 0, "controla_estoque": 0, "ncm": None, "cest": None, "cfop": None,
    "origem": "0", "cst": None, "aliquota_icms": 0, "aliquota_aprox": 0,
}


def _valores_produto(dados):
    valores = dict(_PADROES_PRODUTO)
    valores.update({k: v for k, v in dados.items() if k in _PADROES_PRODUTO})
    return valores


def cadastrar_produto(dados):
    """Insere um produto. `dados` é um dict (ver COLUNAS_PRODUTO).

    Lança CodigoDuplicado se o código de barras já existir.
    """
    valores = _valores_produto(dados)
    momento = agora()
    conexao = conectar()
    try:
        colunas = ", ".join(COLUNAS_PRODUTO)
        marcadores = ", ".join("?" for _ in COLUNAS_PRODUTO)
        cursor = conexao.execute(
            f"""INSERT INTO produtos (uuid, ativo, {colunas}, criado_em, atualizado_em)
                VALUES (?, 1, {marcadores}, ?, ?)""",
            [str(uuid.uuid4())] + [valores[c] for c in COLUNAS_PRODUTO] + [momento, momento],
        )
        conexao.commit()
        novo_id = cursor.lastrowid
    except sqlite3.IntegrityError:
        raise CodigoDuplicado(valores["codigo"])
    finally:
        conexao.close()
    return novo_id


def obter_produto(produto_id):
    """Retorna um produto por id (ativo ou inativo), ou None."""
    conexao = conectar()
    linha = conexao.execute("SELECT * FROM produtos WHERE id = ?", (produto_id,)).fetchone()
    conexao.close()
    return dict(linha) if linha else None


def buscar_produtos(filtros=None):
    """Pesquisa produtos por filtros. Retorna todos os campos.

    filtros: {
        texto: casa com descrição, código EAN ou código interno,
        status: 'ativos' | 'inativos' | 'todos',
        controla: None | 0 | 1,
        ncm, cfop, cst, origem, categoria: trechos (LIKE),
    }
    """
    filtros = filtros or {}
    clausulas, params = [], []

    status = filtros.get("status", "ativos")
    if status == "ativos":
        clausulas.append("ativo = 1")
    elif status == "inativos":
        clausulas.append("ativo = 0")

    texto = (filtros.get("texto") or "").strip()
    if texto:
        clausulas.append("(descricao LIKE ? OR codigo LIKE ? OR codigo_interno LIKE ?)")
        like = f"%{texto}%"
        params += [like, like, like]

    controla = filtros.get("controla")
    if controla in (0, 1):
        clausulas.append("controla_estoque = ?")
        params.append(controla)

    for campo in ("ncm", "cfop", "cst", "origem", "categoria"):
        valor = (filtros.get(campo) or "").strip()
        if valor:
            clausulas.append(f"{campo} LIKE ?")
            params.append(f"%{valor}%")

    onde = ("WHERE " + " AND ".join(clausulas)) if clausulas else ""
    conexao = conectar()
    linhas = conexao.execute(
        f"SELECT * FROM produtos {onde} ORDER BY descricao COLLATE NOCASE", params
    ).fetchall()
    conexao.close()
    return [dict(linha) for linha in linhas]


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
def atualizar_produto(produto_id, dados):
    """Altera um produto existente. `dados` é um dict (ver COLUNAS_PRODUTO).

    Lança CodigoDuplicado se o código colidir.
    """
    valores = _valores_produto(dados)
    momento = agora()
    conexao = conectar()
    try:
        atribuicoes = ", ".join(f"{c} = ?" for c in COLUNAS_PRODUTO)
        conexao.execute(
            f"""UPDATE produtos SET {atribuicoes}, sincronizado = 0, atualizado_em = ?
                WHERE id = ?""",
            [valores[c] for c in COLUNAS_PRODUTO] + [momento, produto_id],
        )
        conexao.commit()
    except sqlite3.IntegrityError:
        raise CodigoDuplicado(valores["codigo"])
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


# ---------- Usuários e papéis (Fase 3) ----------
def _hash_senha(senha, salt=None):
    """Gera 'salt$hash' com PBKDF2-HMAC-SHA256. Nunca guarda a senha pura."""
    if salt is None:
        salt = secrets.token_hex(16)
    derivada = hashlib.pbkdf2_hmac("sha256", senha.encode("utf-8"), bytes.fromhex(salt), 120_000)
    return f"{salt}${derivada.hex()}"


def _conferir_senha(senha, armazenado):
    try:
        salt, _resto = armazenado.split("$", 1)
    except ValueError:
        return False
    return secrets.compare_digest(_hash_senha(senha, salt), armazenado)


def criar_usuario(login, senha, papel="operador", nome=None, email=None):
    """Cria um usuário. Lança LoginDuplicado se o login já existir."""
    conexao = conectar()
    try:
        conexao.execute(
            """INSERT INTO usuarios (uuid, login, senha_hash, papel, nome, email, ativo, criado_em)
               VALUES (?, ?, ?, ?, ?, ?, 1, ?)""",
            (str(uuid.uuid4()), login, _hash_senha(senha), papel, nome, email, agora()),
        )
        conexao.commit()
    except sqlite3.IntegrityError:
        raise LoginDuplicado(login)
    finally:
        conexao.close()


def atualizar_usuario(usuario_id, nome, email, papel, ativo):
    """Altera dados de um usuário (não mexe na senha)."""
    conexao = conectar()
    conexao.execute(
        "UPDATE usuarios SET nome = ?, email = ?, papel = ?, ativo = ? WHERE id = ?",
        (nome, email, papel, 1 if ativo else 0, usuario_id),
    )
    conexao.commit()
    conexao.close()


def alterar_senha_usuario(usuario_id, nova_senha):
    conexao = conectar()
    conexao.execute(
        "UPDATE usuarios SET senha_hash = ? WHERE id = ?",
        (_hash_senha(nova_senha), usuario_id),
    )
    conexao.commit()
    conexao.close()


def autenticar(login, senha):
    """Devolve os dados do usuário (sem o hash) se a senha bater, senão None."""
    conexao = conectar()
    linha = conexao.execute(
        "SELECT * FROM usuarios WHERE login = ? AND ativo = 1", (login,)
    ).fetchone()
    conexao.close()
    if linha and _conferir_senha(senha, linha["senha_hash"]):
        dados = dict(linha)
        dados.pop("senha_hash", None)  # nunca devolve o hash para a interface
        return dados
    return None


def listar_usuarios():
    conexao = conectar()
    linhas = conexao.execute(
        "SELECT id, uuid, login, nome, email, papel, ativo, criado_em FROM usuarios ORDER BY login"
    ).fetchall()
    conexao.close()
    return [dict(linha) for linha in linhas]


def alterar_senha(login, nova_senha):
    conexao = conectar()
    conexao.execute(
        "UPDATE usuarios SET senha_hash = ? WHERE login = ?",
        (_hash_senha(nova_senha), login),
    )
    conexao.commit()
    conexao.close()


def _garantir_master():
    """Na primeira vez, cria um usuário master padrão (master/master)."""
    conexao = conectar()
    total = conexao.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0]
    conexao.close()
    if total == 0:
        criar_usuario("master", "master", "master")


# ---------- Configuração da empresa / fiscal (Fase 3) — só o master edita ----------
CAMPOS_CONFIG_FISCAL = [
    # Empresa
    "razao_social", "nome_fantasia", "cnpj", "ie", "im", "crt",
    # Endereço
    "cep", "logradouro", "numero", "complemento", "bairro",
    "municipio", "cod_municipio", "uf",
    # Contato
    "telefone", "email",
    # Fiscal / NFC-e
    "ambiente", "serie", "proximo_numero",
    "certificado_caminho", "certificado_senha", "csc", "csc_id",
]

_PADROES_CONFIG = {"ambiente": "homologacao", "crt": "1", "serie": "1", "proximo_numero": "1"}


def ler_config_fiscal():
    """Retorna a config fiscal (dict). Se não houver, devolve os padrões."""
    conexao = conectar()
    linha = conexao.execute("SELECT * FROM config_fiscal WHERE id = 1").fetchone()
    conexao.close()
    if linha:
        return dict(linha)
    return {campo: _PADROES_CONFIG.get(campo, "") for campo in CAMPOS_CONFIG_FISCAL}


def salvar_config_fiscal(dados):
    """Grava a config fiscal (uma linha só). Só deve ser chamada por um master."""
    valores = {campo: dados.get(campo, "") for campo in CAMPOS_CONFIG_FISCAL}
    for campo, padrao in _PADROES_CONFIG.items():
        if not valores.get(campo):
            valores[campo] = padrao
    colunas = ", ".join(CAMPOS_CONFIG_FISCAL)
    marcadores = ", ".join("?" for _ in CAMPOS_CONFIG_FISCAL)
    conexao = conectar()
    conexao.execute(
        f"""INSERT INTO config_fiscal (id, {colunas}, atualizado_em)
            VALUES (1, {marcadores}, ?)
            ON CONFLICT(id) DO UPDATE SET
            {", ".join(f"{c}=excluded.{c}" for c in CAMPOS_CONFIG_FISCAL)},
            atualizado_em=excluded.atualizado_em""",
        [valores[c] for c in CAMPOS_CONFIG_FISCAL] + [agora()],
    )
    conexao.commit()
    conexao.close()

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
from contextlib import contextmanager
from datetime import date, datetime, timedelta

# Onde guardar o banco:
# - empacotado (executável): numa pasta fixa no perfil do usuário
# - rodando o código: em dados/ na raiz do projeto (facilita o desenvolvimento)
if getattr(sys, "frozen", False):
    PASTA_DADOS = os.path.join(os.path.expanduser("~"), ".pdv_proprio")
else:
    PASTA_DADOS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dados")

CAMINHO_BANCO = os.path.join(PASTA_DADOS, "pdv.db")

# Tabelas-base. Valores em dinheiro são CENTAVOS (INTEGER), nunca float.
# Colunas/tabelas posteriores (Fase 3) entram em _migrar, sem recriar o banco.
SCHEMA = """
CREATE TABLE IF NOT EXISTS produtos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uuid TEXT NOT NULL UNIQUE,
    codigo TEXT UNIQUE,
    descricao TEXT NOT NULL,
    preco_centavos INTEGER NOT NULL DEFAULT 0,
    ativo INTEGER NOT NULL DEFAULT 1,
    sincronizado INTEGER NOT NULL DEFAULT 0,
    criado_em TEXT NOT NULL,
    atualizado_em TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessoes_caixa (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uuid TEXT NOT NULL UNIQUE,
    operador TEXT,
    abertura_centavos INTEGER NOT NULL DEFAULT 0,
    aberto_em TEXT NOT NULL,
    fechado_em TEXT,
    fechamento_centavos INTEGER
);
CREATE TABLE IF NOT EXISTS movimentos_caixa (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uuid TEXT NOT NULL UNIQUE,
    sessao_id INTEGER NOT NULL REFERENCES sessoes_caixa (id),
    tipo TEXT NOT NULL,
    valor_centavos INTEGER NOT NULL,
    motivo TEXT,
    criado_em TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS vendas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uuid TEXT NOT NULL UNIQUE,
    sessao_id INTEGER REFERENCES sessoes_caixa (id),
    total_centavos INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'concluida',
    sincronizado INTEGER NOT NULL DEFAULT 0,
    criado_em TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS itens_venda (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    venda_id INTEGER NOT NULL REFERENCES vendas (id),
    produto_id INTEGER NOT NULL REFERENCES produtos (id),
    quantidade REAL NOT NULL DEFAULT 1,
    preco_unit_centavos INTEGER NOT NULL,
    subtotal_centavos INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS pagamentos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    venda_id INTEGER NOT NULL REFERENCES vendas (id),
    forma TEXT NOT NULL,
    valor_centavos INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS usuarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uuid TEXT NOT NULL UNIQUE,
    login TEXT NOT NULL UNIQUE,
    senha_hash TEXT NOT NULL,
    papel TEXT NOT NULL DEFAULT 'operador',
    ativo INTEGER NOT NULL DEFAULT 1,
    criado_em TEXT NOT NULL
);
-- Configuração fiscal (uma linha só, id = 1) — dados sensíveis
CREATE TABLE IF NOT EXISTS config_fiscal (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    razao_social TEXT, cnpj TEXT, ie TEXT, uf TEXT,
    ambiente TEXT DEFAULT 'homologacao',
    certificado_caminho TEXT, certificado_senha TEXT,
    csc TEXT, csc_id TEXT,
    atualizado_em TEXT
);
"""

# Índices das consultas frequentes (relatório, caixa, histórico, sincronização).
INDICES = """
CREATE INDEX IF NOT EXISTS idx_vendas_criado ON vendas (criado_em);
CREATE INDEX IF NOT EXISTS idx_vendas_sessao ON vendas (sessao_id);
CREATE INDEX IF NOT EXISTS idx_vendas_pendentes ON vendas (id) WHERE sincronizado = 0;
CREATE INDEX IF NOT EXISTS idx_produtos_pendentes ON produtos (id) WHERE sincronizado = 0;
CREATE INDEX IF NOT EXISTS idx_itens_venda ON itens_venda (venda_id);
CREATE INDEX IF NOT EXISTS idx_pagamentos_venda ON pagamentos (venda_id);
CREATE INDEX IF NOT EXISTS idx_movimentos_sessao ON movimentos_caixa (sessao_id);
"""

SENHA_PADRAO_MASTER = "master"


class CodigoDuplicado(Exception):
    """Lançada quando se tenta cadastrar um código de barras já usado."""


class CaixaJaAberto(Exception):
    """Lançada ao tentar abrir um caixa com outro já aberto."""


class LoginDuplicado(Exception):
    """Lançada ao criar um usuário com login já existente."""


class UltimoMaster(Exception):
    """Lançada quando uma alteração deixaria o sistema sem nenhum master ativo."""


# ---------- Infra ----------
def conectar():
    conexao = sqlite3.connect(CAMINHO_BANCO)
    conexao.row_factory = sqlite3.Row  # acessar colunas pelo nome
    return conexao


@contextmanager
def _conexao():
    """Conexão de uso único: confirma no fim, desfaz tudo (rollback) se der erro."""
    conexao = conectar()
    try:
        with conexao:
            yield conexao
    finally:
        conexao.close()


def _todos(sql, params=()):
    with _conexao() as conexao:
        return [dict(linha) for linha in conexao.execute(sql, params)]


def _um(sql, params=()):
    with _conexao() as conexao:
        linha = conexao.execute(sql, params).fetchone()
    return dict(linha) if linha else None


def _executar(sql, params=()):
    with _conexao() as conexao:
        return conexao.execute(sql, params).lastrowid


def agora():
    return datetime.now().isoformat(timespec="seconds")


def _novo_uuid():
    return str(uuid.uuid4())


def inicializar():
    """Cria a pasta de dados e o banco (se preciso), migra e protege os arquivos."""
    os.makedirs(PASTA_DADOS, exist_ok=True)
    with _conexao() as conexao:
        conexao.execute("PRAGMA journal_mode = WAL")  # gravações mais rápidas; persiste no arquivo
        conexao.executescript(SCHEMA)
    _migrar()
    _garantir_master()
    # O banco guarda hashes de senha e a config fiscal: só o dono do sistema lê.
    for caminho, modo in ((PASTA_DADOS, 0o700), (CAMINHO_BANCO, 0o600)):
        try:
            os.chmod(caminho, modo)
        except OSError:
            pass


def _adicionar_colunas(conexao, tabela, colunas):
    """Adiciona as colunas que faltam. Devolve o conjunto das que foram criadas agora."""
    existentes = {linha[1] for linha in conexao.execute(f"PRAGMA table_info({tabela})")}
    novas = {c for c in colunas if c not in existentes}
    for coluna in novas:
        conexao.execute(f"ALTER TABLE {tabela} ADD COLUMN {coluna} {colunas[coluna]}")
    return novas


def _migrar():
    """Migrações leves: adiciona colunas e índices novos sem apagar dados."""
    with _conexao() as conexao:
        # Marca de sincronização (Fase 2)
        for tabela in ("produtos", "vendas"):
            _adicionar_colunas(conexao, tabela, {"sincronizado": "INTEGER NOT NULL DEFAULT 0"})
        # Campos do produto adicionados na Fase 3 (fiscais + estoque/custo/categoria)
        _adicionar_colunas(conexao, "produtos", {
            "codigo_interno": "TEXT", "categoria": "TEXT",
            "custo_centavos": "INTEGER DEFAULT 0", "estoque": "REAL DEFAULT 0",
            "controla_estoque": "INTEGER DEFAULT 0",
            "unidade": "TEXT DEFAULT 'UN'", "tipo_item": "TEXT DEFAULT '00'",
            "ncm": "TEXT", "cest": "TEXT", "cfop": "TEXT",
            "origem": "TEXT DEFAULT '0'", "cst": "TEXT",
            "aliquota_icms": "REAL DEFAULT 0", "aliquota_aprox": "REAL DEFAULT 0",
        })
        # Cadastro detalhado de usuários + troca de senha obrigatória
        novas = _adicionar_colunas(conexao, "usuarios", {
            "nome": "TEXT", "email": "TEXT", "trocar_senha": "INTEGER NOT NULL DEFAULT 0",
        })
        if "trocar_senha" in novas:
            # Bancos antigos: quem ainda usa a senha padrão do master é obrigado a trocá-la.
            for linha in conexao.execute("SELECT id, senha_hash FROM usuarios WHERE login = 'master'").fetchall():
                if _conferir_senha(SENHA_PADRAO_MASTER, linha["senha_hash"]):
                    conexao.execute("UPDATE usuarios SET trocar_senha = 1 WHERE id = ?", (linha["id"],))
        # Empresa / config fiscal
        _adicionar_colunas(conexao, "config_fiscal", dict.fromkeys((
            "nome_fantasia", "im", "crt", "cep", "logradouro", "numero",
            "complemento", "bairro", "municipio", "cod_municipio",
            "telefone", "email", "serie", "proximo_numero",
        ), "TEXT"))
        # Desconto na venda (total_centavos já vem com o desconto aplicado)
        _adicionar_colunas(conexao, "vendas", {"desconto_centavos": "INTEGER NOT NULL DEFAULT 0"})
        # Preferências locais da estação (ex.: último usuário lembrado no login)
        conexao.execute("CREATE TABLE IF NOT EXISTS preferencias (chave TEXT PRIMARY KEY, valor TEXT)")
        conexao.executescript(INDICES)


# ---------- Preferências locais ----------
def ler_preferencia(chave, padrao=None):
    linha = _um("SELECT valor FROM preferencias WHERE chave = ?", (chave,))
    return linha["valor"] if linha else padrao


def salvar_preferencia(chave, valor):
    """Grava (ou apaga, com valor None) uma preferência local."""
    if valor is None:
        _executar("DELETE FROM preferencias WHERE chave = ?", (chave,))
    else:
        _executar(
            "INSERT INTO preferencias (chave, valor) VALUES (?, ?) "
            "ON CONFLICT(chave) DO UPDATE SET valor = excluded.valor",
            (chave, valor),
        )


# ---------- Conversão de dinheiro ----------
def para_centavos(valor_reais):
    """Converte reais (float ou texto '5,50') para centavos inteiros."""
    if isinstance(valor_reais, str):
        valor_reais = valor_reais.replace(",", ".")
    return round(float(valor_reais) * 100)


def formatar_reais(centavos):
    """Converte centavos (inteiro) para texto '5,50'."""
    return f"{centavos / 100:.2f}".replace(".", ",")


def subtotal_centavos(item):
    """quantidade × preço unitário de um item de venda, em centavos."""
    return round(item["quantidade"] * item["preco_unit_centavos"])


# ---------- Produtos ----------
# Campos preenchidos pelo cadastro/edição (fora uuid, ativo, datas) e seus padrões.
_PADROES_PRODUTO = {
    "codigo": None, "codigo_interno": None, "descricao": None, "categoria": None,
    "unidade": "UN", "tipo_item": "00", "preco_centavos": 0, "custo_centavos": 0,
    "estoque": 0, "controla_estoque": 0, "ncm": None, "cest": None, "cfop": None,
    "origem": "0", "cst": None, "aliquota_icms": 0, "aliquota_aprox": 0,
}
COLUNAS_PRODUTO = list(_PADROES_PRODUTO)


def _valores_produto(dados):
    return [dados.get(c, padrao) for c, padrao in _PADROES_PRODUTO.items()]


def listar_produtos():
    """Retorna os produtos ativos, em ordem alfabética."""
    return _todos("SELECT * FROM produtos WHERE ativo = 1 ORDER BY descricao COLLATE NOCASE")


def listar_categorias():
    """Categorias usadas pelos produtos ativos (para as abas da tela de Venda)."""
    return [
        linha["categoria"] for linha in _todos(
            """SELECT DISTINCT categoria FROM produtos
               WHERE ativo = 1 AND categoria IS NOT NULL AND TRIM(categoria) <> ''
               ORDER BY categoria COLLATE NOCASE"""
        )
    ]


def cadastrar_produto(dados):
    """Insere um produto. `dados` é um dict (ver COLUNAS_PRODUTO).

    Lança CodigoDuplicado se o código de barras já existir.
    """
    momento = agora()
    colunas = ", ".join(COLUNAS_PRODUTO)
    marcadores = ", ".join("?" * len(COLUNAS_PRODUTO))
    try:
        return _executar(
            f"""INSERT INTO produtos (uuid, ativo, {colunas}, criado_em, atualizado_em)
                VALUES (?, 1, {marcadores}, ?, ?)""",
            [_novo_uuid(), *_valores_produto(dados), momento, momento],
        )
    except sqlite3.IntegrityError:
        raise CodigoDuplicado(dados.get("codigo"))


def atualizar_produto(produto_id, dados):
    """Altera um produto existente. `dados` é um dict (ver COLUNAS_PRODUTO).

    Lança CodigoDuplicado se o código colidir.
    """
    atribuicoes = ", ".join(f"{c} = ?" for c in COLUNAS_PRODUTO)
    try:
        _executar(
            f"UPDATE produtos SET {atribuicoes}, sincronizado = 0, atualizado_em = ? WHERE id = ?",
            [*_valores_produto(dados), agora(), produto_id],
        )
    except sqlite3.IntegrityError:
        raise CodigoDuplicado(dados.get("codigo"))


def inativar_produto(produto_id):
    """Exclusão lógica: marca ativo = 0 (não apaga o histórico de vendas)."""
    _executar(
        "UPDATE produtos SET ativo = 0, sincronizado = 0, atualizado_em = ? WHERE id = ?",
        (agora(), produto_id),
    )


def obter_produto(produto_id):
    """Retorna um produto por id (ativo ou inativo), ou None."""
    return _um("SELECT * FROM produtos WHERE id = ?", (produto_id,))


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
    if status in ("ativos", "inativos"):
        clausulas.append("ativo = ?")
        params.append(1 if status == "ativos" else 0)

    texto = (filtros.get("texto") or "").strip()
    if texto:
        clausulas.append("(descricao LIKE ? OR codigo LIKE ? OR codigo_interno LIKE ?)")
        params += [f"%{texto}%"] * 3

    if filtros.get("controla") in (0, 1):
        clausulas.append("controla_estoque = ?")
        params.append(filtros["controla"])

    for campo in ("ncm", "cfop", "cst", "origem", "categoria"):
        valor = (filtros.get(campo) or "").strip()
        if valor:
            clausulas.append(f"{campo} LIKE ?")
            params.append(f"%{valor}%")

    onde = ("WHERE " + " AND ".join(clausulas)) if clausulas else ""
    return _todos(f"SELECT * FROM produtos {onde} ORDER BY descricao COLLATE NOCASE", params)


def buscar_produto_por_codigo(codigo):
    """Retorna o produto ativo com esse código, ou None."""
    return _um("SELECT * FROM produtos WHERE codigo = ? AND ativo = 1", (codigo,))


# ---------- Vendas ----------
def registrar_venda(itens, pagamentos, sessao_id=None, desconto_centavos=0):
    """Grava uma venda inteira de forma ATÔMICA.

    itens: lista de {produto_id, quantidade, preco_unit_centavos}
    pagamentos: lista de {forma, valor_centavos} — somam o total já com desconto
    desconto_centavos: abatido da soma dos itens (nunca maior que ela)

    Ou grava tudo (venda + itens + pagamentos), ou nada (rollback).
    Devolve (venda_id, total_centavos).
    """
    subtotais = [subtotal_centavos(i) for i in itens]
    desconto = max(0, min(desconto_centavos, sum(subtotais)))
    total = sum(subtotais) - desconto
    with _conexao() as conexao:
        venda_id = conexao.execute(
            """INSERT INTO vendas (uuid, sessao_id, total_centavos, desconto_centavos, status, criado_em)
               VALUES (?, ?, ?, ?, 'concluida', ?)""",
            (_novo_uuid(), sessao_id, total, desconto, agora()),
        ).lastrowid
        conexao.executemany(
            """INSERT INTO itens_venda
               (venda_id, produto_id, quantidade, preco_unit_centavos, subtotal_centavos)
               VALUES (?, ?, ?, ?, ?)""",
            [
                (venda_id, i["produto_id"], i["quantidade"], i["preco_unit_centavos"], sub)
                for i, sub in zip(itens, subtotais)
            ],
        )
        conexao.executemany(
            "INSERT INTO pagamentos (venda_id, forma, valor_centavos) VALUES (?, ?, ?)",
            [(venda_id, p["forma"], p["valor_centavos"]) for p in pagamentos],
        )
    return venda_id, total


def _intervalo_dias(inicio, fim):
    """[inicio, fim+1) em ISO, para usar o índice de criado_em (sem substr)."""
    return inicio, (date.fromisoformat(fim) + timedelta(days=1)).isoformat()


def listar_vendas(inicio=None, fim=None, forma=None, limite=500):
    """Vendas concluídas, mais recentes primeiro, com resumo de itens e formas.

    inicio/fim: datas ISO (AAAA-MM-DD), inclusivas. forma: só vendas com essa forma.
    """
    clausulas, params = ["v.status = 'concluida'"], []
    if inicio and fim:
        clausulas.append("v.criado_em >= ? AND v.criado_em < ?")
        params += _intervalo_dias(inicio, fim)
    if forma:
        clausulas.append("EXISTS (SELECT 1 FROM pagamentos WHERE venda_id = v.id AND forma = ?)")
        params.append(forma)
    return _todos(
        f"""SELECT v.id, v.total_centavos, v.desconto_centavos, v.criado_em,
                   (SELECT COUNT(*) FROM itens_venda WHERE venda_id = v.id) AS qtd_itens,
                   (SELECT GROUP_CONCAT(forma, ', ') FROM pagamentos WHERE venda_id = v.id) AS formas
            FROM vendas v
            WHERE {" AND ".join(clausulas)}
            ORDER BY v.id DESC
            LIMIT ?""",
        (*params, limite),
    )


def proximo_numero_venda():
    """Número que a próxima venda deve receber (exibido no topo da tela de Venda)."""
    return _um("SELECT COALESCE(MAX(id), 0) + 1 AS n FROM vendas")["n"]


# ---------- Caixa ----------
def sessao_aberta():
    """Retorna a sessão de caixa aberta (sem fechamento), ou None."""
    return _um("SELECT * FROM sessoes_caixa WHERE fechado_em IS NULL ORDER BY id DESC LIMIT 1")


def abrir_caixa(operador, abertura_centavos=0):
    """Abre uma sessão de caixa. Lança CaixaJaAberto se já houver uma aberta."""
    with _conexao() as conexao:
        if conexao.execute("SELECT 1 FROM sessoes_caixa WHERE fechado_em IS NULL").fetchone():
            raise CaixaJaAberto()
        return conexao.execute(
            "INSERT INTO sessoes_caixa (uuid, operador, abertura_centavos, aberto_em) VALUES (?, ?, ?, ?)",
            (_novo_uuid(), operador, abertura_centavos, agora()),
        ).lastrowid


def registrar_movimento_caixa(sessao_id, tipo, valor_centavos, motivo=None):
    """tipo: 'sangria' (retira dinheiro) ou 'suprimento' (coloca dinheiro)."""
    _executar(
        """INSERT INTO movimentos_caixa (uuid, sessao_id, tipo, valor_centavos, motivo, criado_em)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (_novo_uuid(), sessao_id, tipo, valor_centavos, motivo, agora()),
    )


def resumo_caixa(sessao_id):
    """Resumo financeiro de uma sessão de caixa (tudo em centavos)."""
    resumo = _um(
        """SELECT s.abertura_centavos AS abertura,
                  (SELECT COALESCE(SUM(valor_centavos), 0) FROM movimentos_caixa
                    WHERE sessao_id = s.id AND tipo = 'suprimento') AS suprimentos,
                  (SELECT COALESCE(SUM(valor_centavos), 0) FROM movimentos_caixa
                    WHERE sessao_id = s.id AND tipo = 'sangria') AS sangrias,
                  (SELECT COALESCE(SUM(p.valor_centavos), 0)
                     FROM pagamentos p JOIN vendas v ON v.id = p.venda_id
                    WHERE v.sessao_id = s.id AND v.status = 'concluida'
                      AND p.forma = 'Dinheiro') AS vendas_dinheiro,
                  (SELECT COALESCE(SUM(total_centavos), 0) FROM vendas
                    WHERE sessao_id = s.id AND status = 'concluida') AS vendas_total,
                  (SELECT COUNT(*) FROM vendas
                    WHERE sessao_id = s.id AND status = 'concluida') AS qtd_vendas,
                  (SELECT COUNT(*) FROM movimentos_caixa
                    WHERE sessao_id = s.id AND tipo = 'suprimento') AS qtd_suprimentos,
                  (SELECT COUNT(*) FROM movimentos_caixa
                    WHERE sessao_id = s.id AND tipo = 'sangria') AS qtd_sangrias
           FROM sessoes_caixa s WHERE s.id = ?""",
        (sessao_id,),
    )
    # O que deve haver na gaveta: só dinheiro entra/sai dela.
    resumo["esperado_gaveta"] = (
        resumo["abertura"] + resumo["suprimentos"] + resumo["vendas_dinheiro"] - resumo["sangrias"]
    )
    return resumo


def movimentos_sessao(sessao_id, limite=100):
    """Linha do tempo do turno: abertura, suprimentos, sangrias e vendas (mais recentes primeiro).

    Cada linha: {tipo, detalhe, criado_em, valor_centavos}. tipo: abertura | suprimento |
    sangria | venda (detalhe = formas de pagamento; o id vai em `venda_id`).
    """
    return _todos(
        """SELECT * FROM (
               SELECT 'abertura' AS tipo, operador AS detalhe, aberto_em AS criado_em,
                      abertura_centavos AS valor_centavos, NULL AS venda_id
                 FROM sessoes_caixa WHERE id = :s
               UNION ALL
               SELECT tipo, motivo, criado_em, valor_centavos, NULL
                 FROM movimentos_caixa WHERE sessao_id = :s
               UNION ALL
               SELECT 'venda', (SELECT GROUP_CONCAT(forma, ', ') FROM pagamentos WHERE venda_id = v.id),
                      criado_em, total_centavos, id
                 FROM vendas v WHERE sessao_id = :s AND status = 'concluida'
           ) ORDER BY criado_em DESC LIMIT :limite""",
        {"s": sessao_id, "limite": limite},
    )


def fechar_caixa(sessao_id, fechamento_centavos):
    """Fecha a sessão gravando o valor contado na gaveta."""
    _executar(
        "UPDATE sessoes_caixa SET fechado_em = ?, fechamento_centavos = ? WHERE id = ?",
        (agora(), fechamento_centavos, sessao_id),
    )


# ---------- Relatório ----------
def relatorio_dia(data=None):
    """Resumo das vendas de um dia (padrão: hoje). Valores em centavos.

    por_forma: [(forma, valor, qtd_vendas)]; mais_vendidos: [{descricao, unidade, quantidade, valor}].
    """
    data = data or date.today().isoformat()
    # Intervalo [dia, dia+1) em vez de substr(): assim o índice de criado_em é usado.
    intervalo = _intervalo_dias(data, data)
    ontem = (date.fromisoformat(data) - timedelta(days=1)).isoformat()
    concluidas = "v.status = 'concluida' AND v.criado_em >= ? AND v.criado_em < ?"
    with _conexao() as conexao:
        qtd, total = conexao.execute(
            f"SELECT COUNT(*), COALESCE(SUM(total_centavos), 0) FROM vendas v WHERE {concluidas}",
            intervalo,
        ).fetchone()
        total_ontem = conexao.execute(
            f"SELECT COALESCE(SUM(total_centavos), 0) FROM vendas v WHERE {concluidas}",
            _intervalo_dias(ontem, ontem),
        ).fetchone()[0]
        itens = conexao.execute(
            f"""SELECT COALESCE(SUM(iv.quantidade), 0) FROM itens_venda iv
                JOIN vendas v ON v.id = iv.venda_id WHERE {concluidas}""",
            intervalo,
        ).fetchone()[0]
        por_forma = conexao.execute(
            f"""SELECT p.forma, SUM(p.valor_centavos), COUNT(DISTINCT v.id)
                FROM pagamentos p JOIN vendas v ON v.id = p.venda_id
                WHERE {concluidas}
                GROUP BY p.forma ORDER BY SUM(p.valor_centavos) DESC""",
            intervalo,
        ).fetchall()
        mais_vendidos = conexao.execute(
            f"""SELECT pr.descricao, pr.unidade, SUM(iv.quantidade) AS quantidade,
                       SUM(iv.subtotal_centavos) AS valor
                FROM itens_venda iv
                JOIN vendas v ON v.id = iv.venda_id
                JOIN produtos pr ON pr.id = iv.produto_id
                WHERE {concluidas}
                GROUP BY iv.produto_id ORDER BY quantidade DESC, valor DESC LIMIT 5""",
            intervalo,
        ).fetchall()
    return {
        "data": data, "qtd": qtd, "total": total, "total_ontem": total_ontem, "itens": itens,
        "por_forma": [tuple(l) for l in por_forma],
        "mais_vendidos": [dict(l) for l in mais_vendidos],
    }


# ---------- Sincronização (Fase 2) ----------
def produtos_pendentes():
    """Produtos ainda não enviados ao servidor central."""
    return _todos("SELECT * FROM produtos WHERE sincronizado = 0")


def vendas_pendentes():
    """Vendas pendentes, já com seus itens e pagamentos prontos para enviar."""
    pendentes = "SELECT id FROM vendas WHERE sincronizado = 0 AND status = 'concluida'"
    with _conexao() as conexao:
        vendas = {
            linha["id"]: dict(linha, itens=[], pagamentos=[])
            for linha in conexao.execute(f"SELECT * FROM vendas WHERE id IN ({pendentes})")
        }
        if not vendas:
            return []
        for linha in conexao.execute(
            f"""SELECT iv.venda_id, iv.quantidade, iv.preco_unit_centavos, iv.subtotal_centavos,
                       p.uuid AS produto_uuid
                FROM itens_venda iv JOIN produtos p ON p.id = iv.produto_id
                WHERE iv.venda_id IN ({pendentes})"""
        ):
            item = dict(linha)
            vendas[item.pop("venda_id")]["itens"].append(item)
        for linha in conexao.execute(
            f"SELECT venda_id, forma, valor_centavos FROM pagamentos WHERE venda_id IN ({pendentes})"
        ):
            pagamento = dict(linha)
            vendas[pagamento.pop("venda_id")]["pagamentos"].append(pagamento)
    return list(vendas.values())


def marcar_produtos_sincronizados(produtos):
    """Marca como enviados. Só marca se o produto não mudou desde a leitura."""
    with _conexao() as conexao:
        conexao.executemany(
            "UPDATE produtos SET sincronizado = 1 WHERE uuid = ? AND atualizado_em = ?",
            [(p["uuid"], p["atualizado_em"]) for p in produtos],
        )


def marcar_vendas_sincronizadas(vendas):
    with _conexao() as conexao:
        conexao.executemany(
            "UPDATE vendas SET sincronizado = 1 WHERE uuid = ?", [(v["uuid"],) for v in vendas]
        )


def contar_pendentes():
    return _um(
        """SELECT (SELECT COUNT(*) FROM produtos WHERE sincronizado = 0) AS produtos,
                  (SELECT COUNT(*) FROM vendas WHERE sincronizado = 0 AND status = 'concluida') AS vendas"""
    )


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


def criar_usuario(login, senha, papel="operador", nome=None, email=None, trocar_senha=False):
    """Cria um usuário. Lança LoginDuplicado se o login já existir."""
    try:
        _executar(
            """INSERT INTO usuarios
               (uuid, login, senha_hash, papel, nome, email, ativo, trocar_senha, criado_em)
               VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)""",
            (_novo_uuid(), login, _hash_senha(senha), papel, nome, email, int(trocar_senha), agora()),
        )
    except sqlite3.IntegrityError:
        raise LoginDuplicado(login)


def atualizar_usuario(usuario_id, nome, email, papel, ativo):
    """Altera dados de um usuário (não mexe na senha).

    Lança UltimoMaster se a alteração deixaria o sistema sem master ativo.
    """
    with _conexao() as conexao:
        conexao.execute(
            "UPDATE usuarios SET nome = ?, email = ?, papel = ?, ativo = ? WHERE id = ?",
            (nome, email, papel, 1 if ativo else 0, usuario_id),
        )
        restantes = conexao.execute(
            "SELECT COUNT(*) FROM usuarios WHERE papel = 'master' AND ativo = 1"
        ).fetchone()[0]
        if restantes == 0:
            raise UltimoMaster()  # sai do `with` com erro: rollback


def alterar_senha_usuario(usuario_id, nova_senha, exigir_troca=False):
    """Define a senha. Com exigir_troca, o usuário terá de trocá-la no próximo login."""
    _executar(
        "UPDATE usuarios SET senha_hash = ?, trocar_senha = ? WHERE id = ?",
        (_hash_senha(nova_senha), int(exigir_troca), usuario_id),
    )


def autenticar(login, senha):
    """Devolve os dados do usuário (sem o hash) se a senha bater, senão None."""
    usuario = _um("SELECT * FROM usuarios WHERE login = ? AND ativo = 1", (login,))
    if usuario and _conferir_senha(senha, usuario.pop("senha_hash")):
        return usuario  # o hash nunca vai para a interface
    return None


def listar_usuarios():
    return _todos(
        "SELECT id, uuid, login, nome, email, papel, ativo, criado_em FROM usuarios ORDER BY login"
    )


def _garantir_master():
    """Na primeira vez, cria o master padrão — que é obrigado a trocar a senha no 1º login."""
    if not _um("SELECT 1 AS existe FROM usuarios LIMIT 1"):
        criar_usuario("master", SENHA_PADRAO_MASTER, "master", trocar_senha=True)


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
    return _um("SELECT * FROM config_fiscal WHERE id = 1") or {
        campo: _PADROES_CONFIG.get(campo, "") for campo in CAMPOS_CONFIG_FISCAL
    }


def salvar_config_fiscal(dados):
    """Grava a config fiscal (uma linha só). Só deve ser chamada por um master."""
    valores = [dados.get(c) or _PADROES_CONFIG.get(c, "") for c in CAMPOS_CONFIG_FISCAL]
    colunas = ", ".join(CAMPOS_CONFIG_FISCAL)
    marcadores = ", ".join("?" * len(CAMPOS_CONFIG_FISCAL))
    atualizacoes = ", ".join(f"{c} = excluded.{c}" for c in CAMPOS_CONFIG_FISCAL)
    _executar(
        f"""INSERT INTO config_fiscal (id, {colunas}, atualizado_em) VALUES (1, {marcadores}, ?)
            ON CONFLICT(id) DO UPDATE SET {atualizacoes}, atualizado_em = excluded.atualizado_em""",
        [*valores, agora()],
    )

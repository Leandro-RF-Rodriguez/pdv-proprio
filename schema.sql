CREATE TABLE IF NOT EXISTS produtos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uuid TEXT NOT NULL UNIQUE,
    codigo TEXT,
    descricao TEXT NOT NULL,
    preco REAL NOT NULL DEFAULT 0,
    ativo INTEGER NOT NULL DEFAULT 1,
    criado_em TEXT NOT NULL,
    atualizado_em TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessoes_caixa (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uuid TEXT NOT NULL UNIQUE,
    operador TEXT,
    valor_abertura REAL NOT NULL DEFAULT 0,
    aberto_em TEXT NOT NULL,
    fechado_em TEXT,
    valor_fechamento REAL
);

CREATE TABLE IF NOT EXISTS movimentos_caixa (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uuid TEXT NOT NULL UNIQUE,
    sessao_id INTEGER NOT NULL,
    tipo TEXT NOT NULL,
    valor REAL NOT NULL,
    motivo TEXT,
    criado_em TEXT NOT NULL,
    FOREIGN KEY (sessao_id) REFERENCES sessoes_caixa (id)
);

CREATE TABLE IF NOT EXISTS vendas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uuid TEXT NOT NULL UNIQUE,
    sessao_id INTEGER,
    total REAL NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'concluida',
    criado_em TEXT NOT NULL,
    FOREIGN KEY (sessao_id) REFERENCES sessoes_caixa (id)
);

CREATE TABLE IF NOT EXISTS itens_venda (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    venda_id INTEGER NOT NULL,
    produto_id INTEGER NOT NULL,
    quantidade REAL NOT NULL DEFAULT 1,
    preco_unit REAL NOT NULL,
    subtotal REAL NOT NULL,
    FOREIGN KEY (venda_id) REFERENCES vendas (id),
    FOREIGN KEY (produto_id) REFERENCES produtos (id)
);

CREATE TABLE IF NOT EXISTS pagamentos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    venda_id INTEGER NOT NULL,
    forma TEXT NOT NULL,
    valor REAL NOT NULL,
    FOREIGN KEY (venda_id) REFERENCES vendas (id)
);

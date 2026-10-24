# PDV Próprio

Sistema de **ponto de venda (PDV) de desktop**, offline-first, construído do zero como projeto de estudo e portfólio.

Funciona 100% no computador, sem depender de internet para operar. A sincronização com um sistema Web é uma fase futura, já prevista no modelo de dados.

---

## ✨ Funcionalidades (Fase 1)

- **Produtos** — cadastro com código de barras único e preço.
- **Venda** — carrinho por código ou por nome, cálculo de total e registro do pagamento.
- **Caixa** — abertura com fundo de troco, sangria, suprimento e fechamento com conferência da gaveta.
- **Relatório do dia** — total vendido e quebra por forma de pagamento.

## 🛠️ Tecnologias

| Camada | Tecnologia |
| --- | --- |
| Interface | [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter) (desktop, leve e moderno) |
| Lógica / dados | Python 3 + SQLite |
| Empacotamento | PyInstaller (executável instalável) |

## 🏗️ Arquitetura

Três camadas, todas na mesma máquina:

```
Interface (janela)  →  Lógica (banco.py)  →  Banco local (SQLite)
   CustomTkinter         Python, sem servidor      fonte da verdade
```

A venda é gravada em uma **transação atômica**: ou grava a venda, seus itens e o pagamento juntos, ou nada (rollback).

### Decisões de projeto

- **Dinheiro em centavos (inteiro).** Todos os valores são guardados em centavos (`preco_centavos`, `total_centavos`), evitando erros de arredondamento do ponto flutuante.
- **`uuid` + carimbos de tempo** em cada registro — o gancho para a sincronização futura (Fase 2), sem custo hoje.
- **Consultas parametrizadas** (`?`) em todo o acesso ao banco — proteção contra SQL injection.

## 🚀 Como rodar (a partir do código)

```bash
python3 -m venv venv
source venv/bin/activate          # no Windows: venv\Scripts\activate
pip install -r requirements.txt
python3 pdv_app.py                # o banco é criado automaticamente na 1ª vez
```

## 📦 Gerar o executável

```bash
pyinstaller --onefile --windowed --name pdv-proprio \
  --add-data "schema.sql:." --collect-all customtkinter pdv_app.py
```

O executável fica em `dist/pdv-proprio`.

## 📁 Estrutura

```
pdv-proprio/
├── schema.sql        # definição das tabelas
├── banco.py          # camada de acesso ao banco (SQL isolado)
├── pdv_app.py        # aplicativo de desktop (interface)
├── criar_banco.py    # cria o banco manualmente (opcional)
└── requirements.txt  # dependências
```

## 🗺️ Roadmap

- [x] **Fase 1** — MVP local (produtos, vendas, caixa, relatório)
- [ ] **Fase 2** — sincronização com um sistema Web central
- [ ] **Fase 3** — fiscal (NFC-e / SEFAZ)

---

Projeto pessoal de estudo. A arquitetura é inspirada em padrões da indústria de PDV; todo o código é original.

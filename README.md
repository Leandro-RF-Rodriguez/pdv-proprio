# PDV Próprio

Sistema de ponto de venda **de desktop**, offline-first, construído como projeto de estudo.

- **Interface:** CustomTkinter (janela leve e moderna)
- **Banco:** SQLite local (`pdv.db`)
- **Empacotamento futuro:** PyInstaller (executável instalável)

## Como rodar

```bash
source venv/bin/activate
python3 criar_banco.py   # só na primeira vez, cria o pdv.db
python3 pdv_app.py       # abre a janela do PDV
```

## Estrutura

- `schema.sql` — definição das tabelas
- `criar_banco.py` — cria o banco a partir do schema
- `banco.py` — camada de acesso ao banco (SQL isolado da interface)
- `pdv_app.py` — aplicativo de desktop (interface)

## Fases

- **Fase 1 (atual):** MVP local — produtos, vendas, caixa, relatório do dia
- **Fase 2:** sincronização com um sistema Web central
- **Fase 3:** fiscal (NFC-e / SEFAZ)

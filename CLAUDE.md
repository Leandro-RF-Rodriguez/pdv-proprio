# PDV Próprio — guia do projeto (mapa do código)

PDV de desktop offline-first (CustomTkinter + SQLite), com sincronização a um
servidor central e cadastro fiscal (rumo à NFC-e). Este arquivo é o mapa: diz
onde está cada coisa, para não precisar ler o código todo. Aponta por **função**,
não por linha (linha muda; nome não).

## Como rodar e testar

```bash
source venv/bin/activate
python3 pdv_app.py          # abre o app (login master/master na 1ª vez); = python3 -m pdv
python3 -m servidor.central # servidor de sincronização (porta 5001)
pyinstaller pdv-proprio.spec # gera dist/pdv-proprio
```

- O banco é criado/migrado sozinho em `banco.inicializar()` (chamado no início).
- Bancos locais (`pdv.db`, `central.db`) e certificados ficam em `dados/` (ignorado pelo git). Empacotado, o banco vai para `~/.pdv_proprio`.
- Rode sempre a partir da raiz: os módulos do pacote usam import relativo (`from . import banco`).
- Não há framework de teste no repo; os testes são scripts avulsos rodados à parte.

## Convenções (importantes)

- **Dinheiro em centavos (INTEGER).** Nunca float. `banco.para_centavos` / `banco.formatar_reais` convertem. Colunas terminam em `_centavos`.
- **Camadas separadas:** `pdv/banco.py` concentra todo SQL; a interface (`pdv/interface.py`) nunca escreve SQL.
- **SQL parametrizado** (`?`) sempre — proteção contra injection.
- **`uuid` + `sincronizado` + timestamps** em registros que sincronizam (produtos, vendas).
- **Migração não-destrutiva:** colunas/tabelas novas entram em `banco._migrar` (ALTER/CREATE IF NOT EXISTS), nunca recriando o banco.
- **Senhas:** hash PBKDF2+salt (`banco._hash_senha`), nunca texto puro.

## Mapa dos arquivos

Estrutura: `pdv/` (pacote do app), `servidor/` (central), `scripts/`, `assets/`, `docs/`, `dados/` (local, fora do git). `pdv_app.py` na raiz é só o ponto de entrada.

### `pdv/banco.py` — camada de dados (SQLite). Fonte única do schema da Fase 3.
- **Infra:** `inicializar`, `_migrar` (cria/migra tudo), `conectar`, `agora`, caminho do banco (`CAMINHO_BANCO`: `dados/` no código-fonte, `~/.pdv_proprio` quando empacotado), `_caminho_recurso`.
- **Dinheiro:** `para_centavos`, `formatar_reais`.
- **Produtos:** `COLUNAS_PRODUTO` (lista de campos), `cadastrar_produto(dados)`, `atualizar_produto(id, dados)`, `inativar_produto`, `listar_produtos` (ativos), `buscar_produtos(filtros)` (pesquisa c/ status/texto/controla/ncm/cfop/cst/origem/categoria), `obter_produto(id)`, `buscar_produto_por_codigo`.
- **Vendas:** `registrar_venda(itens, pagamentos, sessao_id)` — transação atômica.
- **Caixa:** `sessao_aberta`, `abrir_caixa`, `registrar_movimento_caixa`, `resumo_caixa`, `fechar_caixa`.
- **Relatório:** `relatorio_dia`.
- **Histórico:** `listar_vendas`.
- **Sincronização (Fase 2):** `produtos_pendentes`, `vendas_pendentes`, `marcar_produto_sincronizado`, `marcar_venda_sincronizada`, `contar_pendentes`.
- **Usuários (Fase 3):** `criar_usuario`, `autenticar`, `atualizar_usuario`, `alterar_senha_usuario`, `listar_usuarios`, `_garantir_master` (semeia master/master), `_hash_senha`/`_conferir_senha`.
- **Config empresa/fiscal:** `CAMPOS_CONFIG_FISCAL` (lista), `ler_config_fiscal`, `salvar_config_fiscal` (linha única id=1).
- **Exceções:** `CodigoDuplicado`, `CaixaJaAberto`, `LoginDuplicado`.

### `pdv/interface.py` — interface (CustomTkinter). Classe `AppPDV`.
- **Tema:** dict `P` (paleta verde), `FONTE`. Helpers: `_fonte`, `_btn`, `_card`, `_entry`, `_option`, `_estilizar_tabelas`, `_titulo`.
- **Login e entrada:** classe `TelaLogin`, função `iniciar()` (login → app; relogin via `_sair`). `AppPDV.__init__(usuario)` guarda `self.usuario`/`self.eh_master`.
- **Barra lateral:** `_montar_barra_lateral` (telas master-only: Configuração e Usuários). `sincronizar_agora`.
- **Venda:** `mostrar_vendas` (catálogo em cartões + checkout), `_desenhar_catalogo`, `_adicionar_ao_carrinho`, `_alterar_qtd`, `remover_item`, `_redesenhar_carrinho`, `_selecionar_forma`, `finalizar_venda`, `adicionar_por_codigo`.
- **Produtos:** `mostrar_produtos` (PESQUISA: filtros + tabela + export), `_toggle_avancado`, `_coletar_filtros`, `_pesquisar_produtos`, `_novo_produto`, `_editar_produto`, `_exportar_produtos`; `mostrar_form_produto(id)` (formulário), `_ler_form_produto`, `_salvar_form`, `excluir_produto`, `_carregar_produto_no_form`.
- **Caixa:** `mostrar_caixa`, `_tela_abrir_caixa`, `abrir_caixa`, `_tela_caixa_aberto`, `_movimento`, `fechar_caixa`.
- **Histórico:** `mostrar_historico`.
- **Relatório:** `mostrar_relatorio`.
- **Configuração (master):** `mostrar_config` (Empresa/Endereço/Contato/Fiscal), `_escolher_certificado`, `_salvar_config`.
- **Usuários (master):** `mostrar_usuarios`, `_atualizar_usuarios`, `_carregar_usuario_sel`, `_criar_usuario`, `_salvar_usuario`, `_trocar_senha_usuario`, `_alternar_ativo`, `_limpar_user_form`.

### `pdv/sync.py` — cliente de sincronização
- `sincronizar(servidor)` envia pendentes ao central (urllib, sem dependência nova); em falha de rede, mantém pendente.

### `servidor/central.py` — servidor central (Flask)
- Endpoints `POST /sync/produtos`, `POST /sync/vendas` (idempotentes por uuid), `GET /status`. Banco próprio `dados/central.db`.

### `pdv/exportacao.py` — exportação de produtos
- `exportar_produtos_csv(caminho, produtos)` — CSV `;` + BOM; cabeçalho baseado no **Registro 0200 do SPED Fiscal** + colunas detalhadas. `CABECALHO` tem a ordem.

### `pdv/schema.sql`
- Só as tabelas-base. Tudo da Fase 3 (campos fiscais, usuarios, config_fiscal) é criado em `banco._migrar`.

### `pdv/nfce.py` — pré-emissão de NFC-e (Fase 4, passo 1)
- `CONFIG_OBRIGATORIA`, `PRODUTO_OBRIGATORIO`, `validar_config`, `validar_produto`, `pendencias_emissao(config, produtos)`. Usado por `AppPDV._emitir_nfce`.

### `scripts/criar_banco.py`
- Cria/migra o banco manualmente via `banco.inicializar()` (opcional; o app já faz sozinho).

## Fases
- **Fase 1:** produtos, venda, caixa, relatório, histórico. ✅
- **Fase 2:** sincronização cliente–servidor idempotente. ✅
- **Fase 3:** acesso (master/operador), cadastro fiscal, config empresa. Em andamento.
- **Fase 4 (próxima):** emissor de NFC-e (montar/assinar/transmitir à SEFAZ em homologação) — precisa de certificado e roda/valida na máquina do usuário.

# PDV Próprio — guia do projeto (mapa do código)

PDV de desktop offline-first (CustomTkinter + SQLite), com sincronização a um
servidor central e cadastro fiscal (rumo à NFC-e). Este arquivo é o mapa: diz
onde está cada coisa, para não precisar ler o código todo. Aponta por **função**,
não por linha (linha muda; nome não).

## Como rodar e testar

```bash
source venv/bin/activate
python3 pdv_app.py          # abre o app (master/master na 1ª vez, com troca obrigatória); = python3 -m pdv
python3 -m servidor.central # servidor de sincronização (porta 5001)
pyinstaller pdv-proprio.spec # gera dist/pdv-proprio
```

- O banco é criado/migrado sozinho em `banco.inicializar()` (chamado no início), que também aplica `chmod 700/600` em `dados/`/`pdv.db`.
- Bancos locais (`pdv.db`, `central.db`) e certificados ficam em `dados/` (ignorado pelo git). Empacotado, o banco vai para `~/.pdv_proprio`.
- Rode sempre a partir da raiz: os módulos do pacote usam import relativo (`from . import banco`).
- Não há framework de teste no repo; os testes são scripts avulsos rodados à parte.

## Convenções (importantes)

- **Dinheiro em centavos (INTEGER).** Nunca float. `banco.para_centavos` / `banco.formatar_reais` convertem. Colunas terminam em `_centavos`.
- **Camadas separadas:** `pdv/banco.py` concentra todo SQL; a interface (`pdv/interface.py`) nunca escreve SQL.
- **SQL parametrizado** (`?`) sempre — proteção contra injection.
- **`uuid` + `sincronizado` + timestamps** em registros que sincronizam (produtos, vendas).
- **Migração não-destrutiva:** colunas/tabelas novas entram em `banco._migrar` (ALTER/CREATE IF NOT EXISTS), nunca recriando o banco.
- **Senhas:** hash PBKDF2+salt (`banco._hash_senha`), nunca texto puro. Senha padrão ou definida pelo master → `trocar_senha = 1` (troca obrigatória no login). Entrada de senha sempre mascarada (`_Estilo._pedir_senha`).
- **Acesso ao banco:** use os helpers `banco._conexao` (commit/rollback automáticos), `_todos`, `_um`, `_executar` — não repita conectar/commit/close.
- **Segredos:** nada de token/senha/chave no código. Sync usa env `PDV_SYNC_TOKEN` / `PDV_SERVIDOR`.

## Mapa dos arquivos

Estrutura: `pdv/` (pacote do app), `servidor/` (central), `assets/`, `docs/`, `dados/` (local, fora do git). `pdv_app.py` na raiz é só o ponto de entrada.

### `pdv/banco.py` — camada de dados (SQLite). Fonte única do schema (`SCHEMA`, `INDICES`).
- **Infra:** `inicializar` (schema + WAL + permissões), `_migrar` (colunas novas via `_adicionar_colunas` + índices), `conectar`, `_conexao`/`_todos`/`_um`/`_executar`, `agora`, caminho do banco (`CAMINHO_BANCO`: `dados/` no código-fonte, `~/.pdv_proprio` quando empacotado).
- **Dinheiro:** `para_centavos`, `formatar_reais`, `subtotal_centavos(item)`.
- **Produtos:** `COLUNAS_PRODUTO` (lista de campos; inclui `foto_arquivo`, nome do arquivo em `<dados>/imagens`), `cadastrar_produto(dados)`, `atualizar_produto(id, dados)`, `inativar_produto`, `listar_produtos` (ativos), `buscar_produtos(filtros)` (pesquisa c/ status/texto/controla/ncm/cfop/cst/origem/categoria), `obter_produto(id)`, `buscar_produto_por_codigo`.
- **Categorias:** `listar_categorias` (abas da tela de Venda).
- **Vendas:** `registrar_venda(itens, pagamentos, sessao_id, desconto_centavos, troco_centavos)` — transação atômica; `total_centavos` já sai com o desconto (coluna `vendas.desconto_centavos`) e os pagamentos (1 ou vários = pagamento dividido) somam esse total (valor devido, não o recebido). O troco fica em `vendas.troco_centavos` (só informativo; vendas antigas = 0). `proximo_numero_venda`.
- **Caixa:** `sessao_aberta`, `abrir_caixa`, `registrar_movimento_caixa`, `resumo_caixa` (inclui contagens `qtd_*`), `movimentos_sessao` (linha do tempo do turno), `fechar_caixa`.
- **Relatório:** `relatorio_dia` (total, ontem, itens, `por_forma` = (forma, valor, qtd), `mais_vendidos`).
- **Histórico:** `listar_vendas(inicio, fim, forma)` (datas ISO inclusivas; `_intervalo_dias` usa o índice de `criado_em`), `detalhes_venda(id)` (venda + `itens` com descrição/código/unidade + `pagamentos`; None se não existe).
- **Preferências locais:** `ler_preferencia` / `salvar_preferencia` (tabela `preferencias`; ex.: `ultimo_login` do "Lembrar meu usuário"; por usuário: `usuario:<id>:fonte` = P/M/G, `usuario:<id>:touch` e `usuario:<id>:tela_cheia` = "1"/"0").
- **Sincronização (Fase 2):** `produtos_pendentes`, `vendas_pendentes` (3 consultas, sem N+1), `marcar_produtos_sincronizados` (só se `atualizado_em` não mudou), `marcar_vendas_sincronizadas`, `contar_pendentes`.
- **Usuários (Fase 3):** `criar_usuario`, `autenticar`, `atualizar_usuario` (bloqueia ficar sem master → `UltimoMaster`), `alterar_senha_usuario(id, senha, exigir_troca)`, `listar_usuarios`, `_garantir_master` (semeia master/master com troca obrigatória), `_hash_senha`/`_conferir_senha`.
- **Config empresa/fiscal:** `CAMPOS_CONFIG_FISCAL` (lista; inclui `logo_arquivo`, nome do arquivo em `<dados>/imagens`), `ler_config_fiscal`, `salvar_config_fiscal` (linha única id=1).
- **Exceções:** `CodigoDuplicado`, `CaixaJaAberto`, `LoginDuplicado`, `UltimoMaster`.

### `pdv/interface.py` — interface (CustomTkinter). Classe `AppPDV`.
Visual = protótipo do Figma Make "Aprimorar Estética do PDV" (pasta `figma/` tem o briefing que o originou).
- **Tema:** dict `P` (tokens do Figma), `ESCALAS_FONTE` (P/M/G), `ALTURA_TOUCH`, `TONS` (pílulas), `CORES_PRODUTO`, `_ESTILOS_BOTAO`, `FONTE`. Formatação: `_reais` (R$ 1.234,56), `_ler_reais` (texto digitado → centavos; "100" = cem reais, aceita "1.234,56"), `_qtd`, `_iniciais`, `_data_hora`, `_data_iso`, `_nome_loja` (nome fantasia das Configurações, mostrado no login e na barra lateral via `_atualizar_marca`), `_logo_loja` (arquivo da logo ou None). `AJUDA_FISCAL`: textos do "?" dos campos fiscais.
- **Mixin `_Estilo`** (login + app): `_fechar` (cancela `after` pendentes e limpa os caches de `icone`/`imagens.imagem`: imagens Tk morrem com a janela, e o login e o PDV são janelas raiz diferentes), `_selo_marca`/`_pintar_selo` (logo da loja numa placa branca, ou o carrinho se não houver logo), `_escala` (multiplicador da letra P/M/G; 1 no login), `_alvo(altura, touch=48)` (altura de botão/campo: sobe no modo touch — use em todo alvo de clique novo), `_fonte` (cache; já aplica `_escala`) / `_fonte_tk` (widgets tk puros, mais leves — usados nos cartões do catálogo), `_rotulo`, `_btn(tipo, icone_nome=)`, `_link`, `_card`, `_entry`, `_campo` (rótulo em cima; entrada em `.entrada`; `ajuda=` põe um "?" com `_dica`), `_select`/`_campo_select` (OptionMenu com moldura), `_pill`, `_dialogo` (modal genérico com campos + validação), `_pedir_senha`.
- **Helpers de tela (app):** `_limpar_area(tela)` (marca o menu), `_pagina(rolavel)`, `_cabecalho` (sobretítulo/título/descrição/ação), `_cartao_dados` (+ `.subtitulo`/`.direita`), `_tabela` (Treeview "PDV.Treeview" + `CTkScrollbar`), `_preencher` (linhas `(valores, tag)`), `_rodape_tabela`, `_secao`, `_grade_campos`, `_barra_acoes` (barra fixa no rodapé), `_kpi`/`_grade_kpis`, `_seletor_imagem` (prévia + "Escolher imagem…"/"Remover"; não grava nada até salvar: estado em `.estado`, gravação via `_gravar_imagem_escolhida` e limpeza via `_descartar_imagem_antiga`), `_avisar(texto, erro=False)` (toast verde de sucesso ou vermelho de erro que não exige resposta; confirmações seguem em messagebox).
- **Tk sem transparência:** frame "transparent" dentro de um container colorido às vezes pinta o fundo errado — passe a cor explícita (ex.: `fg_color=P["canvas"]`). `configure(image=None)` é ignorado pelo CTk: use `icone(None)` (transparente).
- **Login e entrada:** classe `TelaLogin` (painel da marca + formulário; "Mostrar" senha; "Lembrar meu usuário" via `banco.salvar_preferencia`; erro de senha embaixo do campo em `lbl_erro`; força troca de senha se `trocar_senha`), função `iniciar()` (login → app; `_sair` liga `relogar` e o laço reabre o login). `AppPDV.__init__(usuario)` guarda `self.usuario`/`self.eh_master`.
- **Barra lateral:** `_montar_barra_lateral` (guarda `self.barra` e `self.operador`), `_item_menu`/`_hover_menu`/`_marcar_menu` (item ativo com faixa accent + seta), operador (clique abre o menu de perfil) + botão sair.
- **Menu de perfil:** `_alternar_menu_perfil` (cartão flutuante acima do operador: Trocar senha, tamanho da letra `_seletor_letra`, modo touch e tela cheia com `_interruptor`, Sair), `_fechar_menu_perfil` (Esc ou `_clique_fora_do_menu`), `_carregar_preferencias`/`_chave_preferencia` (por usuário), `_mudar_letra`, `_alternar_touch`, `_alternar_tela_cheia` (também F11), `_reaplicar_visual` (refaz barra + tela atual mantendo carrinho e desconto; formulário de produto aberto é recarregado do banco). Telas master-only: Configurações e Usuários. `sincronizar_agora` (thread em 2º plano + `_aguardar_sync`).
- **Venda:** `mostrar_vendas` → `_topo_venda` (status do caixa, nº da venda, data, relógio `_atualizar_relogio`), `_montar_catalogo` (busca + abas de categoria `_selecionar_categoria` + grade; 3 a 5 colunas conforme a largura: `_ajustar_colunas`/`_configurar_colunas`, `LARGURA_CARTAO`, `COLUNAS_CATALOGO`), `_montar_checkout` (só totais; a forma de pagamento fica na janela de pagamento). Índices em memória `_por_codigo`/`_por_id`. `_agendar_busca` (debounce), `_filtrar_catalogo`, `_desenhar_catalogo` (máx. `LIMITE_CARTOES`; estados vazios via `_catalogo_vazio`: catálogo sem produtos → "Cadastrar primeiro produto", busca sem resultado → `_limpar_pesquisa`), `_cartao_produto`, `_visual_produto` (foto do produto ou, sem foto/arquivo ilegível, as iniciais coloridas; usado no catálogo e no carrinho), `_adicionar_ao_carrinho`, `adicionar_por_codigo` (código exato, senão 1º da busca; não achou → toast de erro), `_alterar_qtd` (passo 0,5 em `UNIDADES_FRACIONADAS`), `_digitar_qtd`, `remover_item`, `_limpar_carrinho`, `_redesenhar_carrinho`/`_linha_carrinho`, `_alternar_desconto` (R$ ou %), `_emitir_nfce`, `finalizar_venda` → `_janela_pagamento(total)` (modal: Dinheiro/Cartão/Pix em F1/F2/F3, valor recebido + botões de nota `NOTAS` + troco, "Dividir" via `_dividir_pagamento(total, atuais)`; Enter conclui, Esc volta; o troco vai para `registrar_venda`). Atalhos F2 (busca) e F4 (pagamento).
- **Produtos:** `mostrar_produtos` (PESQUISA: filtros + tabela + export), `_toggle_avancado`, `_coletar_filtros`, `_pesquisar_produtos`, `_editar_produto`, `_exportar_produtos`; `mostrar_form_produto(id)` (seções básicos/fiscais + foto `pf_foto` + barra de ações), `_marcar_erro`, `_ler_form_produto`, `_salvar_form`, `excluir_produto`, `_carregar_produto_no_form`.
- **Caixa:** `mostrar_caixa`, `_tela_abrir_caixa`, `abrir_caixa`, `_tela_caixa_aberto` (KPIs + movimentações + resumo do turno), `_movimento` (valor + motivo), `fechar_caixa`.
- **Histórico:** `mostrar_historico` (filtro de período/forma + atalhos `PERIODOS_RAPIDOS`: Hoje, Ontem, 7 e 30 dias, via `_periodo_rapido`; `_pintar_rapidos` destaca o atalho que bate com as datas), `_filtrar_historico`, `_exportar_vendas`. "Ver itens" (botão, duplo clique ou Enter na linha) → `_ver_itens_venda` → `_janela_recibo(venda)` (modal em forma de cupom: itens, subtotal/desconto, total, pagamentos, recebido em dinheiro e troco).
- **Relatório:** `mostrar_relatorio` (KPIs, barras por forma, mais vendidos).
- **Configuração (master):** `mostrar_config` (abas "Dados da empresa" — com a seção "Logo da loja" `cfg_logo` — e "Fiscal e NFC-e"), `_escolher_certificado`, `_salvar_config`.
- **Usuários (master):** `mostrar_usuarios`, `_atualizar_usuarios` (lista + cache `_usuarios` por id), `_carregar_usuario_sel`, `_montar_editor_usuario`, `_pintar_permissao`, `_usuario_selecionado`, `_salvar_usuario`, `_criar_usuario`, `_gravar_usuario`, `_trocar_senha_usuario`, `_alternar_ativo`, `_limpar_user_form` (= "Novo usuário").

### `pdv/icones.py` — ícones de traço (Pillow)
- `ICONES` (caminhos SVG 24×24 do protótipo), mini-rasterizador `_caminho`/`_arco`, `icone(nome, tamanho, cor)` → `CTkImage` em cache (`icone(None)` = transparente). Ícone novo: acrescente o caminho SVG em `ICONES`.

### `pdv/imagens.py` — logo e fotos de produto (Pillow)
- `preparar(origem, lado, quadrada)` (abre/valida, corrige rotação, reduz; limite `TAMANHO_MAXIMO`; lança `ImagemInvalida`), `gravar(img, prefixo)` (PNG sem metadados com nome único em `<dados>/imagens`), `remover`, `caminho` (basename: o banco não aponta para fora da pasta), `para_tela` (CTkImage com cantos ou placa de fundo já desenhados na imagem — `corner_radius` no CTkLabel alarga a imagem), `imagem(nome, largura, altura, …)` (cache; None se não há arquivo ou ele não abre → quem chama mostra o visual de reserva). `LADO_LOGO`, `LADO_FOTO`, `TIPOS` (filtro do diálogo).
- Só o nome do arquivo vai para o banco e para o sync; a imagem em si não é enviada ao central.

### `pdv/sync.py` — cliente de sincronização
- `sincronizar(servidor)` envia pendentes ao central (urllib, sem dependência nova); em falha de rede, mantém pendente. Env: `PDV_SERVIDOR`, `PDV_SYNC_TOKEN` (header `Authorization: Bearer`).

### `servidor/central.py` — servidor central (Flask)
- Endpoints `POST /sync/produtos`, `POST /sync/vendas` (idempotentes por uuid, JSON validado; vendas guardam também `desconto_centavos` e `troco_centavos`), `GET /status`. Token opcional `PDV_SYNC_TOKEN`. Banco próprio `dados/central.db`; colunas novas via `COLUNAS_NOVAS` (ALTER em `inicializar`, sem recriar).

### `pdv/exportacao.py` — exportação de produtos e vendas
- `exportar_produtos_csv(caminho, produtos)` — CSV `;` + BOM; cabeçalho baseado no **Registro 0200 do SPED Fiscal** + colunas detalhadas. `CABECALHO` tem a ordem. `_seguro` neutraliza injeção de fórmula (=,+,-,@).
- `exportar_vendas_csv(caminho, vendas)` — histórico filtrado (`CABECALHO_VENDAS`).

### `pdv/nfce.py` — pré-emissão de NFC-e (Fase 4, passo 1)
- `CONFIG_OBRIGATORIA`, `PRODUTO_OBRIGATORIO`, `validar_config`, `validar_produto`, `pendencias_emissao(config, produtos)`. Usado por `AppPDV._emitir_nfce`.

## Fases
- **Fase 1:** produtos, venda, caixa, relatório, histórico. ✅
- **Fase 2:** sincronização cliente–servidor idempotente. ✅
- **Fase 3:** acesso (master/operador), cadastro fiscal, config empresa. Em andamento.
- **Fase 4 (próxima):** emissor de NFC-e (montar/assinar/transmitir à SEFAZ em homologação) — precisa de certificado e roda/valida na máquina do usuário.

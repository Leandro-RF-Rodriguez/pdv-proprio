# PDV Próprio — briefing de design para o Figma

Ponto de venda (PDV) de desktop, offline-first, para pequeno comércio no Brasil.
Hoje é feito em Python + CustomTkinter; este pacote descreve **todas as telas**
para recriá-las/redesenhá-las no Figma. Idioma da interface: **português (BR)**.
Dinheiro sempre no formato `R$ 1.234,56`.

Arquivos deste pacote:

| Arquivo | Conteúdo |
|---|---|
| `01-PDV-Proprio-briefing.md` | Este briefing: tokens, componentes e cada tela em detalhe |
| `02-PDV-Proprio-interface-codigo.md` | Código-fonte completo da interface (fonte da verdade do layout) |
| `03-PDV-Proprio-tokens.json` | Tokens de cor, tipografia, raio e espaçamento |
| `04-tela-venda-atual.png` | Captura real da tela de Venda (versão anterior: ainda sem o botão "Emitir NFC-e" e sem os itens só do master) |
| `05-icone.png` | Ícone do app |

---

## 1. Fundamentos visuais

**Estilo:** verde, limpo, cantos arredondados, cartões claros com borda fina sobre
fundo verde-claro. Fonte **Manrope** (regular e bold). Modo claro.

### Cores

| Token | Hex | Uso |
|---|---|---|
| primary | `#173f35` | Barra lateral, botão primário, total, opção ativa |
| primary_strong | `#0d2c25` | Hover do primário, texto sobre accent |
| primary_soft | `#d8efe0` | Hover de cartões/itens, cabeçalho de tabela, linha selecionada |
| accent | `#a9c95d` | Logo "PDV", botão Sincronizar, botão "Novo produto" |
| accent_strong | `#52712f` | Hover do accent |
| accent_soft | `#eaf3d8` | Hover dos mini-botões −/+ |
| success | `#34755f` | Reservado para estados de sucesso |
| text | `#18342d` | Texto padrão |
| muted | `#728079` | Texto secundário, rótulos de seção, dicas |
| border | `#cfe2d6` | Bordas de cartões, inputs, botões secundários |
| surface | `#f8fdf9` | Fundo de cartões e tabelas |
| canvas | `#e6f5eb` | Fundo da janela |
| danger | `#b03a2e` | Botão de perigo, ✕ de remover, avisos de erro |
| danger_strong | `#8c2d24` | Hover do perigo |
| branco | `#ffffff` | Inputs, cartões de produto, itens do carrinho |
| sidebar_muted | `#8fb6a6` | Textos secundários na barra lateral |

### Tipografia (Manrope)

| Papel | Tamanho | Peso |
|---|---|---|
| Título da tela | 26 | Bold |
| Total da venda | 26 | Bold, cor primary |
| Valores de destaque (relatório) | 22 | Bold, primary |
| Subtítulo de cartão ("Venda atual") / título de seção | 15–16 | Bold |
| Corpo / inputs / botões | 13 | Regular / Bold (botões) |
| Rótulos e textos de tabela | 11–12 | Regular |
| Cabeçalho de tabela | 10 | Bold, primary sobre primary_soft |
| Dicas / legenda | 10–11 | Regular, muted |

### Raios, bordas e espaçamentos

- Cartão (`card`): raio **15**, borda 1 px `border`, fundo `surface`.
- Botão: raio **11**, altura ~28–32, texto 13 bold.
- Input: raio **10**, fundo branco, borda `border`.
- Cartão de produto: raio 15, altura 78. Item do carrinho: raio 12.
- Mini-botão (−, +, ✕): 26 × 24, raio 8.
- Margem da área de conteúdo: 24. Espaço entre blocos: 12–16. Padding interno de cartões: 14–16.
- Tabelas: linha de 30 px, fundo surface, sem bordas, linha selecionada `primary_soft`.

---

## 2. Componentes

| Componente | Variantes / estados |
|---|---|
| **Botão** | `primario` (primary/branco) · `secundario` (surface, texto primary, borda) · `perigo` (danger/branco) · `accent` (accent, texto primary_strong) · `sidebar` (transparente, texto branco, alinhado à esquerda, hover primary_strong). Estados: normal, hover, desabilitado ("Sincronizando…") |
| **Input** | normal, placeholder, senha mascarada (•), focado |
| **Dropdown (OptionMenu)** | fundo primary, texto branco bold, seta em primary_strong |
| **Checkbox** | "Controla estoque" — marcado em primary |
| **Cartão** | container padrão (surface + borda + raio 15) |
| **Cartão de produto** | branco, nome bold + preço "R$ 3,00" em 2 linhas centralizadas; hover primary_soft |
| **Item do carrinho** | branco, raio 12: linha 1 = descrição bold; linha 2 = [− qtd +] à esquerda e "R$ subtotal" (primary bold) + ✕ (danger) à direita |
| **Segmentado de pagamento** | 3 botões lado a lado: Dinheiro · Cartão · Pix. Ativo = primary/branco; inativo = surface/muted com borda |
| **Tabela** | cabeçalho primary_soft, linhas de 30 px, barra de rolagem vertical |
| **Diálogo de senha** | modal: título, "Nova senha", "Repita a nova senha", aviso em vermelho ("As senhas não conferem." / "Use ao menos 4 caracteres."), botão "Confirmar" |
| **Diálogo de valor** | modal simples: texto + campo + OK/Cancelar (usado em Suprimento, Sangria, Fechar caixa) |
| **Alertas** | info / aviso / erro (mensagens listadas em cada tela) |
| **Logo** | quadrado 46×46 (56×56 no login), raio 13, fundo accent, texto "PDV" bold primary_strong |

---

## 3. Estrutura da janela principal

- Janela 1040 × 700 (mínimo 880 × 580). Fundo `canvas`.
- **Barra lateral** fixa à esquerda, largura 200, fundo `primary`:
  - Topo: logo "PDV" + "PDV Próprio" (15 bold, branco) + "Ponto de venda" (10, sidebar_muted).
  - Menu (botões sidebar, largura 168): **Venda, Produtos, Caixa, Histórico, Relatório**; só para o papel *master*: **Configuração, Usuários**. O item ativo aparece com fundo primary_strong.
  - Rodapé: botão **Sincronizar** (accent, largura total) · "login · papel" (ex.: `master · master`, 10, sidebar_muted) · botões sidebar **Trocar senha** e **Sair**.
- **Área de conteúdo** à direita, margem 24, título da tela no topo (26 bold).

---

## 4. Telas

### 4.0 Login (janela separada 380 × 460, fundo canvas)
Cartão central (raio 16) com: logo PDV 56×56 · "PDV Próprio" (18 bold) ·
"Entre para continuar" (11, muted) · input **Usuário** · input **Senha** (mascarado) ·
botão primário **Entrar** (largura 250).
- Erro: alerta "Acesso negado — Usuário ou senha incorretos."
- Primeiro acesso / senha provisória: abre o diálogo **"Troca de senha obrigatória"** —
  "Por segurança, defina uma nova senha".

### 4.1 Venda (tela inicial)
Título "Venda" (ou "Venda  (caixa fechado)" quando não há caixa aberto).
Duas colunas:

**Esquerda — catálogo (expande):**
- Cartão de busca: input "Ler código de barras ou buscar produto…" + botão primário **Adicionar** (110).
- Grade rolável de **cartões de produto em 3 colunas** (nome + preço). Clicar adiciona ao carrinho.
- Vazio: "Nenhum produto." Muitos resultados (> 60): "+N produto(s) — refine a busca."

**Direita — checkout (cartão, largura 350):**
- "Venda atual" (16 bold).
- Lista rolável de itens do carrinho. Vazio: "Carrinho vazio / Toque num produto para adicionar" (muted, centralizado).
- Rodapé: "Forma de pagamento" (11, muted) → segmentado **Dinheiro | Cartão | Pix**.
- Total **"R$ 0,00"** (26 bold, primary, alinhado à direita).
- "Trib. aprox.: R$ 0,00" (10, muted, à direita) — Lei da Transparência.
- Botão primário largo **Finalizar venda**.
- Botão secundário largo **Emitir NFC-e**.

Mensagens: "Carrinho vazio — Adicione pelo menos um produto." ·
"Venda registrada — Venda #12 concluída. Total: R$ 23,50" ·
NFC-e incompleta: "Faltam dados para emitir — Para emitir a NFC-e, complete: • …" ·
NFC-e OK: "Pré-emissão OK — Dados completos para NFC-e…".

Dados de exemplo: Água mineral 500ml R$ 3,00 · Refrigerante lata R$ 5,00 ·
Pão francês (kg) R$ 16,90 · Café 500g R$ 24,90 · Leite integral 1L R$ 5,49 ·
Biscoito recheado R$ 3,79 · Arroz 5kg R$ 27,90 · Feijão 1kg R$ 8,49 · Sabão em pó R$ 14,90.

### 4.2 Produtos — pesquisa
Título "Produtos". Cartão de filtros (grade de 4 colunas):
- Linha 1: input "Descrição, código EAN ou interno" (2 colunas) · dropdown **Ativos / Inativos / Todos** · dropdown **Todos / Controla estoque / Não controla**.
- Linha 2 (oculta até clicar "Filtro avançado"): inputs **NCM · CFOP · CST/CSOSN · Origem · Categoria (merc.)**.
- Linha 3: botões **Pesquisar** (primário) · **Filtro avançado** (secundário) · **Novo produto** (accent) · **Exportar CSV** (secundário).

Tabela (expande): ID · Cód. EAN · Descrição · Un · Preço (R$) · Estoque · Ativo (Sim/Não).
Legenda: "Duplo clique num produto para editar. A exportação CSV usa o filtro atual (padrão SPED 0200)."

### 4.3 Produtos — formulário (Novo produto / Editar produto)
Título "Novo produto" ou "Editar produto". Cartão rolável, grade de 4 colunas, inputs com placeholder:
- Seção **"Dados básicos"** (11 bold muted): Descrição * · Código de barras (EAN) · Código interno · Categoria (merc.) · Unidade * · Preço venda * (R$) · Custo (R$) · Estoque.
- Checkbox **Controla estoque**.
- Seção **"Fiscal (NFC-e / SPED)"**: NCM * · CEST · CFOP * · Origem * (0-8) · CST/CSOSN * · Tipo item (00-99) · ICMS % · Tributos aprox. %.
- Botões: **Salvar** (primário) · **Excluir** (perigo, só ao editar) · **Voltar** (secundário).

Mensagens: "Campo obrigatório — Informe: NCM." · "Código repetido — Já existe um produto com o código 789…" · "Excluir produto — Deseja mesmo excluir este produto?" (Sim/Não).

### 4.4 Caixa — dois estados
**Caixa fechado:** cartão com "Caixa fechado. Abra para começar a operar." ·
"Operador:" + input "Nome do operador" · "Fundo de troco (R$):" + input "ex: 100,00" ·
botão primário **Abrir caixa** (à direita).

**Caixa aberto:**
1. Cartão: "Caixa aberto por Maria  ·  desde 2026-10-29 08:02" (14 bold, primary).
2. Cartão resumo (rótulo à esquerda, valor à direita, 14):
   Fundo de troco (abertura) · Suprimentos (+) · Sangrias (−) · Vendas em dinheiro (+) ·
   **Esperado na gaveta** (destacado, bold primary) · Total vendido (todas as formas).
3. Botões: **Suprimento** e **Sangria** (secundários, à esquerda) · **Fechar caixa** (perigo, à direita).

Fechar caixa: diálogo "Esperado na gaveta: R$ 350,00 / Digite o valor contado (R$):" →
resultado "Caixa bateu certo." ou "Sobra de R$ 5,00." / "Falta de R$ 2,50.".

### 4.5 Histórico de vendas
Título "Histórico de vendas". Tabela que ocupa a tela:
Venda (#12) · Data/hora (2026-10-29 14:31:05) · Itens · Pagamento (Dinheiro, Pix) · Total (R$).
Vazio: "(nenhuma venda ainda)".

### 4.6 Relatório do dia
Título "Relatório do dia  ·  2026-10-29".
Cartão com 2 indicadores: "Vendas concluídas" / **37** (esquerda) e "Total vendido" / **R$ 1.284,40** (direita) — rótulo 14 muted, valor 22 bold primary.
Subtítulo "Por forma de pagamento" (16 bold) + tabela curta: Forma · Valor (R$). Vazio: "(sem vendas hoje)".

### 4.7 Configuração da empresa (só master)
Título "Configuração da empresa". Página rolável com seções (título 15 bold primary + cartão com rótulo à direita / campo à esquerda-expandido):
- **Empresa:** Razão social * · Nome fantasia · CNPJ * · Inscrição Estadual · Inscrição Municipal · Regime (CRT) [dropdown: 1 - Simples Nacional / 2 - Simples Nacional (excesso) / 3 - Regime Normal].
- **Endereço:** CEP · Logradouro · Número · Complemento · Bairro · Município · Cód. município (IBGE) · UF *.
- **Contato:** Telefone · E-mail.
- **Fiscal / NFC-e:** Ambiente [dropdown homologacao / producao] · Série · Próximo número NFC-e · CSC · ID do CSC · Certificado (.pfx) + botão **Escolher** · Senha do certificado (mascarada).
- Botão primário **Salvar configuração**.

### 4.8 Usuários (só master)
Título "Usuários". Cartão formulário (4 colunas): Login * · Nome completo · E-mail · Senha (no cadastro) * (mascarada);
"Papel:" + dropdown **operador / master**.
Botões: **Criar** (primário) · **Salvar** · **Trocar senha** · **Ativar/Desativar** · **Limpar** (secundários).
Tabela: Login · Nome · Papel · Ativo (sim/não).
Legenda: "Clique num usuário para editar. A senha só muda em 'Trocar senha'."
Mensagens: "Login repetido" · "Não permitido — O sistema precisa de pelo menos um master ativo." · "Senha alterada. O usuário deverá trocá-la no próximo login."

---

## 5. Fluxos principais

1. **Login** → (troca de senha obrigatória, se provisória) → **Venda**.
2. **Venda:** ler código/buscar → clicar cartão → ajustar −/+ → escolher pagamento → Finalizar → alerta de sucesso → carrinho zera.
3. **Caixa:** Abrir (operador + fundo de troco) → Suprimento/Sangria durante o dia → Fechar (conferência sobra/falta).
4. **Produtos:** Pesquisar → duplo clique → Editar → Salvar; ou Novo produto.
5. **Sincronizar** (barra lateral): botão vira "Sincronizando…" desabilitado → alerta com o resultado ("Enviado(s): 3 produto(s) e 10 venda(s)." / "Servidor indisponível…" / "Nada pendente para enviar.").
6. **Sair** → volta ao login.

## 6. Sugestão de prompt para o Figma Make

> Recrie o app de ponto de venda "PDV Próprio" descrito nos arquivos anexos como um
> protótipo desktop navegável (1040×700), em português do Brasil, usando exatamente a
> paleta, a fonte Manrope e os componentes do briefing. Comece pela tela de Login e
> pela tela de Venda (catálogo em cartões + checkout com carrinho, pagamento e total);
> depois Produtos (pesquisa e formulário), Caixa (fechado e aberto), Histórico,
> Relatório, Configuração e Usuários. A barra lateral navega entre as telas; use os
> dados de exemplo do briefing. Use a captura de tela como referência visual.

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
| Interface | [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter) (desktop, leve e moderno) + Pillow (ícones) |
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

## 📥 Como baixar e instalar

Ainda não há versão pronta para download na aba *Releases*: o sistema é instalado
a partir do código, em quatro passos. Os comandos abaixo são para **Linux
(Ubuntu/Debian/Mint)**; as diferenças do Windows estão indicadas em cada passo.

### 1. Pré-requisitos

- **Python 3.10 ou mais novo** (testado com 3.12), com **Tkinter**.
- **Git** (opcional — dá para baixar o ZIP no lugar).

```bash
sudo apt install python3 python3-venv python3-tk git
```

> **Windows:** instale o Python em [python.org](https://www.python.org/downloads/) marcando
> **“Add python.exe to PATH”** e mantendo a opção **“tcl/tk and IDLE”** (já vem marcada).

**Fonte Manrope (recomendado):** a interface usa a fonte
[Manrope](https://fonts.google.com/specimen/Manrope). Sem ela o sistema funciona,
mas com a fonte padrão do sistema. Baixe em *Get font → Download all*, extraia e:

- **Linux:** copie os arquivos `.ttf` da pasta `static/` para `~/.local/share/fonts/` e rode `fc-cache -f`;
- **Windows:** selecione os `.ttf`, clique com o botão direito → **Instalar**.

### 2. Baixar o código

```bash
git clone https://github.com/Leandro-RF-Rodriguez/pdv-proprio.git
cd pdv-proprio
```

Sem Git: na página do repositório, clique em **Code → Download ZIP**, extraia e abra
um terminal dentro da pasta extraída.

### 3. Instalar as dependências

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

> **Windows:** use `py -m venv venv` e `venv\Scripts\activate`.

Pronto para usar a partir do código:

```bash
python3 pdv_app.py
```

Os dados ficam na pasta `dados/` do projeto.

### 4. Gerar o executável e criar o atalho (opcional)

O executável dispensa o terminal no dia a dia. Com o `venv` ativado:

```bash
pyinstaller --noconfirm pdv-proprio.spec
```

Ele é gerado em `dist/pdv-proprio` (no Windows, `dist\pdv-proprio.exe`) e só roda no
sistema em que foi gerado — para usar no Windows, gere o build no Windows.

**Atalho no menu de aplicativos (Linux):**

```bash
mkdir -p ~/.local/bin ~/.local/share/applications ~/.local/share/icons
cp dist/pdv-proprio ~/.local/bin/
cp assets/icon.png ~/.local/share/icons/pdv-proprio.png
cat > ~/.local/share/applications/pdv-proprio.desktop <<EOF
[Desktop Entry]
Type=Application
Name=PDV Próprio
Comment=Ponto de venda
Exec=$HOME/.local/bin/pdv-proprio
Icon=$HOME/.local/share/icons/pdv-proprio.png
Terminal=false
Categories=Office;
EOF
```

O **PDV Próprio** passa a aparecer no menu do sistema.

> **Windows:** clique com o botão direito em `dist\pdv-proprio.exe` → **Mostrar mais opções →
> Enviar para → Área de trabalho (criar atalho)**.

### Primeiro acesso

Entre com o usuário **`master`** e a senha **`master`**. O sistema obriga a criar uma
senha nova logo no primeiro login. Depois, em **Configurações**, preencha os dados da
empresa e, em **Usuários**, crie os operadores do caixa.

### Onde ficam os dados e como fazer backup

| Como você abre o sistema | Pasta dos dados |
| --- | --- |
| Pelo executável | `~/.pdv_proprio/` (Windows: `C:\Users\<seu usuário>\.pdv_proprio\`) |
| Pelo código (`python3 pdv_app.py`) | `dados/`, dentro da pasta do projeto |

O banco é o arquivo `pdv.db`. Para fazer backup, **feche o sistema** e copie a pasta
inteira (inclui os arquivos `pdv.db-wal`/`pdv.db-shm`, quando existirem). Os dois modos
usam pastas diferentes: os dados de um não aparecem no outro.

### Atualizar para uma versão nova

```bash
cd pdv-proprio
git pull
source venv/bin/activate
pip install -r requirements.txt
pyinstaller --noconfirm pdv-proprio.spec      # só se você usa o executável
cp dist/pdv-proprio ~/.local/bin/             # só se você criou o atalho
```

O banco é atualizado sozinho na próxima abertura, sem apagar dados. Sem Git, baixe o
ZIP novo e repita os passos 3 e 4 — a pasta de dados do executável não é afetada.

### Desinstalar (Linux)

```bash
rm ~/.local/bin/pdv-proprio ~/.local/share/applications/pdv-proprio.desktop ~/.local/share/icons/pdv-proprio.png
```

A pasta `~/.pdv_proprio/` (vendas, produtos, usuários) **não** é apagada; remova-a
manualmente só se não precisar mais dos dados.

## 🔄 Servidor de sincronização (opcional)

```bash
python3 -m servidor.central       # escuta na porta 5001
```

> **Segurança:** para exigir autenticação na sincronização, defina a mesma variável
> `PDV_SYNC_TOKEN` no servidor e no PDV (e `PDV_SERVIDOR` no PDV, se o central estiver
> em outra máquina). Nunca grave tokens, senhas ou certificados no código ou no git.

## 📁 Estrutura

```
pdv-proprio/
├── pdv_app.py            # ponto de entrada (usado também pelo PyInstaller)
├── pdv/                  # pacote do aplicativo de desktop
│   ├── interface.py      # janela (CustomTkinter), visual do protótipo do Figma
│   ├── icones.py         # ícones de traço desenhados com Pillow
│   ├── banco.py          # camada de acesso ao banco (todo o SQL e o schema ficam aqui)
│   ├── sync.py           # cliente de sincronização
│   ├── exportacao.py     # exportação de produtos e vendas (CSV)
│   └── nfce.py           # validação de pré-emissão de NFC-e
├── servidor/
│   └── central.py        # servidor central de sincronização (Flask)
├── assets/               # ícone e outros recursos visuais
├── docs/                 # screenshot e documentação
├── dados/                # bancos locais e certificados (fora do git)
├── pdv-proprio.spec      # receita do PyInstaller
└── requirements.txt      # dependências
```

## 🗺️ Roadmap

- [x] **Fase 1** — MVP local (produtos, vendas, caixa, relatório)
- [ ] **Fase 2** — sincronização com um sistema Web central
- [ ] **Fase 3** — fiscal (NFC-e / SEFAZ)

---

Projeto pessoal de estudo. A arquitetura é inspirada em padrões da indústria de PDV; todo o código é original.

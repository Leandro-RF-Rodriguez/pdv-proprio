"""PDV Próprio — aplicativo de desktop.

Janela feita com CustomTkinter, conversando direto com o banco SQLite pela
camada em banco.py. O visual segue o protótipo do Figma Make ("Aprimorar
Estética do PDV"): barra lateral verde-escura com ícones, cabeçalhos de página
com sobretítulo, cartões brancos de borda suave, indicadores (KPIs), pílulas de
status e avisos rápidos (toasts) no lugar de janelas de "OK".

Rodar com:  python3 -m pdv   (ou python3 pdv_app.py, na raiz)
"""

import re
import threading
import tkinter as tk
import urllib.error
from datetime import date, datetime, timedelta
from tkinter import ttk, messagebox, filedialog

import customtkinter as ctk

from . import banco
from . import exportacao
from . import imagens
from . import nfce
from . import sync
from .icones import icone

ctk.set_appearance_mode("light")

FORMAS_PAGAMENTO = [("Dinheiro", "cash"), ("Cartão", "card"), ("Pix", "pix")]
FONTE = "Manrope"
SENHA_MINIMA = 4
LIMITE_CARTOES = 45      # cartões do catálogo desenhados de uma vez (widgets são pesados)
ATRASO_BUSCA_MS = 200    # espera o operador parar de digitar antes de redesenhar
UNIDADES_FRACIONADAS = ("KG", "G", "L", "ML", "M")  # no carrinho, −/+ andam de 0,5
LARGURA_CARTAO = 200     # largura mínima de um cartão do catálogo: define quantas colunas cabem
COLUNAS_CATALOGO = (3, 5)  # mínimo e máximo de colunas do catálogo
NOTAS = (1000, 2000, 5000, 10000, 20000)  # atalhos de "valor recebido" (centavos)
ESCALAS_FONTE = {"P": 0.9, "M": 1.0, "G": 1.15}  # tamanho da letra (menu de perfil), por usuário
ALTURA_TOUCH = 48        # altura mínima de botões e campos no "modo touch"

# Explicações em linguagem simples para os campos fiscais (ícone "?").
AJUDA_FISCAL = {
    "ncm": "Código de 8 dígitos que diz o que é o produto para a Receita. "
           "Está na nota fiscal de compra do fornecedor. Ex.: água mineral = 22011000.",
    "cest": "Só é exigido para produtos com substituição tributária (bebidas, cigarros, "
            "combustíveis…). Se o fornecedor não informa, deixe em branco.",
    "cfop": "Diz o tipo da operação. Para venda ao consumidor dentro do estado, "
            "quase sempre é 5102 (ou 5405 se o produto tem substituição tributária).",
    "origem": "De onde vem o produto: 0 = nacional (o mais comum), 1 ou 2 = importado. "
              "Na dúvida, confirme com o contador.",
    "cst": "Como o ICMS é cobrado. No Simples Nacional, use o CSOSN (ex.: 102). "
           "Peça ao contador o código certo para os seus produtos.",
    "tipo_item": "Classificação para o SPED. Para mercadoria comprada para revenda, use 00.",
    "aliquota_icms": "Porcentagem do ICMS. No Simples Nacional normalmente fica 0.",
    "aliquota_aprox": "Porcentagem aproximada de impostos que aparece no cupom (Lei da "
                      "Transparência). A tabela IBPT informa o valor por NCM.",
}
UFS = ["AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", "MA", "MG", "MS", "MT", "PA",
       "PB", "PE", "PI", "PR", "RJ", "RN", "RO", "RR", "RS", "SC", "SE", "SP", "TO"]
DIAS_SEMANA = ["Segunda-feira", "Terça-feira", "Quarta-feira", "Quinta-feira", "Sexta-feira", "Sábado", "Domingo"]
MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
         "agosto", "setembro", "outubro", "novembro", "dezembro"]

# Paleta do protótipo (tokens do Figma).
P = {
    "primary_950": "#0b2b24",
    "primary_900": "#113b31",
    "primary_800": "#194b3e",
    "primary_700": "#266454",
    "primary_100": "#dcefe7",
    "primary_50": "#edf7f1",
    "accent": "#b4d66a",
    "accent_hover": "#c1df7d",
    "accent_soft": "#edf7d7",
    "canvas": "#f2f7f4",
    "surface": "#ffffff",
    "text": "#17372f",
    "text_soft": "#526b63",
    "muted": "#64746e",  # contraste ≥ 4,5:1 sobre canvas/surface (texto pequeno legível)
    "line": "#d9e6df",
    "line_soft": "#e9f0ec",
    "line_hover": "#9fc5b2",
    "table_head": "#f7faf8",
    "topbar": "#fcfdfd",
    "danger": "#b14b3d",
    "danger_hover": "#963c32",
    "danger_soft": "#f8e8e5",
    "status_ok": "#52a575",
    # Barra lateral
    "nav_text": "#b8cec6",
    "nav_label": "#719b8c",
    "nav_hover": "#1a3831",
    "nav_line": "#1d3c35",
    "brand_sub": "#91b4a6",
    "kpi_sub": "#b9d0c7",
    "avatar": "#dcece4",
}

# Pílulas de status: (texto, fundo, borda)
TONS = {
    "sucesso": ("#267052", "#eaf7ef", "#cee7d8"),
    "neutro": (P["text_soft"], P["canvas"], P["line"]),
    "aviso": ("#775e1d", "#fff8dc", "#eadca9"),
    "perigo": (P["danger"], P["danger_soft"], "#efcfc9"),
}

# Fundos dos "visuais" de produto (iniciais coloridas), como no protótipo.
CORES_PRODUTO = ["#dff1e7", "#f7ddd3", "#f4e8cc", "#e8ddd3", "#dcebf1", "#e8e0f0", "#f4f0db", "#efdedc", "#d8efec"]

_ESTILOS_BOTAO = {
    "primario": dict(fg_color=P["primary_900"], hover_color=P["primary_950"], text_color="#ffffff"),
    "secundario": dict(fg_color=P["surface"], hover_color=P["primary_50"], text_color=P["primary_800"],
                       border_width=1, border_color=P["line"]),
    "perigo": dict(fg_color=P["danger"], hover_color=P["danger_hover"], text_color="#ffffff"),
    "accent": dict(fg_color=P["accent"], hover_color=P["accent_hover"], text_color=P["primary_950"]),
}


# ---------- Formatação ----------
def _reais(centavos):
    """Centavos -> 'R$ 1.234,56'."""
    inteiro, _, frac = banco.formatar_reais(abs(centavos)).partition(",")
    milhar = f"{int(inteiro):,}".replace(",", ".")
    return f"{'-' if centavos < 0 else ''}R$ {milhar},{frac}"


def _qtd(valor):
    return f"{valor:g}".replace(".", ",")


def _iniciais(texto):
    """'Água mineral' -> 'AG', 'Café' -> 'CF' (1ª letra + 1ª consoante seguinte)."""
    palavra = next((p for p in (texto or "").split() if p[:1].isalnum()), "?")
    consoante = next((c for c in palavra[1:] if c.isalpha() and c.lower() not in "aeiouáéíóúâêôãõà"), palavra[1:2])
    return (palavra[0] + consoante).upper()


def _iniciais_nome(nome):
    """'Marina Costa' -> 'MC'."""
    partes = (nome or "?").split()
    return "".join(p[0] for p in partes[:2]).upper()


def _data_hora(iso):
    """'2026-10-29T15:31:05' -> '29/10/2026 · 15:31'."""
    momento = datetime.fromisoformat(iso)
    return momento.strftime("%d/%m/%Y · %H:%M")


def _data_iso(texto):
    """'29/10/2026' -> '2026-10-29' (ValueError se inválida)."""
    return datetime.strptime(texto.strip(), "%d/%m/%Y").date().isoformat()


def _nome_loja():
    """Nome fantasia (ou razão social) cadastrado nas Configurações; '' se não houver."""
    cfg = banco.ler_config_fiscal()
    nome = (cfg.get("nome_fantasia") or cfg.get("razao_social") or "").strip()
    return nome if len(nome) <= 40 else nome[:39] + "…"


def _logo_loja():
    """Nome do arquivo da logo (Configurações); None se não houver."""
    return banco.ler_config_fiscal().get("logo_arquivo") or None


def _ler_reais(texto):
    """'R$ 1.234,56', '1234,56' ou '100' -> centavos. ValueError se inválido ou negativo.

    '100' é sempre cem reais (nunca R$ 1,00): é o que o operador quer dizer ao digitar.
    """
    texto = texto.replace("R$", "").replace(" ", "")
    if "," in texto or re.fullmatch(r"\d{1,3}(\.\d{3})+", texto):
        texto = texto.replace(".", "")  # ponto de milhar ('1.000' = mil reais)
    centavos = banco.para_centavos(texto)
    if centavos < 0:
        raise ValueError(texto)
    return centavos


def _centavos_ou_zero(texto):
    texto = (texto or "").strip()
    return banco.para_centavos(texto) if texto else 0


class _Estilo:
    """Componentes visuais compartilhados pela janela de login e pelo app."""

    def _fechar(self):
        """Fecha a janela cancelando antes os `after` pendentes do CustomTkinter.

        Sem isso, animações de clique e checagens de DPI disparam depois do destroy
        e o terminal mostra 'invalid command name ...'.

        Cancela direto no Tcl, não com `after_cancel`: ele apaga o comando Python do
        `after`, mas o nome fica na lista do widget que o agendou (ex.: a animação de
        clique do botão Sair). No destroy o tkinter tentaria apagá-lo de novo, o Tk
        aborta no meio ('can't delete Tcl command') e a janela fica branca e aberta.
        """
        for agendado in self.tk.call("after", "info"):
            self.tk.call("after", "cancel", agendado)
        self.destroy()
        # As imagens do Tk pertencem a esta janela e morrem com ela: a próxima (login <-> PDV)
        # recriaria um ícone/logo em cache e o Tk acusaria 'image "pyimage1" doesn't exist'.
        icone.cache_clear()
        imagens.imagem.cache_clear()

    @property
    def _escala(self):
        """Multiplicador do tamanho da letra (P/M/G do menu de perfil; o login usa 1)."""
        return getattr(self, "_escala_fonte", 1.0)

    def _alvo(self, altura, touch=ALTURA_TOUCH):
        """Altura de um alvo de clique: no "modo touch" ela sobe para `touch` (padrão 48 px)."""
        return max(altura, touch) if getattr(self, "touch", False) else altura

    def _fonte(self, tamanho=13, negrito=False):
        # Reaproveita a mesma fonte: criar um CTkFont por widget custa caro.
        tamanho = round(tamanho * self._escala)
        chave = (tamanho, negrito)
        if chave not in self._fontes:
            self._fontes[chave] = ctk.CTkFont(family=FONTE, size=tamanho, weight="bold" if negrito else "normal")
        return self._fontes[chave]

    def _fonte_tk(self, tamanho, negrito=False):
        """Fonte para widgets tk puros (mais leves que os CTk): tamanho em pixels."""
        return (FONTE, -round(tamanho * self._escala), "bold" if negrito else "normal")

    def _rotulo(self, parent, texto, tamanho=12, negrito=False, cor="text", **kw):
        return ctk.CTkLabel(parent, text=texto, font=self._fonte(tamanho, negrito),
                            text_color=P.get(cor, cor), **kw)

    def _btn(self, parent, text, command, tipo="primario", width=140, height=40, icone_nome=None, lado="left"):
        estilo = _ESTILOS_BOTAO[tipo]
        imagem = icone(icone_nome, 17, estilo["text_color"]) if icone_nome else None
        return ctk.CTkButton(
            parent, text=text, command=command, width=width, height=self._alvo(height), corner_radius=12,
            font=self._fonte(12, True), image=imagem, compound=lado, **estilo,
        )

    def _link(self, parent, texto, comando, tamanho=11, cor="primary_700"):
        return ctk.CTkButton(
            parent, text=texto, command=comando, width=10, height=24, corner_radius=6,
            fg_color="transparent", hover_color=P["primary_50"], text_color=P[cor],
            font=self._fonte(tamanho, True),
        )

    def _card(self, parent, **kw):
        opcoes = dict(fg_color=P["surface"], corner_radius=15, border_width=1, border_color=P["line"])
        return ctk.CTkFrame(parent, **{**opcoes, **kw})

    def _entry(self, parent, placeholder="", senha=False, **kw):
        opcoes = dict(height=40, corner_radius=9, fg_color="#ffffff", border_width=1, border_color=P["line"],
                      text_color=P["text"], placeholder_text_color="#a0ada8", font=self._fonte(12))
        opcoes.update(kw)
        opcoes["height"] = self._alvo(opcoes["height"])
        return ctk.CTkEntry(parent, placeholder_text=placeholder, show="•" if senha else "", **opcoes)

    def _titulo_campo(self, parent, rotulo, obrigatorio=False, ajuda=None):
        linha = ctk.CTkFrame(parent, fg_color="transparent")
        self._rotulo(linha, rotulo, 10, True, "text_soft").pack(side="left")
        if obrigatorio:
            self._rotulo(linha, " *", 10, True, "danger").pack(side="left")
        if ajuda:
            self._dica(linha, ajuda).pack(side="left", padx=(6, 0))
        return linha

    def _dica(self, parent, texto):
        """Bolinha "?" que mostra uma explicação ao passar o mouse (ou tocar)."""
        botao = ctk.CTkLabel(parent, text="?", width=16, height=16, corner_radius=8, cursor="question_arrow",
                             fg_color=P["primary_100"], text_color=P["primary_800"], font=self._fonte(10, True))
        balao = {}  # "rotulo" (criado uma vez e reaproveitado), "agendado" (atraso antes de aparecer)

        def sob_o_mouse():
            # O CTkLabel são dois widgets (canvas + label): ir de um ao outro gera <Leave>.
            sob = botao.winfo_containing(*botao.winfo_pointerxy())
            return sob is not None and str(sob).startswith(str(botao))

        def visivel():
            return "rotulo" in balao and balao["rotulo"].winfo_ismapped()

        def cancelar_atraso():
            if "agendado" in balao:
                botao.after_cancel(balao.pop("agendado"))

        def exibir():
            # Desenhado dentro da própria janela (place), não num Toplevel: em tela cheia,
            # cada janela nova por cima faz o gerenciador de janelas/compositor redesenhar
            # tudo — a tela trava e pisca em branco.
            cancelar_atraso()
            janela = botao.winfo_toplevel()
            if "rotulo" not in balao:
                balao["rotulo"] = tk.Label(janela, text=texto, bg=P["primary_950"], fg="#ffffff",
                                           font=self._fonte_tk(12), wraplength=280, justify="left", padx=12, pady=9)
            rotulo = balao["rotulo"]
            rotulo.update_idletasks()
            largura, altura = rotulo.winfo_reqwidth(), rotulo.winfo_reqheight()
            # Abaixo do "?", sem cobrir o ponteiro (balão sob o mouse = <Leave> e pisca-pisca) e dentro da janela.
            x = botao.winfo_rootx() - janela.winfo_rootx()
            y = botao.winfo_rooty() - janela.winfo_rooty() + botao.winfo_height() + 6
            if y + altura > janela.winfo_height():
                y -= botao.winfo_height() + altura + 12
            rotulo.place(x=max(min(x, janela.winfo_width() - largura - 8), 0), y=max(y, 0))
            rotulo.lift()

        def mostrar(_evento=None):
            if "agendado" not in balao and not visivel():
                balao["agendado"] = botao.after(250, exibir)  # passar o mouse de raspão não abre

        def esconder(_evento=None, forcar=False):
            if not forcar and sob_o_mouse():
                return
            cancelar_atraso()
            if "rotulo" in balao:
                balao["rotulo"].place_forget()

        def clique(_evento=None):
            if visivel():
                esconder(forcar=True)
            else:
                exibir()

        def destruir(_evento=None):
            # O balão é filho da janela, não do "?": some junto quando a tela é refeita.
            cancelar_atraso()
            if "rotulo" in balao:
                balao.pop("rotulo").destroy()

        botao.bind("<Enter>", mostrar)
        botao.bind("<Button-1>", clique)
        botao.bind("<Leave>", esconder)
        botao.bind("<Destroy>", destruir)
        return botao

    def _campo(self, parent, rotulo, placeholder="", valor="", obrigatorio=False, senha=False, ajuda=None):
        """Rótulo em cima + campo. O campo fica em `.entrada`."""
        quadro = ctk.CTkFrame(parent, fg_color="transparent")
        self._titulo_campo(quadro, rotulo, obrigatorio, ajuda).pack(anchor="w", pady=(0, 5))
        quadro.entrada = self._entry(quadro, placeholder, senha=senha)
        quadro.entrada.pack(fill="x")
        if valor:
            quadro.entrada.insert(0, valor)
        return quadro

    def _select(self, parent, valores, comando=None):
        """Lista de opções com borda (OptionMenu dentro de uma moldura). Devolve (moldura, menu)."""
        moldura = ctk.CTkFrame(parent, fg_color="#ffffff", corner_radius=9, border_width=1,
                               border_color=P["line"], height=self._alvo(40))
        menu = ctk.CTkOptionMenu(
            moldura, values=valores, height=self._alvo(36, ALTURA_TOUCH - 4), corner_radius=8, anchor="w",
            fg_color="#ffffff", button_color="#ffffff", button_hover_color=P["primary_50"],
            text_color=P["text"], dropdown_fg_color="#ffffff", dropdown_hover_color=P["primary_50"],
            dropdown_text_color=P["text"], font=self._fonte(12), dropdown_font=self._fonte(12), command=comando,
        )
        menu.pack(fill="x", padx=2, pady=2)
        return moldura, menu

    def _campo_select(self, parent, rotulo, valores, valor=None, obrigatorio=False, comando=None):
        quadro = ctk.CTkFrame(parent, fg_color="transparent")
        self._titulo_campo(quadro, rotulo, obrigatorio).pack(anchor="w", pady=(0, 5))
        moldura, quadro.entrada = self._select(quadro, valores, comando=comando)
        moldura.pack(fill="x")
        if valor in valores:
            quadro.entrada.set(valor)
        return quadro

    def _selo_marca(self, parent, lado):
        """Quadrado da marca: a logo da loja ou, sem logo, o carrinho do PDV."""
        selo = ctk.CTkLabel(parent, text="", width=lado, height=lado)
        self._pintar_selo(selo, lado)
        return selo

    def _pintar_selo(self, selo, lado):
        # Logo sobre placa branca (desenhada na imagem): logo escura também aparece na barra verde.
        logo = imagens.imagem(_logo_loja(), lado, lado, round(lado * 0.3), False, "#ffffff", round(lado / 8))
        if logo:
            selo.configure(image=logo, fg_color="transparent", corner_radius=0)
        else:
            selo.configure(image=icone("cart", round(lado / 2), P["primary_950"]), fg_color=P["accent"],
                           corner_radius=round(lado * 0.3))

    def _pill(self, parent, texto, tom="sucesso"):
        cor, fundo, borda = TONS[tom]
        quadro = ctk.CTkFrame(parent, fg_color=fundo, border_width=1, border_color=borda, corner_radius=11)
        ctk.CTkLabel(quadro, text=texto, font=self._fonte(10, True), text_color=cor, height=18).pack(padx=10, pady=2)
        return quadro

    def _dialogo(self, titulo, descricao, campos, validar=None, botao="Confirmar"):
        """Janela modal com campos. campos: [(chave, rótulo, valor_inicial, senha)].

        validar(valores) devolve uma mensagem de erro (mostrada na janela) ou None.
        Devolve o dict {chave: texto} ou None se cancelar.
        """
        janela = ctk.CTkToplevel(self)
        janela.title(titulo)
        janela.resizable(False, False)
        janela.transient(self)
        janela.configure(fg_color=P["surface"])
        resultado = {}

        corpo = ctk.CTkFrame(janela, fg_color="transparent")
        corpo.pack(padx=24, pady=22, fill="both")
        self._rotulo(corpo, titulo, 17, True, "primary_950").pack(anchor="w")
        if descricao:
            self._rotulo(corpo, descricao, 11, cor="text_soft", justify="left", wraplength=300).pack(anchor="w", pady=(3, 12))
        entradas = {}
        for chave, rotulo, valor, senha in campos:
            campo = self._campo(corpo, rotulo, valor=valor, senha=senha)
            campo.entrada.configure(width=300)
            campo.pack(fill="x", pady=5)
            entradas[chave] = campo.entrada
        aviso = self._rotulo(corpo, "", 11, cor="danger", justify="left", wraplength=300)
        aviso.pack(anchor="w")

        def confirmar(_evento=None):
            valores = {chave: entrada.get() for chave, entrada in entradas.items()}
            erro = validar(valores) if validar else None
            if erro:
                aviso.configure(text=erro)
                return
            resultado.update(valores)
            janela.destroy()

        botoes = ctk.CTkFrame(corpo, fg_color="transparent")
        botoes.pack(fill="x", pady=(10, 0))
        self._btn(botoes, botao, confirmar, width=150).pack(side="right")
        self._btn(botoes, "Cancelar", janela.destroy, "secundario", 110).pack(side="right", padx=(0, 8))

        lista = list(entradas.values())
        for atual, proxima in zip(lista, lista[1:]):
            atual.bind("<Return>", lambda e, p=proxima: p.focus())
        lista[-1].bind("<Return>", confirmar)
        janela.bind("<Escape>", lambda e: janela.destroy())

        def focar():
            try:
                janela.grab_set()  # modal: bloqueia a janela de trás
            except tk.TclError:
                pass
            lista[0].focus()

        janela.after(120, focar)
        janela.wait_window()
        return resultado or None

    def _pedir_senha(self, titulo, texto="Defina a nova senha"):
        """Pede uma senha nova (mascarada, com confirmação). Devolve a senha ou None."""
        def validar(v):
            if len(v["senha"]) < SENHA_MINIMA:
                return f"Use ao menos {SENHA_MINIMA} caracteres."
            if v["senha"] != v["confirmacao"]:
                return "As senhas não conferem."
            return None

        resposta = self._dialogo(titulo, texto, [
            ("senha", "Nova senha", "", True), ("confirmacao", "Repita a nova senha", "", True),
        ], validar)
        return resposta["senha"] if resposta else None


class AppPDV(_Estilo, ctk.CTk):
    def __init__(self, usuario):
        super().__init__()
        self._fontes = {}
        self.usuario = usuario
        self.eh_master = usuario.get("papel") == "master"
        self.title("PDV Próprio")
        self.geometry("1280x780")
        self.minsize(1100, 680)
        self.configure(fg_color=P["canvas"])
        self.protocol("WM_DELETE_WINDOW", self._fechar)

        self.carrinho = []
        self.produto_sel_id = None
        self.desconto = 0                 # centavos
        self.relogar = False
        self.tela = None
        self._busca_agendada = None
        self._relogio_agendado = None
        self._toast = None
        self._menu = {}
        self._menu_perfil = None
        self._carregar_preferencias()

        self._estilizar_tabelas()
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._montar_barra_lateral()
        self.area = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self.area.grid(row=0, column=1, sticky="nsew")

        # Atalhos do caixa (como no protótipo): F2 busca, F4 finaliza.
        self.bind("<F2>", lambda e: self.tela == "vendas" and self.campo_venda_cod.focus())
        self.bind("<F4>", lambda e: self.tela == "vendas" and self.finalizar_venda())
        self.bind("<F11>", lambda e: self._alternar_tela_cheia())
        self.bind("<Escape>", lambda e: self._fechar_menu_perfil(), add="+")
        self.bind("<Button-1>", self._clique_fora_do_menu, add="+")
        if self.tela_cheia:
            self.attributes("-fullscreen", True)

        self.mostrar_vendas()

    # ---------- Helpers de tela ----------
    def _estilizar_tabelas(self):
        estilo = ttk.Style()
        try:
            estilo.theme_use("default")
        except tk.TclError:
            pass
        estilo.layout("PDV.Treeview", [("Treeview.treearea", {"sticky": "nswe"})])  # sem moldura
        estilo.configure(
            "PDV.Treeview", background=P["surface"], fieldbackground=P["surface"],
            foreground=P["text_soft"], rowheight=self._alvo(round(40 * self._escala), 50), borderwidth=0,
            font=self._fonte_tk(12),
        )
        estilo.configure(
            "PDV.Treeview.Heading", background=P["table_head"], foreground=P["muted"],
            relief="flat", borderwidth=0, font=self._fonte_tk(10, True), padding=(12, 9),
        )
        estilo.map("PDV.Treeview", background=[("selected", P["primary_50"])], foreground=[("selected", P["primary_900"])])
        estilo.map("PDV.Treeview.Heading", background=[("active", P["table_head"])])

    def _tabela(self, parent, colunas, altura=8):
        """Tabela sem moldura + barra de rolagem. colunas: [(chave, título, largura, alinhamento)]."""
        moldura = ctk.CTkFrame(parent, fg_color="transparent")
        moldura.grid_columnconfigure(0, weight=1)
        moldura.grid_rowconfigure(0, weight=1)
        tabela = ttk.Treeview(moldura, columns=[c[0] for c in colunas], show="headings",
                              style="PDV.Treeview", height=altura)
        for chave, titulo, largura, alinhamento in colunas:
            tabela.heading(chave, text=titulo.upper(), anchor=alinhamento)
            tabela.column(chave, width=largura, anchor=alinhamento, minwidth=40)
        tabela.tag_configure("sucesso", foreground=TONS["sucesso"][0])
        tabela.tag_configure("neutro", foreground=P["muted"])
        tabela.tag_configure("perigo", foreground=P["danger"])
        tabela.tag_configure("forte", foreground=P["text"], font=self._fonte_tk(12, True))
        tabela.grid(row=0, column=0, sticky="nsew")
        rolagem = ctk.CTkScrollbar(moldura, command=tabela.yview, width=12,
                                   button_color=P["line"], button_hover_color=P["line_hover"])
        tabela.configure(yscrollcommand=rolagem.set)
        rolagem.grid(row=0, column=1, sticky="ns", padx=(0, 4), pady=4)
        return moldura, tabela

    @staticmethod
    def _preencher(tabela, linhas, vazio=None):
        """linhas: [(valores, tag)] ou [valores]."""
        tabela.delete(*tabela.get_children())
        for linha in linhas or ([(vazio, "neutro")] if vazio else []):
            valores, tag = linha if isinstance(linha, tuple) and len(linha) == 2 and isinstance(linha[0], (list, tuple)) else (linha, "")
            tabela.insert("", tk.END, values=valores, tags=(tag,) if tag else ())

    def _limpar_area(self, tela):
        """Esvazia a área principal, zera o layout e marca o item do menu."""
        for agendado in (self._busca_agendada, self._relogio_agendado):
            if agendado:
                self.after_cancel(agendado)
        self._busca_agendada = self._relogio_agendado = None
        for widget in self.area.winfo_children():
            widget.destroy()
        for i in range(4):
            self.area.grid_rowconfigure(i, weight=0)
            self.area.grid_columnconfigure(i, weight=0)
        self.area.grid_columnconfigure(0, weight=1)
        self.tela = tela
        self._marcar_menu(tela)

    def _pagina(self, rolavel=False):
        """Frame da página (padding 24). Rolável para formulários longos."""
        self.area.grid_rowconfigure(0, weight=1)
        if rolavel:
            pagina = ctk.CTkScrollableFrame(self.area, fg_color="transparent", corner_radius=0,
                                            scrollbar_button_color=P["line"], scrollbar_button_hover_color=P["line_hover"])
            pagina.grid(row=0, column=0, sticky="nsew", padx=(24, 8), pady=(24, 0))
        else:
            pagina = ctk.CTkFrame(self.area, fg_color="transparent", corner_radius=0)
            pagina.grid(row=0, column=0, sticky="nsew", padx=24, pady=24)
        pagina.grid_columnconfigure(0, weight=1)
        return pagina

    def _cabecalho(self, parent, sobretitulo, titulo, descricao, acao=None):
        """Cabeçalho de página: sobretítulo, título, descrição e uma ação à direita."""
        topo = ctk.CTkFrame(parent, fg_color="transparent")
        topo.grid_columnconfigure(0, weight=1)
        textos = ctk.CTkFrame(topo, fg_color="transparent")
        textos.grid(row=0, column=0, sticky="w")
        self._rotulo(textos, sobretitulo, 10, True, "primary_700").pack(anchor="w")
        self._rotulo(textos, titulo, 26, True, "primary_950").pack(anchor="w", pady=(0, 2))
        self._rotulo(textos, descricao, 12, cor="text_soft").pack(anchor="w")
        if acao:
            acao(topo).grid(row=0, column=1, sticky="se")
        return topo

    def _cartao_dados(self, parent, titulo, subtitulo="", direita=None):
        """Cartão com cabeçalho (título/subtítulo) e linha; o conteúdo vai na linha 2."""
        card = self._card(parent)
        card.grid_columnconfigure(0, weight=1)
        cab = ctk.CTkFrame(card, fg_color="transparent")
        cab.grid(row=0, column=0, sticky="ew", padx=18, pady=(14, 12))
        cab.grid_columnconfigure(0, weight=1)
        self._rotulo(cab, titulo, 13, True).grid(row=0, column=0, sticky="w")
        card.subtitulo = self._rotulo(cab, subtitulo, 10, cor="muted")
        card.subtitulo.grid(row=1, column=0, sticky="w")
        card.direita = direita(cab) if direita else None
        if card.direita:
            card.direita.grid(row=0, column=1, rowspan=2, sticky="e")
        ctk.CTkFrame(card, height=1, fg_color=P["line_soft"], corner_radius=0).grid(row=1, column=0, sticky="ew", padx=1)
        return card

    def _rodape_tabela(self, card, texto, linha=3):
        rodape = ctk.CTkFrame(card, fg_color="transparent")
        rodape.grid(row=linha, column=0, sticky="ew", padx=18, pady=(8, 12))
        rodape.grid_columnconfigure(0, weight=1)
        self._rotulo(rodape, texto, 10, cor="muted").grid(row=0, column=0, sticky="w")
        contagem = self._rotulo(rodape, "", 10, True, "text_soft")
        contagem.grid(row=0, column=1, sticky="e")
        return contagem

    def _secao(self, parent, titulo, subtitulo, pill=None):
        """Seção de formulário (cartão com título). Devolve (cartão, corpo)."""
        card = self._card(parent)
        cab = ctk.CTkFrame(card, fg_color="transparent")
        cab.pack(fill="x", padx=20, pady=(18, 0))
        textos = ctk.CTkFrame(cab, fg_color="transparent")
        textos.pack(side="left")
        self._rotulo(textos, titulo, 13, True).pack(anchor="w")
        self._rotulo(textos, subtitulo, 10, cor="muted").pack(anchor="w")
        if pill:
            self._pill(cab, *pill).pack(side="right")
        ctk.CTkFrame(card, height=1, fg_color=P["line_soft"]).pack(fill="x", padx=20, pady=14)
        corpo = ctk.CTkFrame(card, fg_color="transparent")
        corpo.pack(fill="x", padx=20, pady=(0, 18))
        return card, corpo

    def _grade_campos(self, corpo, campos, colunas, destino):
        """Distribui campos em grade. campos: [(chave, widget_campo)] -> destino[chave] = entrada."""
        for i in range(colunas):
            corpo.grid_columnconfigure(i, weight=1, uniform="campos")
        for i, (chave, campo) in enumerate(campos):
            campo.grid(row=i // colunas, column=i % colunas, sticky="ew",
                       padx=(0 if i % colunas == 0 else 6, 0 if i % colunas == colunas - 1 else 6), pady=6)
            destino[chave] = campo.entrada

    def _barra_acoes(self, texto):
        """Barra fixa no rodapé (fora da rolagem), como as 'sticky actions' do protótipo."""
        self.area.grid_rowconfigure(1, weight=0)
        barra = ctk.CTkFrame(self.area, fg_color=P["surface"], corner_radius=0, height=68)
        barra.grid(row=1, column=0, sticky="ew")
        ctk.CTkFrame(barra, height=1, fg_color=P["line"], corner_radius=0).pack(fill="x", side="top")
        conteudo = ctk.CTkFrame(barra, fg_color="transparent")
        conteudo.pack(fill="x", padx=24, pady=12)
        barra.texto = self._rotulo(conteudo, texto, 11, cor="muted")
        barra.texto.pack(side="left")
        barra.botoes = ctk.CTkFrame(conteudo, fg_color="transparent")
        barra.botoes.pack(side="right")
        return barra

    def _kpi(self, parent, rotulo, valor, detalhe, destaque=False):
        cor_fundo = P["primary_800"] if destaque else P["surface"]
        card = ctk.CTkFrame(parent, fg_color=cor_fundo, corner_radius=14, border_width=1,
                            border_color=P["primary_800"] if destaque else P["line"], height=112)
        card.pack_propagate(False)
        sub = P["kpi_sub"] if destaque else P["muted"]
        interno = ctk.CTkFrame(card, fg_color="transparent")
        interno.pack(fill="x", padx=18, expand=True)
        self._rotulo(interno, rotulo, 10, True, sub).pack(anchor="w")
        self._rotulo(interno, valor, 22, True, "#ffffff" if destaque else P["primary_900"]).pack(anchor="w", pady=(4, 2))
        self._rotulo(interno, detalhe, 10, cor=sub).pack(anchor="w")
        return card

    def _grade_kpis(self, parent, kpis):
        grade = ctk.CTkFrame(parent, fg_color="transparent")
        for i, kpi in enumerate(kpis):
            grade.grid_columnconfigure(i, weight=1, uniform="kpi")
            self._kpi(grade, *kpi).grid(row=0, column=i, sticky="ew", padx=(0 if i == 0 else 6, 0 if i == len(kpis) - 1 else 6))
        return grade

    def _seletor_imagem(self, parent, atual, titulo, texto, lado, quadrada, icone_vazio):
        """Prévia + "Escolher imagem…" + "Remover", sem gravar nada ainda.

        O estado fica em `quadro.estado` ({atual, nova, remover}); quem salva o formulário
        chama `_gravar_imagem_escolhida` e, depois de gravar no banco, `_descartar_imagem_antiga`.
        """
        quadro = ctk.CTkFrame(parent, fg_color="transparent")
        estado = {"atual": atual, "nova": None, "remover": False}
        quadro.estado = estado
        quadro.pintar = lambda: pintar()
        previa = ctk.CTkLabel(quadro, text="", width=88, height=88, bg_color=P["surface"])
        previa.pack(side="left")
        textos = ctk.CTkFrame(quadro, fg_color="transparent")
        textos.pack(side="left", padx=(16, 0), fill="x", expand=True)
        self._rotulo(textos, titulo, 12, True).pack(anchor="w")
        self._rotulo(textos, texto, 10, cor="muted", justify="left", wraplength=460).pack(anchor="w", pady=(2, 8))
        botoes = ctk.CTkFrame(textos, fg_color="transparent")
        botoes.pack(anchor="w")
        # Logo: encaixada inteira numa placa clara; foto: cortada em quadrado. Cantos já na imagem
        # (corner_radius no CTkLabel alargaria a prévia e empurraria o texto ao lado).
        forma = (88, 88, 14) + ((True,) if quadrada else (False, P["canvas"], 8))

        def pintar():
            if estado["nova"] is not None:
                img = imagens.para_tela(estado["nova"], *forma)
            else:
                img = None if estado["remover"] else imagens.imagem(estado["atual"], *forma)
            if img:
                previa.configure(image=img, fg_color="transparent", corner_radius=0)
            else:
                previa.configure(image=icone(icone_vazio, 30, P["line_hover"]), fg_color=P["canvas"], corner_radius=14)
            escolher_btn.configure(text="Trocar imagem…" if img else "Escolher imagem…")
            if img:
                remover_btn.pack(side="left", padx=(8, 0))
            else:
                remover_btn.pack_forget()

        def escolher():
            origem = filedialog.askopenfilename(title=titulo, filetypes=imagens.TIPOS)
            if not origem:
                return
            try:
                estado["nova"] = imagens.preparar(origem, lado, quadrada)
            except imagens.ImagemInvalida as erro:
                self._avisar(str(erro), erro=True)
                return
            estado["remover"] = False
            pintar()

        def remover():
            estado.update(nova=None, remover=True)
            pintar()

        escolher_btn = self._btn(botoes, "Escolher imagem…", escolher, "secundario", 160, 36)
        escolher_btn.pack(side="left")
        remover_btn = self._btn(botoes, "Remover", remover, "secundario", 100, 36, "trash")
        pintar()
        return quadro

    @staticmethod
    def _gravar_imagem_escolhida(estado, prefixo):
        """Grava a imagem nova do seletor (se houver). Devolve o nome que vai para o banco."""
        if estado["nova"] is not None:
            return imagens.gravar(estado["nova"], prefixo)
        return None if estado["remover"] else estado["atual"]

    @staticmethod
    def _descartar_imagem_antiga(estado, gravada):
        """Depois de salvar: apaga a cópia anterior se ela foi trocada ou removida."""
        if gravada != estado["atual"]:
            imagens.remover(estado["atual"])

    def _avisar(self, texto, erro=False):
        """Toast na base da janela (some sozinho): confirmações e erros que não exigem resposta."""
        if self._toast is not None:
            self._toast.destroy()
        toast = ctk.CTkFrame(self, fg_color=P["danger"] if erro else P["primary_950"], corner_radius=11)
        if erro:
            ctk.CTkLabel(toast, text="!", width=20, height=20, corner_radius=10, fg_color="#ffffff",
                         text_color=P["danger"], font=self._fonte(12, True)).pack(side="left", padx=(16, 8), pady=10)
        else:
            ctk.CTkLabel(toast, text="", image=icone("check", 17, P["accent"])).pack(side="left", padx=(16, 8), pady=10)
        ctk.CTkLabel(toast, text=texto, font=self._fonte(12, True), text_color="#ffffff").pack(side="left", padx=(0, 18))
        toast.place(relx=0.5, rely=1.0, x=111, y=-24, anchor="s")  # centro da área de trabalho
        toast.lift()
        self._toast = toast

        def sumir():
            if self._toast is toast:
                toast.destroy()
                self._toast = None

        self.after(4000 if erro else 2800, sumir)

    # ---------- Barra lateral ----------
    def _montar_barra_lateral(self):
        barra = self.barra = ctk.CTkFrame(self, width=222, corner_radius=0, fg_color=P["primary_950"])
        barra.grid(row=0, column=0, sticky="nsew")
        barra.pack_propagate(False)

        marca = ctk.CTkFrame(barra, fg_color="transparent")
        marca.pack(fill="x", padx=20, pady=(24, 22))
        self.selo_marca = self._selo_marca(marca, 42)
        self.selo_marca.pack(side="left")
        textos = ctk.CTkFrame(marca, fg_color="transparent")
        textos.pack(side="left", padx=(12, 0))
        self.lbl_marca = self._rotulo(textos, "", 15, True, "#ffffff", justify="left", wraplength=130)
        self.lbl_marca.pack(anchor="w")
        self.lbl_marca_sub = self._rotulo(textos, "", 11, cor="brand_sub")
        self.lbl_marca_sub.pack(anchor="w")
        self._atualizar_marca()
        ctk.CTkFrame(barra, height=1, fg_color=P["nav_line"], corner_radius=0).pack(fill="x")

        nav = ctk.CTkFrame(barra, fg_color="transparent")
        nav.pack(fill="x", padx=12, pady=20)
        self._rotulo(nav, "OPERAÇÃO", 10, True, "nav_label").pack(anchor="w", padx=12, pady=(0, 6))
        for chave, texto, nome_icone, comando in [
            ("vendas", "Venda", "cart", self.mostrar_vendas),
            ("produtos", "Produtos", "package", self.mostrar_produtos),
            ("caixa", "Caixa", "wallet", self.mostrar_caixa),
            ("historico", "Histórico", "history", self.mostrar_historico),
            ("relatorio", "Relatórios", "chart", self.mostrar_relatorio),
        ]:
            self._item_menu(nav, chave, texto, nome_icone, comando)
        # Telas sensíveis: só o master vê.
        if self.eh_master:
            self._rotulo(nav, "GESTÃO", 10, True, "nav_label").pack(anchor="w", padx=12, pady=(18, 6))
            self._item_menu(nav, "config", "Configurações", "settings", self.mostrar_config)
            self._item_menu(nav, "usuarios", "Usuários", "users", self.mostrar_usuarios)

        # Rodapé: sincronizar + operador logado.
        rodape = ctk.CTkFrame(barra, fg_color="transparent")
        rodape.pack(side="bottom", fill="x")
        ctk.CTkFrame(rodape, height=1, fg_color=P["nav_line"], corner_radius=0).pack(fill="x")
        self.btn_sync = ctk.CTkButton(
            rodape, text="Sincronizar dados", command=self.sincronizar_agora, height=self._alvo(38), corner_radius=10,
            image=icone("sync", 16, P["primary_950"]), font=self._fonte(12, True), **_ESTILOS_BOTAO["accent"],
        )
        self.btn_sync.pack(fill="x", padx=12, pady=(14, 12))

        # Operador: clicar no nome (ou no avatar) abre o menu de perfil.
        linha = ctk.CTkFrame(rodape, fg_color="transparent")
        linha.pack(fill="x", padx=8, pady=(0, 12))
        operador = self.operador = ctk.CTkFrame(linha, fg_color="transparent", corner_radius=10, cursor="hand2")
        operador.pack(side="left", fill="x", expand=True)
        nome = self.usuario.get("nome") or self.usuario["login"]
        avatar = ctk.CTkLabel(operador, text=_iniciais_nome(nome), width=32, height=32, corner_radius=16,
                              fg_color=P["avatar"], text_color=P["primary_900"], font=self._fonte(10, True))
        avatar.pack(side="left", padx=(6, 0), pady=6)
        textos = ctk.CTkFrame(operador, fg_color="transparent")
        textos.pack(side="left", padx=(10, 0))
        lbl_nome = self._rotulo(textos, nome, 12, True, "#ffffff", anchor="w")
        lbl_nome.pack(anchor="w")
        lbl_papel = self._rotulo(textos, f"{'Master' if self.eh_master else 'Operador'} · Perfil", 10,
                                 cor="brand_sub", anchor="w")
        lbl_papel.pack(anchor="w")
        seta = ctk.CTkLabel(operador, text="", image=icone("chevron", 14, P["nav_text"]), width=16)
        seta.pack(side="right", padx=(0, 6))
        for w in (operador, avatar, textos, lbl_nome, lbl_papel, seta):
            w.bind("<Button-1>", lambda e: self._alternar_menu_perfil())
            w.bind("<Enter>", lambda e: operador.configure(fg_color=P["nav_hover"]))
            w.bind("<Leave>", lambda e: self._sair_do_operador())
        ctk.CTkButton(linha, text="", image=icone("logout", 17, P["nav_text"]), width=self._alvo(30, 44),
                      height=self._alvo(30, 44), corner_radius=8, fg_color="transparent", hover_color=P["nav_hover"],
                      command=self._sair).pack(side="right", padx=(4, 0))

    def _sair_do_operador(self):
        # Como em _hover_menu: passar do avatar para o nome também gera <Leave>.
        sob = self.winfo_containing(*self.winfo_pointerxy())
        if self._menu_perfil is None and not (sob is not None and str(sob).startswith(str(self.operador))):
            self.operador.configure(fg_color="transparent")

    # ---------- Menu de perfil (senha, letra, modo touch, tela cheia, sair) ----------
    def _chave_preferencia(self, nome):
        return f"usuario:{self.usuario['id']}:{nome}"

    def _carregar_preferencias(self):
        """Preferências da tela, salvas por usuário (banco.preferencias)."""
        ler = lambda nome, padrao: banco.ler_preferencia(self._chave_preferencia(nome), padrao)
        self.tamanho_letra = ler("fonte", "M") if ler("fonte", "M") in ESCALAS_FONTE else "M"
        self._escala_fonte = ESCALAS_FONTE[self.tamanho_letra]
        self.touch = ler("touch", "0") == "1"
        self.tela_cheia = ler("tela_cheia", "0") == "1"

    def _alternar_menu_perfil(self):
        if self._menu_perfil is not None:
            self._fechar_menu_perfil()
            return
        menu = self._menu_perfil = ctk.CTkFrame(self, fg_color=P["surface"], corner_radius=14,
                                                border_width=1, border_color=P["line"])
        nome = self.usuario.get("nome") or self.usuario["login"]
        cab = ctk.CTkFrame(menu, fg_color=P["surface"])
        cab.pack(fill="x", padx=16, pady=(14, 10))
        ctk.CTkLabel(cab, text=_iniciais_nome(nome), width=38, height=38, corner_radius=19, fg_color=P["avatar"],
                     text_color=P["primary_900"], font=self._fonte(11, True)).pack(side="left")
        textos = ctk.CTkFrame(cab, fg_color=P["surface"])
        textos.pack(side="left", padx=(10, 0))
        self._rotulo(textos, nome, 13, True).pack(anchor="w")
        self._rotulo(textos, f"{'Master' if self.eh_master else 'Operador'} · {self.usuario['login']}", 10,
                     cor="muted").pack(anchor="w")

        def separador():
            ctk.CTkFrame(menu, height=1, fg_color=P["line_soft"], corner_radius=0).pack(fill="x", padx=1, pady=4)

        def opcao(texto, nome_icone, comando, cor="text"):
            item = ctk.CTkFrame(menu, fg_color=P["surface"], corner_radius=9, height=self._alvo(40), cursor="hand2")
            item.pack(fill="x", padx=8, pady=1)
            item.pack_propagate(False)
            simbolo = ctk.CTkLabel(item, text="", image=icone(nome_icone, 17, P.get(cor, cor)), width=20)
            simbolo.pack(side="left", padx=(10, 10))
            rotulo = self._rotulo(item, texto, 12, True, cor)
            rotulo.pack(side="left")
            def escolher(_evento):
                self._fechar_menu_perfil()
                comando()
                return "break"  # o clique não segue para _clique_fora_do_menu (após Sair a janela já não existe)

            for w in (item, simbolo, rotulo):
                w.bind("<Button-1>", escolher)
                w.bind("<Enter>", lambda e: item.configure(fg_color=P["primary_50"]))
                w.bind("<Leave>", lambda e: item.configure(fg_color=P["surface"]))

        def ajuste(titulo, detalhe, controle):
            linha = ctk.CTkFrame(menu, fg_color=P["surface"])
            linha.pack(fill="x", padx=18, pady=6)
            textos = ctk.CTkFrame(linha, fg_color=P["surface"])
            textos.pack(side="left")
            self._rotulo(textos, titulo, 12, True).pack(anchor="w")
            self._rotulo(textos, detalhe, 10, cor="muted").pack(anchor="w")
            controle(linha).pack(side="right", padx=(16, 0))

        separador()
        opcao("Trocar senha", "lock", self._trocar_minha_senha)
        separador()
        ajuste("Tamanho da letra", "Pequena, média ou grande", self._seletor_letra)
        ajuste("Modo touch", "Botões e alvos maiores", lambda pai: self._interruptor(pai, self.touch, self._alternar_touch))
        ajuste("Tela cheia", "Também pela tecla F11",
               lambda pai: self._interruptor(pai, self.tela_cheia, self._alternar_tela_cheia))
        separador()
        opcao("Sair", "logout", self._sair, "danger")
        ctk.CTkFrame(menu, height=6, fg_color=P["surface"]).pack()

        self.update_idletasks()
        # Abre para cima, logo acima do operador; fica por cima da barra e da tela.
        altura_rodape = self.winfo_height() - self.operador.winfo_rooty() + self.winfo_rooty()
        menu.place(x=12, rely=1, y=-(altura_rodape + 6), anchor="sw")
        menu.lift()
        self.operador.configure(fg_color=P["nav_hover"])

    def _seletor_letra(self, parent):
        seletor = ctk.CTkSegmentedButton(
            parent, values=list(ESCALAS_FONTE), command=self._mudar_letra, width=110, height=self._alvo(30, 40),
            font=self._fonte(11, True), fg_color=P["canvas"], selected_color=P["accent"],
            selected_hover_color=P["accent_hover"], unselected_color=P["canvas"], unselected_hover_color=P["line_soft"],
            text_color=P["primary_950"], corner_radius=8)
        seletor.set(self.tamanho_letra)
        return seletor

    def _interruptor(self, parent, ligado, comando):
        chave = ctk.CTkSwitch(parent, text="", width=46, switch_width=40, switch_height=22, command=comando,
                              progress_color=P["accent"], button_color=P["primary_900"],
                              button_hover_color=P["primary_950"], fg_color=P["line"])
        (chave.select if ligado else chave.deselect)()
        return chave

    def _fechar_menu_perfil(self):
        if self._menu_perfil is not None:
            self._menu_perfil.destroy()
            self._menu_perfil = None
            if self.operador.winfo_exists():
                self.operador.configure(fg_color="transparent")

    def _clique_fora_do_menu(self, evento):
        """Clique em qualquer lugar fora do menu (e fora do operador, que alterna) fecha o menu."""
        if self._menu_perfil is None:
            return
        alvo = str(evento.widget)
        if not (alvo.startswith(str(self._menu_perfil)) or alvo.startswith(str(self.operador))):
            self._fechar_menu_perfil()

    def _mudar_letra(self, tamanho):
        if tamanho == self.tamanho_letra:
            return
        banco.salvar_preferencia(self._chave_preferencia("fonte"), tamanho)
        self.tamanho_letra, self._escala_fonte = tamanho, ESCALAS_FONTE[tamanho]
        self.after(1, self._reaplicar_visual)  # fora do clique: o seletor é destruído ao refazer o menu

    def _alternar_touch(self):
        self.touch = not self.touch
        banco.salvar_preferencia(self._chave_preferencia("touch"), "1" if self.touch else "0")
        self.after(1, self._reaplicar_visual)

    def _alternar_tela_cheia(self):
        self.tela_cheia = not self.tela_cheia
        banco.salvar_preferencia(self._chave_preferencia("tela_cheia"), "1" if self.tela_cheia else "0")
        self.attributes("-fullscreen", self.tela_cheia)
        if self._menu_perfil is not None:  # F11 com o menu aberto: redesenha o interruptor
            self.after(1, lambda: (self._fechar_menu_perfil(), self._alternar_menu_perfil()))

    def _reaplicar_visual(self):
        """Letra/modo touch mudaram: refaz a barra lateral e a tela atual, mantendo o carrinho.

        Um formulário de produto aberto é recarregado do banco (o que não foi salvo se perde).
        """
        self._fechar_menu_perfil()
        self._estilizar_tabelas()
        self.barra.destroy()
        self._menu = {}
        self._montar_barra_lateral()
        tela, carrinho, desconto = self.tela, self.carrinho, self.desconto
        form_aberto = tela == "produtos" and getattr(self, "pf", None) and self.pf["descricao"].winfo_exists()
        if tela == "vendas":
            self.mostrar_vendas()
            self.carrinho, self.desconto = carrinho, desconto
            self._redesenhar_carrinho()
        elif form_aberto:
            self.mostrar_form_produto(self.produto_sel_id)
        else:
            {"produtos": self.mostrar_produtos, "caixa": self.mostrar_caixa, "historico": self.mostrar_historico,
             "relatorio": self.mostrar_relatorio, "config": self.mostrar_config,
             "usuarios": self.mostrar_usuarios}[tela]()
        self._alternar_menu_perfil()  # reabre o menu: o operador vê o efeito e pode ajustar de novo

    def _atualizar_marca(self):
        """Mostra a logo e o nome fantasia da loja (Configurações) no lugar da marca genérica."""
        self._pintar_selo(self.selo_marca, 42)
        loja = _nome_loja()
        self.lbl_marca.configure(text=loja or "PDV Próprio")
        self.lbl_marca_sub.configure(text="PDV Próprio" if loja else "Ponto de venda")
        self.title(f"{loja} — PDV Próprio" if loja else "PDV Próprio")

    def _item_menu(self, parent, chave, texto, nome_icone, comando):
        item = ctk.CTkFrame(parent, height=self._alvo(42), corner_radius=10, fg_color="transparent", cursor="hand2")
        item.pack(fill="x", pady=1)
        item.pack_propagate(False)
        faixa = ctk.CTkFrame(item, width=3, height=22, corner_radius=2, fg_color="transparent")
        faixa.place(x=0, rely=0.5, anchor="w")
        simbolo = ctk.CTkLabel(item, text="", image=icone(nome_icone, 18, P["nav_text"]), width=20)
        simbolo.pack(side="left", padx=(13, 11))
        rotulo = ctk.CTkLabel(item, text=texto, font=self._fonte(13, True), text_color=P["nav_text"])
        rotulo.pack(side="left")
        seta = ctk.CTkLabel(item, text="", width=16)
        seta.pack(side="right", padx=10)
        for widget in (item, simbolo, rotulo, seta):
            widget.bind("<Button-1>", lambda e: comando())
            widget.bind("<Enter>", lambda e: self._hover_menu(chave, True))
            widget.bind("<Leave>", lambda e: self._hover_menu(chave, False))
        self._menu[chave] = dict(item=item, faixa=faixa, simbolo=simbolo, rotulo=rotulo, seta=seta, icone=nome_icone)

    def _hover_menu(self, chave, dentro):
        if chave == self.tela:
            return
        item = self._menu[chave]["item"]
        if not dentro:
            # Mover o mouse entre ícone e texto também gera <Leave>: só apaga se saiu do item.
            sob = self.winfo_containing(*self.winfo_pointerxy())
            if sob is not None and str(sob).startswith(str(item)):
                return
        item.configure(fg_color=P["nav_hover"] if dentro else "transparent")

    def _marcar_menu(self, tela):
        for chave, m in self._menu.items():
            ativo = chave == tela
            cor = "#ffffff" if ativo else P["nav_text"]
            m["item"].configure(fg_color=P["primary_800"] if ativo else "transparent")
            m["faixa"].configure(fg_color=P["accent"] if ativo else "transparent")
            m["simbolo"].configure(image=icone(m["icone"], 18, cor))
            m["rotulo"].configure(text_color=cor)
            m["seta"].configure(image=icone("chevron" if ativo else None, 15, cor))

    def _trocar_minha_senha(self):
        nova = self._pedir_senha("Trocar senha")
        if nova:
            banco.alterar_senha_usuario(self.usuario["id"], nova)
            self._avisar("Sua senha foi alterada")

    def _sair(self):
        self.relogar = True  # iniciar() reabre a tela de login
        self._fechar()

    def sincronizar_agora(self):
        pendentes = banco.contar_pendentes()
        if not any(pendentes.values()):
            self._avisar("Tudo sincronizado — nada pendente para enviar")
            return
        # A rede pode demorar: roda em segundo plano para a tela não travar.
        self.btn_sync.configure(state="disabled", text="Sincronizando…")
        resultado = {}

        def trabalho():
            try:
                resultado["ok"] = sync.sincronizar()
            except Exception as erro:
                resultado["erro"] = erro

        tarefa = threading.Thread(target=trabalho, daemon=True)
        tarefa.start()
        self._aguardar_sync(tarefa, resultado)

    def _aguardar_sync(self, tarefa, resultado):
        if tarefa.is_alive():
            self.after(150, self._aguardar_sync, tarefa, resultado)
            return
        self.btn_sync.configure(state="normal", text="Sincronizar dados")
        erro = resultado.get("erro")
        if isinstance(erro, urllib.error.HTTPError):
            messagebox.showerror("Sincronização", f"O servidor recusou o envio (HTTP {erro.code}).")
        elif isinstance(erro, OSError):  # inclui URLError: sem rede / servidor fora
            messagebox.showwarning(
                "Servidor indisponível",
                "Não foi possível conectar ao servidor central.\n"
                "Os registros continuam pendentes e serão enviados depois.",
            )
        elif erro:
            messagebox.showerror("Sincronização", f"Falha ao sincronizar.\n{erro}")
        else:
            enviado = resultado["ok"]
            self.btn_sync.configure(text="Tudo sincronizado", image=icone("check", 16, P["primary_950"]))
            self.after(2000, lambda: self.btn_sync.configure(
                text="Sincronizar dados", image=icone("sync", 16, P["primary_950"])))
            self._avisar(f"Enviado(s): {enviado['produtos']} produto(s) e {enviado['vendas']} venda(s)")

    # ==================================================================
    # Tela de Venda  (topo + catálogo em cartões + checkout)
    # ==================================================================
    def mostrar_vendas(self):
        self._limpar_area("vendas")
        self.carrinho = []
        self.desconto = 0
        self.produtos_venda = banco.listar_produtos()
        for p in self.produtos_venda:
            p["_busca"] = p["descricao"].lower()
        # Índices em memória: leitura de código e NFC-e sem ir ao banco.
        self._por_codigo = {p["codigo"]: p for p in self.produtos_venda if p["codigo"]}
        self._por_id = {p["id"]: p for p in self.produtos_venda}
        self._filtro_desenhado = None
        self.categoria_venda = "Todos"

        self.area.grid_rowconfigure(1, weight=1)
        self._topo_venda().grid(row=0, column=0, sticky="ew")

        corpo = ctk.CTkFrame(self.area, fg_color="transparent")
        corpo.grid(row=1, column=0, sticky="nsew", padx=24, pady=20)
        corpo.grid_columnconfigure(0, weight=1)
        corpo.grid_rowconfigure(0, weight=1)
        self._montar_catalogo(corpo).grid(row=0, column=0, sticky="nsew", padx=(0, 18))
        self._montar_checkout(corpo).grid(row=0, column=1, sticky="nsew")

        self.campo_venda_cod.focus()
        self._desenhar_catalogo()
        self._redesenhar_carrinho()

    def _topo_venda(self):
        quadro = ctk.CTkFrame(self.area, fg_color=P["topbar"], corner_radius=0)
        topo = ctk.CTkFrame(quadro, fg_color="transparent", height=92)
        topo.pack(fill="x", padx=24)
        topo.pack_propagate(False)
        ctk.CTkFrame(quadro, height=1, fg_color=P["line"], corner_radius=0).pack(fill="x")

        esquerda = ctk.CTkFrame(topo, fg_color="transparent")
        esquerda.pack(side="left", pady=16)
        status = ctk.CTkFrame(esquerda, fg_color="transparent")
        status.pack(anchor="w")
        aberto = banco.sessao_aberta() is not None
        self._rotulo(status, "●", 10, cor=P["status_ok"] if aberto else P["danger"]).pack(side="left")
        self._rotulo(status, " Caixa aberto" if aberto else " Caixa fechado", 11, True, "text_soft").pack(side="left")
        self._rotulo(status, "  •  ", 11, cor="#b6c3be").pack(side="left")
        self.lbl_num_venda = self._rotulo(status, "", 11, True, "text_soft")
        self.lbl_num_venda.pack(side="left")
        self._rotulo(esquerda, "Nova venda", 26, True, "primary_950").pack(anchor="w")
        self._atualizar_numero_venda()

        direita = ctk.CTkFrame(topo, fg_color="transparent")
        direita.pack(side="right")
        hoje = date.today()
        datas = ctk.CTkFrame(direita, fg_color="transparent")
        datas.pack(side="left", padx=(0, 16))
        self._rotulo(datas, DIAS_SEMANA[hoje.weekday()], 10, cor="muted").pack(anchor="e")
        self._rotulo(datas, f"{hoje.day} de {MESES[hoje.month - 1]}", 11, True, "text_soft").pack(anchor="e")
        ctk.CTkFrame(direita, width=1, height=36, fg_color=P["line"]).pack(side="left")
        self.lbl_relogio = self._rotulo(direita, "", 24, True, "primary_900")
        self.lbl_relogio.pack(side="left", padx=(16, 0))
        self._atualizar_relogio()
        return quadro

    def _atualizar_numero_venda(self):
        self.lbl_num_venda.configure(text=f"Venda #{banco.proximo_numero_venda()}")

    def _atualizar_relogio(self):
        self.lbl_relogio.configure(text=datetime.now().strftime("%H:%M"))
        self._relogio_agendado = self.after(15000, self._atualizar_relogio)

    def _montar_catalogo(self, parent):
        catalogo = ctk.CTkFrame(parent, fg_color="transparent")
        catalogo.grid_columnconfigure(0, weight=1)
        catalogo.grid_rowconfigure(2, weight=1)

        linha = ctk.CTkFrame(catalogo, fg_color="transparent")
        linha.grid(row=0, column=0, sticky="ew")
        linha.grid_columnconfigure(0, weight=1)
        caixa = ctk.CTkFrame(linha, fg_color=P["surface"], corner_radius=12, border_width=1, border_color=P["line"], height=48)
        caixa.grid(row=0, column=0, sticky="ew")
        caixa.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(caixa, text="", image=icone("search", 19, P["muted"])).grid(row=0, column=0, padx=(14, 6), pady=4)
        self.campo_venda_cod = ctk.CTkEntry(
            caixa, border_width=0, fg_color=P["surface"], height=38, text_color=P["text"],
            placeholder_text="Busque por nome, código ou leia o código de barras",
            placeholder_text_color="#8c9c96", font=self._fonte(12),
        )
        self.campo_venda_cod.grid(row=0, column=1, sticky="ew", pady=4)
        self.campo_venda_cod.bind("<Return>", lambda e: self.adicionar_por_codigo())
        self.campo_venda_cod.bind("<KeyRelease>", self._agendar_busca)
        ctk.CTkLabel(caixa, text="F2", width=28, height=22, corner_radius=6, fg_color=P["canvas"],
                     text_color=P["muted"], font=self._fonte(10, True)).grid(row=0, column=2, padx=12)
        self._btn(linha, "Adicionar", self.adicionar_por_codigo, width=130, height=48,
                  icone_nome="scan").grid(row=0, column=1, padx=(10, 0))

        cab = ctk.CTkFrame(catalogo, fg_color="transparent")
        cab.grid(row=1, column=0, sticky="ew", pady=(14, 10))
        self.abas_categoria = ctk.CTkFrame(cab, fg_color="transparent")
        self.abas_categoria.pack(side="left")
        self.botoes_categoria = {}
        for nome in ["Todos", *banco.listar_categorias()][:9]:
            b = ctk.CTkButton(self.abas_categoria, text=nome, width=10, height=self._alvo(32, 44), corner_radius=9,
                              font=self._fonte(11, True), command=lambda n=nome: self._selecionar_categoria(n))
            b.pack(side="left", padx=(0, 5))
            self.botoes_categoria[nome] = b
        self.lbl_qtd_catalogo = self._rotulo(cab, "", 10, cor="muted")
        self.lbl_qtd_catalogo.pack(side="right")
        self._pintar_categorias()

        self.grade = ctk.CTkScrollableFrame(catalogo, fg_color="transparent", corner_radius=0,
                                            scrollbar_button_color=P["line"], scrollbar_button_hover_color=P["line_hover"])
        self.grade.grid(row=2, column=0, sticky="nsew")
        self._colunas_catalogo = COLUNAS_CATALOGO[0]
        self._configurar_colunas()
        # Janela maior = mais colunas (3 a 5), sem cartões esticados demais.
        catalogo.bind("<Configure>", self._ajustar_colunas)
        return catalogo

    def _configurar_colunas(self):
        for i in range(COLUNAS_CATALOGO[1]):
            ativa = i < self._colunas_catalogo
            self.grade.grid_columnconfigure(i, weight=1 if ativa else 0, uniform="cards" if ativa else "")

    def _ajustar_colunas(self, evento):
        minimo, maximo = COLUNAS_CATALOGO
        colunas = max(minimo, min(maximo, evento.width // round(LARGURA_CARTAO * self._escala)))
        if colunas != self._colunas_catalogo:
            self._colunas_catalogo = colunas
            self._configurar_colunas()
            self._filtro_desenhado = None  # força redesenhar com o novo número de colunas
            self._desenhar_catalogo(self.campo_venda_cod.get())

    def _pintar_categorias(self):
        for nome, b in self.botoes_categoria.items():
            if nome == self.categoria_venda:
                b.configure(fg_color=P["surface"], hover_color=P["surface"], text_color=P["primary_900"],
                            border_width=1, border_color=P["line"])
            else:
                b.configure(fg_color="transparent", hover_color=P["surface"], text_color=P["text_soft"], border_width=0)

    def _selecionar_categoria(self, nome):
        self.categoria_venda = nome
        self._pintar_categorias()
        self._filtro_desenhado = None
        self._desenhar_catalogo(self.campo_venda_cod.get())

    def _agendar_busca(self, _evento=None):
        """Debounce: só redesenha o catálogo quando o operador para de digitar."""
        if self._busca_agendada:
            self.after_cancel(self._busca_agendada)
        self._busca_agendada = self.after(
            ATRASO_BUSCA_MS, lambda: self._desenhar_catalogo(self.campo_venda_cod.get())
        )

    def _filtrar_catalogo(self, filtro):
        termo = filtro.strip().lower()
        prods = self.produtos_venda
        if self.categoria_venda != "Todos":
            prods = [p for p in prods if (p.get("categoria") or "") == self.categoria_venda]
        if termo:
            prods = [p for p in prods if termo in p["_busca"] or (p["codigo"] or "").startswith(filtro.strip())]
        return prods

    def _desenhar_catalogo(self, filtro=""):
        self._busca_agendada = None
        filtro = filtro.strip()
        if filtro == self._filtro_desenhado:
            return  # nada mudou (ex.: setas, Shift): evita recriar os cartões
        self._filtro_desenhado = filtro
        for w in self.grade.winfo_children():
            w.destroy()

        prods = self._filtrar_catalogo(filtro)
        self.lbl_qtd_catalogo.configure(text=f"{len(prods)} produto(s)")
        colunas = self._colunas_catalogo
        if not self.produtos_venda:
            self._catalogo_vazio(
                "package", "Seu catálogo ainda está vazio",
                "Cadastre o primeiro produto para começar a vender.",
                "Cadastrar primeiro produto", self.mostrar_form_produto,
            )
            return
        if not prods:
            onde = f" para “{filtro}”" if filtro else ""
            categoria = f" na categoria {self.categoria_venda}" if self.categoria_venda != "Todos" else ""
            self._catalogo_vazio(
                "search", f"Nenhum produto encontrado{onde}{categoria}",
                "Confira o nome ou o código, ou procure em todas as categorias.",
                "Limpar pesquisa", self._limpar_pesquisa,
            )
            return
        for idx, p in enumerate(prods[:LIMITE_CARTOES]):
            self._cartao_produto(p).grid(row=idx // colunas, column=idx % colunas,
                                         padx=8 if self.touch else 5, pady=8 if self.touch else 5, sticky="nsew")
        if len(prods) > LIMITE_CARTOES:
            self._rotulo(
                self.grade, f"+{len(prods) - LIMITE_CARTOES} produto(s) — refine a busca.", 11, cor="muted"
            ).grid(row=LIMITE_CARTOES // colunas + 1, column=0, columnspan=colunas, pady=10)

    def _catalogo_vazio(self, nome_icone, titulo, texto, acao, comando):
        """Estado vazio do catálogo: explica o que houve e oferece o próximo passo."""
        vazio = ctk.CTkFrame(self.grade, fg_color="transparent")
        vazio.grid(row=0, column=0, columnspan=self._colunas_catalogo, pady=60)
        ctk.CTkLabel(vazio, text="", image=icone(nome_icone, 26, P["primary_700"]), width=56, height=56,
                     corner_radius=18, fg_color=P["primary_50"]).pack()
        self._rotulo(vazio, titulo, 14, True, wraplength=420).pack(pady=(12, 2))
        self._rotulo(vazio, texto, 11, cor="muted").pack()
        self._btn(vazio, acao, comando, "secundario", width=200).pack(pady=(14, 0))

    def _limpar_pesquisa(self):
        self.campo_venda_cod.delete(0, tk.END)
        self.categoria_venda = "Todos"
        self._pintar_categorias()
        self._filtro_desenhado = None
        self._desenhar_catalogo()
        self.campo_venda_cod.focus()

    def _visual_produto(self, parent, produto_id, descricao, foto, lado, tamanho_fonte, fundo=P["surface"]):
        """Foto do produto (cache em imagens.imagem) ou, sem foto/arquivo ilegível, as iniciais coloridas."""
        imagem = imagens.imagem(foto, lado, lado, round(lado / 5))
        if imagem:
            return ctk.CTkLabel(parent, text="", image=imagem, width=lado, height=lado, fg_color=fundo)
        return ctk.CTkLabel(parent, text=_iniciais(descricao), width=lado, height=lado, corner_radius=round(lado / 5),
                            fg_color=CORES_PRODUTO[produto_id % len(CORES_PRODUTO)],
                            text_color=P["primary_900"], font=self._fonte(tamanho_fonte, True))

    def _cartao_produto(self, p):
        card = ctk.CTkFrame(self.grade, fg_color=P["surface"], corner_radius=13, border_width=1,
                            border_color=P["line"], height=round(104 * self._escala) + (12 if self.touch else 0),
                            cursor="hand2")
        card.pack_propagate(False)
        visual = self._visual_produto(card, p["id"], p["descricao"], p.get("foto_arquivo"), 48, 11)
        visual.pack(side="left", padx=(13, 11), pady=13)
        # Textos em tk.Label (leve): o catálogo pode ter dezenas de cartões.
        info = tk.Frame(card, bg=P["surface"])
        info.pack(side="left", fill="both", expand=True, pady=14, padx=(0, 10))
        nome = tk.Label(info, text=p["descricao"], bg=P["surface"], fg=P["text"], font=self._fonte_tk(12, True),
                        anchor="w", justify="left", wraplength=135)
        nome.pack(anchor="w", fill="x")
        # Quebra o nome na largura real do cartão (muda com as colunas e com a letra P/M/G).
        info.bind("<Configure>", lambda e: nome.configure(wraplength=max(60, e.width - 2)))
        categoria = tk.Label(info, text=p.get("categoria") or "Sem categoria", bg=P["surface"], fg=P["muted"],
                             font=self._fonte_tk(10), anchor="w")
        categoria.pack(anchor="w", pady=(1, 4))
        preco = tk.Label(info, text=_reais(p["preco_centavos"]), bg=P["surface"], fg=P["primary_800"],
                         font=self._fonte_tk(13, True), anchor="w")
        preco.pack(anchor="w")
        for w in (card, visual, info, nome, categoria, preco):
            w.bind("<Button-1>", lambda e, pr=p: self._adicionar_ao_carrinho(pr))
            w.bind("<Enter>", lambda e: card.configure(border_color=P["line_hover"]))
            w.bind("<Leave>", lambda e: card.configure(border_color=P["line"]))
        return card

    def _montar_checkout(self, parent):
        checkout = self._card(parent, width=370, corner_radius=16)
        checkout.grid_propagate(False)
        checkout.grid_columnconfigure(0, weight=1)
        checkout.grid_rowconfigure(1, weight=1)

        cab = ctk.CTkFrame(checkout, fg_color="transparent")
        cab.grid(row=0, column=0, sticky="ew", padx=18, pady=(16, 6))
        textos = ctk.CTkFrame(cab, fg_color="transparent")
        textos.pack(side="left")
        self._rotulo(textos, "Venda atual", 16, True).pack(anchor="w")
        self.lbl_itens = self._rotulo(textos, "", 10, cor="muted")
        self.lbl_itens.pack(anchor="w")
        self.link_limpar = self._link(cab, "Limpar", self._limpar_carrinho)

        self.lista_carrinho = ctk.CTkScrollableFrame(checkout, fg_color="transparent", corner_radius=0,
                                                     scrollbar_button_color=P["line"],
                                                     scrollbar_button_hover_color=P["line_hover"])
        self.lista_carrinho.grid(row=1, column=0, sticky="nsew", padx=8)
        self.lista_carrinho.grid_columnconfigure(0, weight=1)

        ctk.CTkFrame(checkout, height=1, fg_color=P["line_soft"], corner_radius=0).grid(row=2, column=0, sticky="ew", padx=1)
        # A forma de pagamento e o troco ficam na janela de pagamento (F4): aqui só os totais.
        rodape = ctk.CTkFrame(checkout, fg_color="transparent")
        rodape.grid(row=3, column=0, sticky="ew", padx=16, pady=(10, 12))
        rodape.grid_columnconfigure(0, weight=1)

        totais = ctk.CTkFrame(rodape, fg_color="transparent")
        totais.grid(row=2, column=0, sticky="ew")
        totais.grid_columnconfigure(0, weight=1)
        self._rotulo(totais, "Subtotal", 11, cor="text_soft").grid(row=0, column=0, sticky="w")
        self.label_subtotal = self._rotulo(totais, "", 11, cor="text_soft")
        self.label_subtotal.grid(row=0, column=1, sticky="e")
        self._rotulo(totais, "Descontos", 11, cor="text_soft").grid(row=1, column=0, sticky="w")
        desconto = ctk.CTkFrame(totais, fg_color="transparent")
        desconto.grid(row=1, column=1, sticky="e")
        self.label_desconto = self._rotulo(desconto, "", 11, True, "danger")
        self.label_desconto.pack(side="left")
        self.link_desconto = self._link(desconto, "Adicionar", self._alternar_desconto)
        self.link_desconto.pack(side="left")
        self._rotulo(totais, "Tributos aproximados", 10, cor="muted").grid(row=2, column=0, sticky="w")
        self.label_tributos = self._rotulo(totais, "", 10, cor="muted")
        self.label_tributos.grid(row=2, column=1, sticky="e")

        ctk.CTkFrame(rodape, height=1, fg_color=P["line"]).grid(row=3, column=0, sticky="ew", pady=8)
        total = ctk.CTkFrame(rodape, fg_color="transparent")
        total.grid(row=4, column=0, sticky="ew", pady=(0, 10))
        self._rotulo(total, "Total", 13, True).pack(side="left", anchor="s", pady=(0, 6))
        self.label_total = self._rotulo(total, "", 30, True, "primary_900")
        self.label_total.pack(side="right")

        self.btn_finalizar = self._btn(rodape, "Ir para o pagamento      F4", self.finalizar_venda, height=48)
        self.btn_finalizar.grid(row=5, column=0, sticky="ew")
        self._btn(rodape, "Emitir NFC-e", self._emitir_nfce, "secundario", height=34,
                  icone_nome="receipt").grid(row=6, column=0, sticky="ew", pady=(6, 0))
        self._rotulo(rodape, "Na próxima tela você escolhe a forma de pagamento e vê o troco.", 10,
                     cor="muted", wraplength=320).grid(row=7, column=0, pady=(8, 0))
        return checkout

    def _adicionar_ao_carrinho(self, produto):
        item = next((i for i in self.carrinho if i["produto_id"] == produto["id"]), None)
        if item:
            item["quantidade"] += 1
        else:
            self.carrinho.append({
                "produto_id": produto["id"],
                "descricao": produto["descricao"],
                "unidade": (produto.get("unidade") or "UN").upper(),
                "quantidade": 1,
                "preco_unit_centavos": produto["preco_centavos"],
                "aliquota_aprox": produto.get("aliquota_aprox") or 0,
                "foto_arquivo": produto.get("foto_arquivo"),
            })
        self._redesenhar_carrinho()

    def adicionar_por_codigo(self):
        """Enter/Adicionar: código de barras exato; senão, o 1º produto da busca."""
        texto = self.campo_venda_cod.get().strip()
        if not texto:
            return
        produto = self._por_codigo.get(texto)
        if produto is None:
            encontrados = self._filtrar_catalogo(texto)
            produto = encontrados[0] if encontrados else None
        if produto:
            self._adicionar_ao_carrinho(produto)
            self.campo_venda_cod.delete(0, tk.END)
            self._desenhar_catalogo()
        else:
            # Antes era só um bip: o operador não sabia o que tinha acontecido.
            self.bell()
            self._avisar(f"Nenhum produto com o código ou nome “{texto}”. Confira ou cadastre o produto.", erro=True)
            self.campo_venda_cod.select_range(0, tk.END)  # a próxima leitura substitui o texto
        self.campo_venda_cod.focus()

    def _passo(self, item):
        return 0.5 if item["unidade"] in UNIDADES_FRACIONADAS else 1

    def _alterar_qtd(self, item, delta):
        item["quantidade"] = round(item["quantidade"] + delta, 3)
        if item["quantidade"] <= 0:
            self.carrinho.remove(item)
        self._redesenhar_carrinho()

    def _digitar_qtd(self, item):
        def validar(v):
            try:
                if float(v["qtd"].replace(",", ".")) <= 0:
                    return "Informe uma quantidade maior que zero."
            except ValueError:
                return "Use um número, ex: 1,250."
            return None

        resposta = self._dialogo("Quantidade", item["descricao"],
                                 [("qtd", f"Quantidade ({item['unidade']})", _qtd(item["quantidade"]), False)], validar)
        if resposta:
            item["quantidade"] = float(resposta["qtd"].replace(",", "."))
            self._redesenhar_carrinho()

    def remover_item(self, item):
        self.carrinho.remove(item)
        self._redesenhar_carrinho()

    def _limpar_carrinho(self):
        self.carrinho = []
        self.desconto = 0
        self._redesenhar_carrinho()

    def _subtotal(self):
        return sum(banco.subtotal_centavos(i) for i in self.carrinho)

    def _total_atual(self):
        return self._subtotal() - min(self.desconto, self._subtotal())

    def _redesenhar_carrinho(self):
        for w in self.lista_carrinho.winfo_children():
            w.destroy()

        if not self.carrinho:
            vazio = ctk.CTkFrame(self.lista_carrinho, fg_color="transparent")
            vazio.grid(row=0, column=0, pady=18)
            ctk.CTkLabel(vazio, text="", image=icone("cart", 26, P["primary_700"]), width=52, height=52,
                         corner_radius=17, fg_color=P["primary_50"]).pack()
            self._rotulo(vazio, "Seu carrinho está vazio", 13, True).pack(pady=(10, 2))
            self._rotulo(vazio, "Selecione um produto ao lado\npara começar a venda.", 11, cor="muted").pack()
            self.desconto = 0

        subtotal = tributos = 0
        for idx, item in enumerate(self.carrinho):
            sub = banco.subtotal_centavos(item)
            subtotal += sub
            # Lei da Transparência: valor aproximado dos tributos sobre o total.
            tributos += round(sub * item["aliquota_aprox"] / 100)
            self._linha_carrinho(idx, item, sub)

        desconto = min(self.desconto, subtotal)
        total = subtotal - desconto
        if subtotal:
            tributos = round(tributos * total / subtotal)  # o desconto também reduz os tributos

        qtd = sum(i["quantidade"] for i in self.carrinho)
        self.lbl_itens.configure(text=f"{_qtd(qtd)} {'item adicionado' if qtd == 1 else 'itens adicionados'}")
        if self.carrinho:
            self.link_limpar.pack(side="right")
        else:
            self.link_limpar.pack_forget()
        self.label_subtotal.configure(text=_reais(subtotal))
        self.label_desconto.configure(text=f"− {_reais(desconto)}  " if desconto else "")
        self.link_desconto.configure(text="Remover" if desconto else "Adicionar")
        self.label_tributos.configure(text=_reais(tributos))
        self.label_total.configure(text=_reais(total))
        self.btn_finalizar.configure(state="normal" if self.carrinho else "disabled",
                                     fg_color=P["primary_900"] if self.carrinho else "#9fb3ab")

    def _linha_carrinho(self, idx, item, sub):
        linha = ctk.CTkFrame(self.lista_carrinho, fg_color="#ffffff", corner_radius=12,
                             border_width=1, border_color=P["line_soft"])
        linha.grid(row=idx, column=0, sticky="ew", pady=4, padx=2)
        linha.grid_columnconfigure(1, weight=1)
        self._visual_produto(linha, item["produto_id"], item["descricao"], item.get("foto_arquivo"), 44, 10,
                             fundo="#ffffff").grid(row=0, column=0, rowspan=3, padx=(10, 10), pady=10, sticky="n")
        tk.Label(linha, text=item["descricao"], bg="#ffffff", fg=P["text"], font=self._fonte_tk(12, True),
                 anchor="w", justify="left", wraplength=200).grid(row=0, column=1, sticky="w", pady=(10, 0))
        tk.Label(linha, text=f"{_reais(item['preco_unit_centavos'])} / {item['unidade'].lower()}", bg="#ffffff", fg=P["muted"],
                 font=self._fonte_tk(10), anchor="w").grid(row=1, column=1, sticky="w")
        lixeira = 40 if self.touch else 26
        ctk.CTkButton(linha, text="", image=icone("trash", 15, P["muted"]), width=lixeira, height=lixeira, corner_radius=7,
                      fg_color="transparent", hover_color=P["danger_soft"],
                      command=lambda: self.remover_item(item)).grid(row=0, column=2, padx=(0, 6), pady=(6, 0), sticky="ne")

        base = ctk.CTkFrame(linha, fg_color="transparent")
        base.grid(row=2, column=1, columnspan=2, sticky="ew", padx=(0, 12), pady=(6, 10))
        stepper = ctk.CTkFrame(base, fg_color=P["primary_50"], corner_radius=7, border_width=1, border_color=P["line"])
        stepper.pack(side="left")
        passo = self._passo(item)
        # Modo touch: −/+ viram alvos quase quadrados de 44×40, com folga entre eles.
        lado, alto, folga = (44, 40, 3) if self.touch else (26, 24, 1)
        for texto_icone, delta in (("minus", -passo), (None, 0), ("plus", passo)):
            if texto_icone:
                ctk.CTkButton(stepper, text="", image=icone(texto_icone, 16 if self.touch else 14, P["primary_700"]),
                              width=lado, height=alto, corner_radius=6, fg_color="transparent", hover_color=P["accent_soft"],
                              command=lambda d=delta: self._alterar_qtd(item, d)).pack(side="left", padx=folga, pady=1)
            else:
                ctk.CTkButton(stepper, text=_qtd(item["quantidade"]), width=lado + 8, height=alto, corner_radius=0,
                              fg_color="#ffffff", hover_color=P["accent_soft"], text_color=P["text"],
                              font=self._fonte(11, True), command=lambda: self._digitar_qtd(item)).pack(side="left", pady=1)
        self._rotulo(base, _reais(sub), 12, True, "primary_800").pack(side="right")

    def _alternar_desconto(self):
        if self.desconto:
            self.desconto = 0
            self._redesenhar_carrinho()
            return
        subtotal = self._subtotal()
        if not subtotal:
            messagebox.showinfo("Desconto", "Adicione produtos antes de dar desconto.")
            return

        def converter(texto):
            texto = texto.strip()
            if texto.endswith("%"):
                return round(subtotal * float(texto[:-1].replace(",", ".")) / 100)
            return banco.para_centavos(texto)

        def validar(v):
            try:
                valor = converter(v["valor"])
            except ValueError:
                return "Use um valor (ex: 5,00) ou uma porcentagem (ex: 10%)."
            if valor <= 0:
                return "Informe um desconto maior que zero."
            if valor > subtotal:
                return f"O desconto não pode passar do subtotal ({_reais(subtotal)})."
            return None

        resposta = self._dialogo(
            "Adicionar desconto", f"Subtotal da venda: {_reais(subtotal)}. Informe o desconto em reais ou em %.",
            [("valor", "Desconto (R$ ou %)", "", False)], validar, "Aplicar",
        )
        if resposta:
            self.desconto = converter(resposta["valor"])
            self._redesenhar_carrinho()

    def _dividir_pagamento(self, total, atuais):
        """Pede quanto vai em cada forma. atuais: {forma: centavos}. Devolve [{forma, valor_centavos}] ou None."""
        def validar(v):
            try:
                valores = [_centavos_ou_zero(t) for t in v.values()]
            except ValueError:
                return "Use números, ex: 10,50."
            if any(c < 0 for c in valores):
                return "Os valores não podem ser negativos."
            if sum(valores) != total:
                return f"A soma ({_reais(sum(valores))}) precisa ser igual ao total ({_reais(total)})."
            return None

        resposta = self._dialogo(
            "Dividir pagamento", f"Total da venda: {_reais(total)}. Informe quanto será pago em cada forma.",
            [(forma, f"{forma} (R$)", banco.formatar_reais(atuais[forma]) if atuais.get(forma) else "", False)
             for forma, _ in FORMAS_PAGAMENTO],
            validar, "Aplicar",
        )
        if not resposta:
            return None
        pagamentos = [{"forma": f, "valor_centavos": _centavos_ou_zero(t)} for f, t in resposta.items()]
        return [p for p in pagamentos if p["valor_centavos"] > 0]

    def _emitir_nfce(self):
        if not self.carrinho:
            messagebox.showwarning("Emitir NFC-e", "Carrinho vazio.")
            return
        produtos = [self._por_id[i["produto_id"]] for i in self.carrinho]
        pendencias = nfce.pendencias_emissao(banco.ler_config_fiscal(), produtos)
        if pendencias:
            resumo = "\n".join("• " + p for p in pendencias[:12])
            extra = "" if len(pendencias) <= 12 else f"\n(+{len(pendencias) - 12} outras)"
            messagebox.showwarning("Faltam dados para emitir", "Para emitir a NFC-e, complete:\n\n" + resumo + extra)
            return
        messagebox.showinfo(
            "Pré-emissão OK",
            "Dados completos para NFC-e.\n"
            "Falta integrar o certificado digital (passo 2) para transmitir à SEFAZ.",
        )

    def finalizar_venda(self):
        """F4 / "Ir para o pagamento": abre a janela de pagamento e grava a venda se confirmar."""
        if not self.carrinho:
            return
        total = self._total_atual()
        pagamento = self._janela_pagamento(total)
        if not pagamento:
            self.campo_venda_cod.focus()
            return
        sessao = banco.sessao_aberta()
        try:
            venda_id, total_gravado = banco.registrar_venda(
                self.carrinho, pagamento["pagamentos"], sessao and sessao["id"], self.desconto, pagamento["troco"],
            )
        except Exception as erro:
            messagebox.showerror("Erro", f"Não foi possível registrar a venda.\n{erro}")
            return
        troco = f" · Troco {_reais(pagamento['troco'])}" if pagamento["troco"] else ""
        self._avisar(f"Venda #{venda_id} de {_reais(total_gravado)} concluída{troco}")
        self._limpar_carrinho()
        self._atualizar_numero_venda()
        self.campo_venda_cod.focus()

    def _janela_pagamento(self, total):
        """Janela modal: forma de pagamento, valor recebido e troco.

        Teclado: F1/F2/F3 escolhem a forma, Enter conclui, Esc volta para a venda.
        Devolve {"pagamentos": [{forma, valor_centavos}], "troco": centavos} ou None.
        """
        janela = ctk.CTkToplevel(self)
        janela.title("Pagamento")
        janela.resizable(False, False)
        janela.transient(self)
        janela.configure(fg_color=P["surface"])
        estado = {"pagamentos": [{"forma": "Dinheiro", "valor_centavos": total}], "troco": 0}
        resultado = {}

        corpo = ctk.CTkFrame(janela, fg_color=P["surface"])
        corpo.pack(padx=26, pady=22, fill="both")
        corpo.grid_columnconfigure(0, weight=1)
        qtd = sum(i["quantidade"] for i in self.carrinho)
        self._rotulo(corpo, "Pagamento", 20, True, "primary_950").grid(row=0, column=0, sticky="w")
        self._rotulo(corpo, f"Venda #{banco.proximo_numero_venda()} · {_qtd(qtd)} {'item' if qtd == 1 else 'itens'}",
                     11, cor="muted").grid(row=1, column=0, sticky="w")

        caixa_total = ctk.CTkFrame(corpo, fg_color=P["canvas"], corner_radius=12)
        caixa_total.grid(row=2, column=0, sticky="ew", pady=(14, 16))
        self._rotulo(caixa_total, "Total a pagar", 13, True, "text_soft").pack(side="left", padx=16)
        self._rotulo(caixa_total, _reais(total), 30, True, "primary_900").pack(side="right", padx=16, pady=10)

        cab_formas = ctk.CTkFrame(corpo, fg_color=P["surface"])
        cab_formas.grid(row=3, column=0, sticky="ew", pady=(0, 6))
        self._rotulo(cab_formas, "Como o cliente vai pagar?", 12, True, "text").pack(side="left")
        self._link(cab_formas, "Dividir em mais de uma forma", lambda: dividir()).pack(side="right")
        formas = ctk.CTkFrame(corpo, fg_color=P["surface"])
        formas.grid(row=4, column=0, sticky="ew")
        formas.grid_columnconfigure((0, 1, 2), weight=1, uniform="formas")
        botoes = {}
        for i, (forma, nome_icone) in enumerate(FORMAS_PAGAMENTO):
            b = ctk.CTkButton(formas, text=f"{forma}   F{i + 1}", height=52, corner_radius=11,
                              font=self._fonte(13, True), command=lambda f=forma: escolher(f))
            b.grid(row=0, column=i, sticky="ew", padx=(0 if i == 0 else 4, 0 if i == 2 else 4))
            botoes[forma] = (b, nome_icone)
        lbl_divisao = self._rotulo(corpo, "", 11, True, "primary_800", justify="left")
        lbl_divisao.grid(row=5, column=0, sticky="w", pady=(6, 0))

        # Bloco do dinheiro: valor recebido + troco (some quando não há parte em dinheiro).
        dinheiro = ctk.CTkFrame(corpo, fg_color=P["surface"])
        dinheiro.grid_columnconfigure(0, weight=1)
        self._rotulo(dinheiro, "Valor recebido em dinheiro", 12, True, "text").grid(row=0, column=0, sticky="w", pady=(14, 6))
        recebido = self._entry(dinheiro, "0,00", height=50, font=self._fonte(20, True))
        recebido.grid(row=1, column=0, sticky="ew")
        notas = ctk.CTkFrame(dinheiro, fg_color=P["surface"])
        notas.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        rotulos_notas = [("Valor exato", None)] + [(_reais(n).replace(",00", ""), n) for n in NOTAS]
        for i, (texto, valor) in enumerate(rotulos_notas):
            notas.grid_columnconfigure(i, weight=1)
            ctk.CTkButton(notas, text=texto, height=self._alvo(38), corner_radius=9, font=self._fonte(11, True),
                          fg_color=P["primary_50"], hover_color=P["primary_100"], text_color=P["primary_800"],
                          border_width=1, border_color=P["line"],
                          command=lambda v=valor: definir_recebido(v)).grid(
                row=0, column=i, sticky="ew", padx=(0 if i == 0 else 3, 0))
        caixa_troco = ctk.CTkFrame(dinheiro, corner_radius=12)
        caixa_troco.grid(row=3, column=0, sticky="ew", pady=(12, 0))
        lbl_troco_titulo = self._rotulo(caixa_troco, "", 14, True)
        lbl_troco_titulo.pack(side="left", padx=16)
        lbl_troco = self._rotulo(caixa_troco, "", 32, True)
        lbl_troco.pack(side="right", padx=16, pady=8)

        lbl_outras = self._rotulo(corpo, "", 12, cor="text_soft", justify="left", wraplength=470)

        acoes = ctk.CTkFrame(corpo, fg_color=P["surface"])
        acoes.grid(row=8, column=0, sticky="ew", pady=(20, 0))
        btn_concluir = self._btn(acoes, "Concluir venda   Enter", lambda: concluir(), width=230, height=50)
        btn_concluir.pack(side="right")
        self._btn(acoes, "Voltar   Esc", janela.destroy, "secundario", 130, height=50).pack(side="right", padx=(0, 8))

        def parte_dinheiro():
            return sum(p["valor_centavos"] for p in estado["pagamentos"] if p["forma"] == "Dinheiro")

        def atualizar(_evento=None):
            em_dinheiro = parte_dinheiro()
            dividido = len(estado["pagamentos"]) > 1
            unica = None if dividido else estado["pagamentos"][0]["forma"]
            for forma, (b, nome_icone) in botoes.items():
                ativo = forma == unica
                cor = "#ffffff" if ativo else P["text_soft"]
                b.configure(image=icone(nome_icone, 18, cor), text_color=cor,
                            fg_color=P["primary_800"] if ativo else "#fbfdfc",
                            hover_color=P["primary_900"] if ativo else P["primary_50"],
                            border_width=0 if ativo else 1, border_color=P["line"])
            lbl_divisao.configure(text="Dividido: " + " + ".join(
                f"{p['forma']} {_reais(p['valor_centavos'])}" for p in estado["pagamentos"]) if dividido else "")

            outras = [p for p in estado["pagamentos"] if p["forma"] != "Dinheiro"]
            if outras:
                texto = " e ".join(f"{_reais(p['valor_centavos'])} no {p['forma']}" for p in outras)
                lbl_outras.configure(text=f"Confirme o recebimento de {texto} na maquininha ou no app do banco "
                                          "antes de concluir.")
                # Sem dinheiro, o aviso ocupa o lugar do bloco de troco (linha 6).
                lbl_outras.grid(row=7 if em_dinheiro else 6, column=0, sticky="nw", pady=(14, 0))
            else:
                lbl_outras.grid_remove()

            if not em_dinheiro:
                dinheiro.grid_remove()
                estado["troco"] = 0
                btn_concluir.configure(state="normal", fg_color=P["primary_900"])
                return
            dinheiro.grid(row=6, column=0, sticky="ew")
            try:
                valor = _ler_reais(recebido.get()) if recebido.get().strip() else 0
            except (ValueError, OverflowError):
                valor = None
            if valor is None or valor < em_dinheiro:
                falta = em_dinheiro - (valor or 0)
                caixa_troco.configure(fg_color=P["danger_soft"])
                lbl_troco_titulo.configure(text="Valor inválido" if valor is None else "Falta receber",
                                           text_color=P["danger"])
                lbl_troco.configure(text="—" if valor is None else _reais(falta), text_color=P["danger"])
                estado["troco"] = None
                btn_concluir.configure(state="disabled", fg_color="#9fb3ab")
            else:
                estado["troco"] = valor - em_dinheiro
                caixa_troco.configure(fg_color=P["accent_soft"])
                lbl_troco_titulo.configure(text="Troco", text_color=P["primary_900"])
                lbl_troco.configure(text=_reais(estado["troco"]), text_color=P["primary_900"])
                btn_concluir.configure(state="normal", fg_color=P["primary_900"])

        def definir_recebido(valor):
            recebido.delete(0, tk.END)
            recebido.insert(0, banco.formatar_reais(valor if valor is not None else parte_dinheiro()))
            atualizar()
            recebido.focus()

        def escolher(forma):
            estado["pagamentos"] = [{"forma": forma, "valor_centavos": total}]
            definir_recebido(None)
            recebido.select_range(0, tk.END)

        def dividir():
            janela.grab_release()
            atuais = {p["forma"]: p["valor_centavos"] for p in estado["pagamentos"]}
            pagamentos = self._dividir_pagamento(total, atuais)
            if janela.winfo_exists():
                # Ao fechar o diálogo, o foco voltaria para a janela principal: traz de volta para cá.
                janela.grab_set()
                janela.lift()
                janela.focus_force()
                if pagamentos:
                    estado["pagamentos"] = pagamentos
                definir_recebido(None)
                recebido.select_range(0, tk.END)

        def concluir(_evento=None):
            if estado["troco"] is None:
                recebido.focus()
                recebido.select_range(0, tk.END)
                return
            resultado.update(estado)
            janela.destroy()

        recebido.bind("<KeyRelease>", atualizar)
        for tecla in ("<Return>", "<KP_Enter>"):
            janela.bind(tecla, concluir)
        janela.bind("<Escape>", lambda e: janela.destroy())
        for i, (forma, _) in enumerate(FORMAS_PAGAMENTO):
            janela.bind(f"<F{i + 1}>", lambda e, f=forma: escolher(f))

        escolher("Dinheiro")
        # Trava o tamanho com o bloco de troco visível: trocar para Cartão/Pix não faz a janela "pular".
        janela.update_idletasks()
        corpo.grid_rowconfigure(6, minsize=dinheiro.winfo_reqheight())
        corpo.grid_columnconfigure(0, minsize=corpo.winfo_reqwidth())

        def focar():
            try:
                janela.grab_set()  # modal: bloqueia a janela de trás
            except tk.TclError:
                pass
            recebido.focus()
            recebido.select_range(0, tk.END)

        janela.after(120, focar)
        janela.wait_window()
        return resultado or None

    # ==================================================================
    # Tela de Produtos (pesquisa + formulário)
    # ==================================================================
    def mostrar_produtos(self):
        """Tela de PESQUISA de produtos (filtros + resultados + exportação)."""
        self._limpar_area("produtos")
        self._avancado_visivel = False
        self._produtos_filtrados = []
        pagina = self._pagina()
        pagina.grid_rowconfigure(2, weight=1)

        self._cabecalho(
            pagina, "CATÁLOGO", "Produtos", "Consulte, organize e mantenha o catálogo da loja.",
            lambda p: self._btn(p, "Novo produto", lambda: self.mostrar_form_produto(None), width=150, icone_nome="plus"),
        ).grid(row=0, column=0, sticky="ew", pady=(0, 18))

        filtros = self._card(pagina)
        filtros.grid(row=1, column=0, sticky="ew", pady=(0, 14))
        filtros.grid_columnconfigure(0, weight=2)
        filtros.grid_columnconfigure((1, 2), weight=1)

        busca = ctk.CTkFrame(filtros, fg_color="#ffffff", corner_radius=9, border_width=1, border_color=P["line"], height=40)
        busca.grid(row=0, column=0, sticky="sew", padx=(16, 6), pady=(16, 6))
        busca.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(busca, text="", image=icone("search", 17, P["muted"])).grid(row=0, column=0, padx=(12, 4), pady=2)
        self.flt_texto = ctk.CTkEntry(busca, border_width=0, fg_color="#ffffff", height=34, text_color=P["text"],
                                      placeholder_text="Descrição, código EAN ou interno",
                                      placeholder_text_color="#a0ada8", font=self._fonte(12))
        self.flt_texto.grid(row=0, column=1, sticky="ew", padx=(0, 8), pady=2)
        self.flt_texto.bind("<Return>", lambda e: self._pesquisar_produtos())
        status = self._campo_select(filtros, "Situação", ["Ativos", "Inativos", "Todos"])
        status.grid(row=0, column=1, sticky="ew", padx=6, pady=(16, 6))
        controla = self._campo_select(filtros, "Estoque", ["Todos", "Controla estoque", "Não controla"])
        controla.grid(row=0, column=2, sticky="ew", padx=6, pady=(16, 6))
        self.flt_status, self.flt_controla = status.entrada, controla.entrada
        self._btn(filtros, "Pesquisar", self._pesquisar_produtos, width=120).grid(row=0, column=3, sticky="s", padx=(6, 16), pady=(16, 6))

        # Filtro avançado (escondido por padrão)
        self.adv = ctk.CTkFrame(filtros, fg_color="transparent")
        self.adv.grid(row=1, column=0, columnspan=4, padx=16, pady=(6, 0), sticky="ew")
        self.flt_avancado = {}
        self._grade_campos(self.adv, [
            (chave, self._campo(self.adv, rotulo, f"Filtrar por {rotulo}"))
            for chave, rotulo in [("ncm", "NCM"), ("cfop", "CFOP"), ("cst", "CST / CSOSN"),
                                  ("origem", "Origem"), ("categoria", "Categoria")]
        ], 5, self.flt_avancado)
        self.adv.grid_remove()

        rodape = ctk.CTkFrame(filtros, fg_color="transparent")
        rodape.grid(row=2, column=0, columnspan=4, sticky="ew", padx=12, pady=(4, 12))
        self.link_avancado = self._link(rodape, "Mais filtros", self._toggle_avancado)
        self.link_avancado.pack(side="left")
        self._btn(rodape, "Exportar CSV", self._exportar_produtos, "secundario", 130, 34).pack(side="right", padx=4)

        dados = self._cartao_dados(pagina, "Catálogo de produtos", direita=lambda p: self._pill(p, "Atualizado agora", "neutro"))
        dados.grid(row=2, column=0, sticky="nsew")
        dados.grid_rowconfigure(2, weight=1)
        self.prod_cartao = dados
        moldura, self.tabela_prod = self._tabela(dados, [
            ("id", "ID", 60, "w"), ("codigo", "Código EAN", 140, "w"),
            ("descricao", "Descrição", 300, "w"), ("unidade", "Un.", 60, "w"),
            ("preco", "Preço", 110, "w"), ("estoque", "Estoque", 90, "w"),
            ("ativo", "Situação", 90, "w"),
        ])
        moldura.grid(row=2, column=0, sticky="nsew", padx=1)
        self.tabela_prod.bind("<Double-1>", lambda e: self._editar_produto())
        self.lbl_pag_prod = self._rodape_tabela(dados, "Duplo clique em um produto para editar. O CSV usa o filtro atual (SPED 0200).")

        self._pesquisar_produtos()
        self.flt_texto.focus()

    def _toggle_avancado(self):
        self._avancado_visivel = not self._avancado_visivel
        if self._avancado_visivel:
            self.adv.grid()
            self.link_avancado.configure(text="Ocultar filtros avançados")
        else:
            self.adv.grid_remove()
            self.link_avancado.configure(text="Mais filtros")

    def _coletar_filtros(self):
        filtros = {
            "texto": self.flt_texto.get().strip(),
            "status": self.flt_status.get().lower(),
            "controla": {"Controla estoque": 1, "Não controla": 0}.get(self.flt_controla.get()),
        }
        if self._avancado_visivel:
            filtros.update({chave: campo.get().strip() for chave, campo in self.flt_avancado.items()})
        return filtros

    def _pesquisar_produtos(self):
        self._produtos_filtrados = banco.buscar_produtos(self._coletar_filtros())
        self._preencher(self.tabela_prod, [
            ((
                f"{p['id']:03d}", p.get("codigo") or "—", p["descricao"], p.get("unidade") or "",
                _reais(p["preco_centavos"]),
                _qtd(p.get("estoque") or 0) if p.get("controla_estoque") else "—",
                "● Ativo" if p.get("ativo") else "● Inativo",
            ), "sucesso" if p.get("ativo") else "neutro")
            for p in self._produtos_filtrados
        ], vazio=("", "", "Nenhum produto encontrado", "", "", "", ""))
        n = len(self._produtos_filtrados)
        self.prod_cartao.subtitulo.configure(text=f"{n} produto(s) encontrado(s)")
        self.lbl_pag_prod.configure(text=f"1–{n} de {n}" if n else "0 de 0")

    def _editar_produto(self):
        selecao = self.tabela_prod.selection()
        if selecao:
            valor = self.tabela_prod.item(selecao[0], "values")[0]
            if valor:
                self.mostrar_form_produto(int(valor))

    def _exportar_produtos(self):
        if not self._produtos_filtrados:
            messagebox.showinfo("Exportar", "Faça uma pesquisa primeiro — não há produtos para exportar.")
            return
        caminho = filedialog.asksaveasfilename(
            title="Exportar produtos (CSV)", defaultextension=".csv",
            initialfile="produtos.csv", filetypes=[("CSV", "*.csv")],
        )
        if not caminho:
            return
        try:
            qtd = exportacao.exportar_produtos_csv(caminho, self._produtos_filtrados)
        except OSError as erro:
            messagebox.showerror("Erro", f"Não foi possível exportar.\n{erro}")
            return
        self._avisar(f"{qtd} produto(s) exportado(s)")

    # ---------- Formulário de produto (novo / editar) ----------
    # (chave, rótulo, exemplo). Obrigatórios: os que a NFC-e exige + preço.
    _CAMPOS_BASICOS = [
        ("descricao", "Descrição", "Ex.: Água mineral 500ml"), ("codigo", "Código de barras (EAN)", "789..."),
        ("codigo_interno", "Código interno", "Ex.: 001"), ("categoria", "Categoria", "Ex.: Bebidas"),
        ("unidade", "Unidade", "UN"), ("preco", "Preço de venda", "0,00"),
        ("custo", "Custo", "0,00"), ("estoque", "Estoque atual", "0"),
    ]
    _CAMPOS_FISCAIS = [
        ("ncm", "NCM", "22011000"), ("cest", "CEST", "03.001.00"), ("cfop", "CFOP", "5102"),
        ("origem", "Origem (0-8)", "0"), ("cst", "CST / CSOSN", "102"), ("tipo_item", "Tipo do item", "00"),
        ("aliquota_icms", "ICMS %", "0,00"), ("aliquota_aprox", "Tributos aproximados %", "12,10"),
    ]
    _CAMPOS_NUMERICOS = ("estoque", "aliquota_icms", "aliquota_aprox")

    def mostrar_form_produto(self, produto_id=None):
        self._limpar_area("produtos")
        self.produto_sel_id = produto_id
        pagina = self._pagina(rolavel=True)

        self._cabecalho(
            pagina, "PRODUTOS", "Editar produto" if produto_id else "Novo produto",
            "Mantenha os dados comerciais e fiscais organizados.",
            lambda p: self._btn(p, "Voltar para produtos", self.mostrar_produtos, "secundario", 180),
        ).grid(row=0, column=0, sticky="ew", pady=(0, 18), padx=(0, 14))

        obrigatorios = set(nfce.PRODUTO_OBRIGATORIO) | {"preco"}
        self.pf = {}
        card, corpo = self._secao(pagina, "Dados básicos", "Informações usadas na venda e no controle de estoque.",
                                  ("Dados comerciais", "sucesso"))
        card.grid(row=1, column=0, sticky="ew", pady=(0, 12), padx=(0, 14))
        self._grade_campos(corpo, [
            (chave, self._campo(corpo, rotulo, exemplo, obrigatorio=chave in obrigatorios))
            for chave, rotulo, exemplo in self._CAMPOS_BASICOS
        ], 4, self.pf)
        controle = ctk.CTkFrame(corpo, fg_color=P["canvas"], corner_radius=11, border_width=1, border_color=P["line"])
        controle.grid(row=2, column=0, columnspan=4, sticky="ew", pady=(10, 0))
        self.pf_controla = ctk.CTkCheckBox(controle, text="", width=24, fg_color=P["primary_800"],
                                           hover_color=P["primary_900"], border_color=P["line_hover"], corner_radius=6)
        self.pf_controla.pack(side="left", padx=(14, 4), pady=12)
        textos = ctk.CTkFrame(controle, fg_color=P["canvas"])
        textos.pack(side="left", pady=8)
        self._rotulo(textos, "Controlar estoque", 12, True).pack(anchor="w")
        self._rotulo(textos, "Movimentar o saldo automaticamente a cada venda.", 10, cor="muted").pack(anchor="w")
        self.pf_foto = self._seletor_imagem(
            corpo, None, "Foto do produto",
            "Aparece no catálogo da venda e no carrinho. A imagem é cortada em quadrado pelo centro. "
            "Sem foto, o produto aparece com as iniciais coloridas.",
            imagens.LADO_FOTO, quadrada=True, icone_vazio="package",
        )
        self.pf_foto.grid(row=3, column=0, columnspan=4, sticky="ew", pady=(14, 0))

        card, corpo = self._secao(pagina, "Dados fiscais", "Campos necessários para NFC-e e escrituração fiscal.",
                                  ("NFC-e / SPED", "neutro"))
        card.grid(row=2, column=0, sticky="ew", pady=(0, 18), padx=(0, 14))
        self._grade_campos(corpo, [
            (chave, self._campo(corpo, rotulo, exemplo, obrigatorio=chave in obrigatorios,
                                ajuda=AJUDA_FISCAL.get(chave)))
            for chave, rotulo, exemplo in self._CAMPOS_FISCAIS
        ], 4, self.pf)

        barra = self._barra_acoes("Os campos marcados com * são obrigatórios.")
        self._btn(barra.botoes, "Salvar produto", self._salvar_form, width=150).pack(side="right")
        self._btn(barra.botoes, "Cancelar", self.mostrar_produtos, "secundario", 110).pack(side="right", padx=8)
        if produto_id:
            self._btn(barra.botoes, "Excluir produto", self.excluir_produto, "perigo", 150).pack(side="right")

        if produto_id:
            self._carregar_produto_no_form(produto_id)
        self.pf["descricao"].focus()

    def _marcar_erro(self, chave, titulo, mensagem):
        for campo in self.pf.values():
            campo.configure(border_color=P["line"])
        self.pf[chave].configure(border_color=P["danger"])
        messagebox.showwarning(titulo, mensagem)
        self.pf[chave].focus()

    def _ler_form_produto(self):
        v = {chave: campo.get().strip() for chave, campo in self.pf.items()}

        # Campos obrigatórios (os mesmos que a NFC-e exige)
        for chave, nome in {**nfce.PRODUTO_OBRIGATORIO, "preco": "Preço de venda"}.items():
            if not v[chave]:
                self._marcar_erro(chave, "Campo obrigatório", f"Informe: {nome}.")
                return None

        try:
            preco_centavos = banco.para_centavos(v["preco"])
        except ValueError:
            self._marcar_erro("preco", "Preço inválido", "Preço de venda: use um número, ex: 5,50.")
            return None

        def numero(chave):
            try:
                return float(v[chave].replace(",", ".")) if v[chave] else 0.0
            except ValueError:
                return 0.0

        try:
            custo_centavos = banco.para_centavos(v["custo"]) if v["custo"] else 0
        except ValueError:
            custo_centavos = 0

        dados = {c: v[c] or None for c in ("descricao", "codigo", "codigo_interno", "categoria", "ncm", "cest", "cfop", "cst")}
        dados.update(
            unidade=(v["unidade"] or "UN").upper(),
            tipo_item=v["tipo_item"] or "00",
            origem=v["origem"] or "0",
            preco_centavos=preco_centavos,
            custo_centavos=custo_centavos,
            controla_estoque=1 if self.pf_controla.get() else 0,
            **{c: numero(c) for c in self._CAMPOS_NUMERICOS},
        )
        return dados

    def _salvar_form(self):
        dados = self._ler_form_produto()
        if dados is None:
            return
        foto = self.pf_foto.estado
        try:
            dados["foto_arquivo"] = self._gravar_imagem_escolhida(foto, "produto")
        except OSError as erro:
            messagebox.showerror("Erro", f"Não foi possível guardar a foto.\n{erro}")
            return
        try:
            if self.produto_sel_id is None:
                banco.cadastrar_produto(dados)
            else:
                banco.atualizar_produto(self.produto_sel_id, dados)
        except banco.CodigoDuplicado:
            if dados["foto_arquivo"] != foto["atual"]:
                imagens.remover(dados["foto_arquivo"])  # a cópia nova não chegou ao banco
            self._marcar_erro("codigo", "Código repetido", f"Já existe um produto com o código {dados['codigo']}.")
            return
        self._descartar_imagem_antiga(foto, dados["foto_arquivo"])
        self.mostrar_produtos()
        self._avisar("Produto salvo com sucesso")

    def excluir_produto(self):
        if self.produto_sel_id is None:
            return
        if messagebox.askyesno("Excluir produto", "Deseja mesmo excluir este produto?"):
            banco.inativar_produto(self.produto_sel_id)
            self.mostrar_produtos()
            self._avisar("Produto excluído")

    def _carregar_produto_no_form(self, produto_id):
        produto = banco.obter_produto(produto_id)
        if not produto:
            return
        valores = {chave: produto.get(chave) or "" for chave in self.pf}
        valores["tipo_item"] = produto.get("tipo_item") or "00"
        valores["preco"] = banco.formatar_reais(produto.get("preco_centavos") or 0)
        valores["custo"] = banco.formatar_reais(produto.get("custo_centavos") or 0)
        for chave in self._CAMPOS_NUMERICOS:
            valores[chave] = _qtd(produto[chave]) if produto.get(chave) else ""
        for chave, campo in self.pf.items():
            campo.delete(0, tk.END)
            campo.insert(0, valores[chave])
        (self.pf_controla.select if produto.get("controla_estoque") else self.pf_controla.deselect)()
        self.pf_foto.estado["atual"] = produto.get("foto_arquivo") or None
        self.pf_foto.pintar()

    # ==================================================================
    # Tela de Caixa
    # ==================================================================
    def mostrar_caixa(self):
        self._limpar_area("caixa")
        sessao = banco.sessao_aberta()
        if sessao is None:
            self._tela_abrir_caixa()
        else:
            self._tela_caixa_aberto(sessao)

    def _tela_abrir_caixa(self):
        pagina = self._pagina()
        self._cabecalho(pagina, "OPERAÇÃO", "Caixa", "Abra o caixa para começar a registrar vendas.").grid(
            row=0, column=0, sticky="ew")
        card = self._card(pagina, width=540)
        card.grid(row=1, column=0, pady=60)
        corpo = ctk.CTkFrame(card, fg_color="transparent")
        corpo.pack(padx=32, pady=30)
        ctk.CTkLabel(corpo, text="", image=icone("wallet", 27, P["primary_700"]), width=58, height=58,
                     corner_radius=18, fg_color=P["primary_50"]).pack()
        self._rotulo(corpo, "Caixa fechado", 18, True).pack(pady=(14, 2))
        self._rotulo(corpo, "Informe o operador e o fundo de troco para iniciar o turno.", 11, cor="muted").pack()
        campos = ctk.CTkFrame(corpo, fg_color="transparent")
        campos.pack(fill="x", pady=18)
        campos.grid_columnconfigure((0, 1), weight=1, uniform="c")
        operador = self._campo(campos, "Operador", "Nome do operador", self.usuario.get("nome") or self.usuario["login"])
        operador.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        fundo = self._campo(campos, "Fundo de troco (R$)", "Ex.: 100,00")
        fundo.grid(row=0, column=1, sticky="ew", padx=(6, 0))
        self.campo_operador, self.campo_abertura = operador.entrada, fundo.entrada
        self.campo_operador.configure(width=220)
        self.campo_abertura.bind("<Return>", lambda e: self.abrir_caixa())
        self._btn(corpo, "Abrir caixa", self.abrir_caixa, height=44).pack(fill="x")
        self.campo_abertura.focus()

    def abrir_caixa(self):
        operador = self.campo_operador.get().strip() or None
        try:
            abertura = _centavos_ou_zero(self.campo_abertura.get())
        except ValueError:
            messagebox.showwarning("Valor inválido", "Fundo de troco: use um número, ex: 100,00.")
            return
        try:
            banco.abrir_caixa(operador, abertura)
        except banco.CaixaJaAberto:
            messagebox.showwarning("Caixa já aberto", "Já existe um caixa aberto.")
        self.mostrar_caixa()
        self._avisar("Caixa aberto com sucesso")

    def _tela_caixa_aberto(self, sessao):
        pagina = self._pagina()
        pagina.grid_rowconfigure(2, weight=1)
        aberto = datetime.fromisoformat(sessao["aberto_em"])
        self._cabecalho(
            pagina, "OPERAÇÃO", "Caixa", "Acompanhe o movimento e o saldo esperado do turno.",
            lambda p: self._pill(p, f"Caixa aberto desde {aberto:%H:%M}"),
        ).grid(row=0, column=0, sticky="ew", pady=(0, 18))

        r = banco.resumo_caixa(sessao["id"])
        def lancamentos(n):
            return f"{n} lançamento{'s' if n != 1 else ''}"
        self._grade_kpis(pagina, [
            ("Esperado na gaveta", _reais(r["esperado_gaveta"]), "Saldo atual estimado", True),
            ("Vendas do turno", _reais(r["vendas_total"]), f"{r['qtd_vendas']} venda(s) concluída(s)"),
            ("Suprimentos", _reais(r["suprimentos"]), lancamentos(r["qtd_suprimentos"])),
            ("Sangrias", _reais(r["sangrias"]), lancamentos(r["qtd_sangrias"])),
        ]).grid(row=1, column=0, sticky="ew", pady=(0, 14))

        corpo = ctk.CTkFrame(pagina, fg_color="transparent")
        corpo.grid(row=2, column=0, sticky="nsew")
        corpo.grid_columnconfigure(0, weight=1)
        corpo.grid_rowconfigure(0, weight=1)

        operador = sessao["operador"] or "—"
        movs = self._cartao_dados(corpo, "Movimentações recentes", f"Turno de {operador}")
        movs.grid(row=0, column=0, sticky="nsew", padx=(0, 14))
        movs.grid_rowconfigure(2, weight=1)
        moldura, tabela = self._tabela(movs, [
            ("mov", "Movimento", 160, "w"), ("detalhe", "Detalhe", 180, "w"),
            ("hora", "Horário", 90, "w"), ("valor", "Valor", 120, "w"),
        ])
        moldura.grid(row=2, column=0, sticky="nsew", padx=1, pady=(0, 8))
        nomes = {"abertura": "Fundo de troco", "suprimento": "Suprimento", "sangria": "Sangria"}
        linhas = []
        for m in banco.movimentos_sessao(sessao["id"]):
            nome = f"Venda #{m['venda_id']}" if m["tipo"] == "venda" else nomes.get(m["tipo"], m["tipo"])
            detalhe = "Abertura" if m["tipo"] == "abertura" else (m["detalhe"] or operador)
            sinal = "− " if m["tipo"] == "sangria" else "+ "
            linhas.append(((nome, detalhe, m["criado_em"][11:16], sinal + _reais(m["valor_centavos"])),
                           "perigo" if m["tipo"] == "sangria" else ""))
        self._preencher(tabela, linhas)

        resumo = self._card(corpo, width=300)
        resumo.grid(row=0, column=1, sticky="n")
        interno = ctk.CTkFrame(resumo, fg_color="transparent")
        interno.pack(fill="both", padx=20, pady=20)
        self._rotulo(interno, "RESUMO DO TURNO", 10, True, "primary_700").pack(anchor="w")
        self._rotulo(interno, operador, 18, True).pack(anchor="w", pady=(4, 0))
        self._rotulo(interno, f"Aberto em {aberto:%d/%m/%Y} às {aberto:%H:%M}", 10, cor="muted").pack(anchor="w")
        ctk.CTkFrame(interno, height=1, fg_color=P["line_soft"]).pack(fill="x", pady=14)
        for rotulo, valor in [
            ("Abertura", r["abertura"]),
            ("Vendas em dinheiro", r["vendas_dinheiro"]),
            ("Outras formas", r["vendas_total"] - r["vendas_dinheiro"]),
        ]:
            linha = ctk.CTkFrame(interno, fg_color="transparent")
            linha.pack(fill="x", pady=3)
            self._rotulo(linha, rotulo, 11, cor="text_soft").pack(side="left")
            self._rotulo(linha, _reais(valor), 11, True).pack(side="right")
        ctk.CTkFrame(interno, height=1, fg_color=P["line_soft"]).pack(fill="x", pady=14)
        botoes = ctk.CTkFrame(interno, fg_color="transparent")
        botoes.pack(fill="x")
        botoes.grid_columnconfigure((0, 1), weight=1, uniform="b")
        self._btn(botoes, "Suprimento", lambda: self._movimento(sessao, "suprimento"), "secundario", 100, 38).grid(
            row=0, column=0, sticky="ew", padx=(0, 4))
        self._btn(botoes, "Sangria", lambda: self._movimento(sessao, "sangria"), "secundario", 100, 38).grid(
            row=0, column=1, sticky="ew", padx=(4, 0))
        self._btn(interno, "Fechar caixa", lambda: self.fechar_caixa(sessao), "perigo", height=40).pack(fill="x", pady=(8, 0))

    def _movimento(self, sessao, tipo):
        def validar(v):
            try:
                if banco.para_centavos(v["valor"]) <= 0:
                    return "Informe um valor maior que zero."
            except ValueError:
                return "Use um número, ex: 50,00."
            return None

        resposta = self._dialogo(
            tipo.capitalize(),
            "Dinheiro colocado na gaveta." if tipo == "suprimento" else "Dinheiro retirado da gaveta.",
            [("valor", "Valor (R$)", "", False), ("motivo", "Motivo (opcional)", "", False)], validar, "Registrar",
        )
        if resposta:
            banco.registrar_movimento_caixa(sessao["id"], tipo, banco.para_centavos(resposta["valor"]),
                                            resposta["motivo"].strip() or None)
            self.mostrar_caixa()
            self._avisar(f"{tipo.capitalize()} registrado")

    def fechar_caixa(self, sessao):
        esperado = banco.resumo_caixa(sessao["id"])["esperado_gaveta"]

        def validar(v):
            try:
                banco.para_centavos(v["contado"])
            except ValueError:
                return "Use um número, ex: 350,00."
            return None

        resposta = self._dialogo("Fechar caixa", f"Esperado na gaveta: {_reais(esperado)}",
                                 [("contado", "Valor contado (R$)", "", False)], validar, "Fechar caixa")
        if not resposta:
            return
        contado = banco.para_centavos(resposta["contado"])
        banco.fechar_caixa(sessao["id"], contado)
        diferenca = contado - esperado
        if diferenca == 0:
            situacao = "Caixa bateu certo."
        else:
            situacao = f"{'Sobra' if diferenca > 0 else 'Falta'} de {_reais(abs(diferenca))}."
        messagebox.showinfo("Caixa fechado", situacao)
        self.mostrar_caixa()

    # ==================================================================
    # Tela de Histórico de vendas
    # ==================================================================
    def mostrar_historico(self):
        self._limpar_area("historico")
        pagina = self._pagina()
        pagina.grid_rowconfigure(2, weight=1)
        self._cabecalho(
            pagina, "VENDAS", "Histórico de vendas", "Consulte as vendas registradas e seus meios de pagamento.",
            lambda p: self._btn(p, "Exportar CSV", self._exportar_vendas, "secundario", 140),
        ).grid(row=0, column=0, sticky="ew", pady=(0, 18))

        filtros = self._card(pagina)
        filtros.grid(row=1, column=0, sticky="ew", pady=(0, 14))
        filtros.grid_columnconfigure((0, 1, 2), weight=1)
        hoje = date.today()
        inicio = self._campo(filtros, "Período inicial", "dd/mm/aaaa", (hoje - timedelta(days=29)).strftime("%d/%m/%Y"))
        inicio.grid(row=0, column=0, sticky="ew", padx=(16, 6), pady=16)
        fim = self._campo(filtros, "Período final", "dd/mm/aaaa", hoje.strftime("%d/%m/%Y"))
        fim.grid(row=0, column=1, sticky="ew", padx=6, pady=16)
        forma = self._campo_select(filtros, "Pagamento", ["Todas as formas", *(f for f, _ in FORMAS_PAGAMENTO)])
        forma.grid(row=0, column=2, sticky="ew", padx=6, pady=16)
        self.h_inicio, self.h_fim, self.h_forma = inicio.entrada, fim.entrada, forma.entrada
        self._btn(filtros, "Aplicar filtros", self._filtrar_historico, width=140).grid(
            row=0, column=3, sticky="s", padx=(6, 16), pady=16)

        # Atalhos de período: evita digitar datas no dia a dia.
        rapidos = ctk.CTkFrame(filtros, fg_color="transparent")
        rapidos.grid(row=1, column=0, columnspan=4, sticky="w", padx=16, pady=(0, 14))
        self._rotulo(rapidos, "Período rápido:", 11, True, "text_soft").pack(side="left", padx=(0, 8))
        self.h_rapidos = {}
        for nome in self.PERIODOS_RAPIDOS:
            b = ctk.CTkButton(rapidos, text=nome, width=10, height=self._alvo(32, 44), corner_radius=9,
                              font=self._fonte(11, True),
                              command=lambda n=nome: self._periodo_rapido(n))
            b.pack(side="left", padx=(0, 6))
            self.h_rapidos[nome] = b

        def direita(parent):
            quadro = ctk.CTkFrame(parent, fg_color="transparent")
            self._btn(quadro, "Ver itens", self._ver_itens_venda, "secundario", 120, 36, "receipt").pack(side="left", padx=(0, 16))
            quadro.total = self._rotulo(quadro, "", 20, True, "primary_900")
            quadro.total.pack(side="left")
            return quadro

        dados = self._cartao_dados(pagina, "Vendas encontradas", direita=direita)
        dados.grid(row=2, column=0, sticky="nsew")
        dados.grid_rowconfigure(2, weight=1)
        self.h_cartao, self.h_total = dados, dados.direita.total
        moldura, self.h_tabela = self._tabela(dados, [
            ("id", "Venda", 90, "w"), ("data", "Data e hora", 180, "w"),
            ("itens", "Itens", 90, "w"), ("formas", "Pagamento", 200, "w"),
            ("desconto", "Desconto", 110, "w"), ("total", "Total", 120, "w"),
        ])
        moldura.grid(row=2, column=0, sticky="nsew", padx=1)
        for evento in ("<Double-1>", "<Return>", "<KP_Enter>"):
            self.h_tabela.bind(evento, lambda e: self._ver_itens_venda())
        self.h_contagem = self._rodape_tabela(dados, "Vendas concluídas no período, mais recentes primeiro. "
                                                     "Duplo clique abre os itens.")
        self._filtrar_historico()

    # nome: (dias atrás do fim, quantidade de dias)
    PERIODOS_RAPIDOS = {"Hoje": (0, 1), "Ontem": (1, 1), "Últimos 7 dias": (0, 7), "Últimos 30 dias": (0, 30)}

    @staticmethod
    def _datas_periodo(dias_atras, dias):
        fim = date.today() - timedelta(days=dias_atras)
        return fim - timedelta(days=dias - 1), fim

    def _periodo_rapido(self, nome):
        for entrada, dia in zip((self.h_inicio, self.h_fim), self._datas_periodo(*self.PERIODOS_RAPIDOS[nome])):
            entrada.delete(0, tk.END)
            entrada.insert(0, dia.strftime("%d/%m/%Y"))
        self._filtrar_historico()

    def _pintar_rapidos(self, inicio, fim):
        """Destaca o atalho que corresponde às datas digitadas (nenhum, se for um período livre)."""
        for nome, b in self.h_rapidos.items():
            sel = self._datas_periodo(*self.PERIODOS_RAPIDOS[nome]) == (inicio, fim)
            b.configure(fg_color=P["primary_800"] if sel else P["surface"], text_color="#ffffff" if sel else P["text_soft"],
                        hover_color=P["primary_900"] if sel else P["primary_50"],
                        border_width=0 if sel else 1, border_color=P["line"])

    def _filtrar_historico(self):
        try:
            inicio, fim = _data_iso(self.h_inicio.get()), _data_iso(self.h_fim.get())
        except ValueError:
            messagebox.showwarning("Data inválida", "Use datas no formato dd/mm/aaaa.")
            return
        self._pintar_rapidos(date.fromisoformat(inicio), date.fromisoformat(fim))
        forma = self.h_forma.get()
        self._vendas_filtradas = banco.listar_vendas(inicio, fim, None if forma.startswith("Todas") else forma)
        vendas = self._vendas_filtradas
        self._preencher(self.h_tabela, [
            ((f"#{v['id']}", _data_hora(v["criado_em"]),
              f"{v['qtd_itens']} {'item' if v['qtd_itens'] == 1 else 'itens'}", v["formas"] or "",
              _reais(v["desconto_centavos"]) if v["desconto_centavos"] else "—", _reais(v["total_centavos"])), "")
            for v in vendas
        ], vazio=("", "Nenhuma venda no período", "", "", "", ""))
        n = len(vendas)
        self.h_cartao.subtitulo.configure(text=f"{n} registro(s) no período selecionado")
        self.h_total.configure(text=_reais(sum(v["total_centavos"] for v in vendas)))
        self.h_contagem.configure(text=f"1–{n} de {n}" if n else "0 de 0")

    def _ver_itens_venda(self):
        """Abre o recibo da venda selecionada no Histórico."""
        selecao = self.h_tabela.selection()
        numero = self.h_tabela.item(selecao[0], "values")[0] if selecao else ""
        if not numero.startswith("#"):
            self._avisar("Selecione uma venda na lista", erro=True)
            return
        venda = banco.detalhes_venda(int(numero[1:]))
        if venda:
            self._janela_recibo(venda)

    def _janela_recibo(self, venda):
        """Modal "recibo": itens, totais, formas de pagamento e troco de uma venda gravada."""
        janela = ctk.CTkToplevel(self)
        janela.title(f"Venda #{venda['id']}")
        janela.resizable(False, False)
        janela.transient(self)
        janela.configure(fg_color=P["canvas"])
        largura = 470

        recibo = self._card(janela)
        recibo.pack(fill="x", padx=22, pady=(22, 12))
        cab = ctk.CTkFrame(recibo, fg_color=P["surface"])
        cab.pack(fill="x", padx=22, pady=(20, 14))
        cab.grid_columnconfigure(0, weight=1)
        self._rotulo(cab, f"Venda #{venda['id']}", 20, True, "primary_950").grid(row=0, column=0, sticky="w")
        concluida = venda["status"] == "concluida"
        self._pill(cab, "Concluída" if concluida else venda["status"].capitalize(),
                   "sucesso" if concluida else "perigo").grid(row=0, column=1, sticky="e")
        qtd = len(venda["itens"])
        self._rotulo(cab, f"{_data_hora(venda['criado_em'])} · {qtd} {'item' if qtd == 1 else 'itens'}",
                     11, cor="muted").grid(row=1, column=0, columnspan=2, sticky="w")

        def separador():
            # Picote do cupom: traços em vez de linha contínua.
            tk.Label(recibo, text="- " * 60, bg=P["surface"], fg=P["line_hover"], font=self._fonte_tk(9),
                     anchor="w", width=1).pack(fill="x", padx=22)

        separador()
        # Itens em tk.Label (leve) dentro de um quadro rolável quando a venda é grande.
        lista = (ctk.CTkScrollableFrame(recibo, fg_color=P["surface"], height=300,
                                        scrollbar_button_color=P["line"], scrollbar_button_hover_color=P["line_hover"])
                 if qtd > 6 else ctk.CTkFrame(recibo, fg_color=P["surface"]))
        lista.pack(fill="x", padx=(22, 14 if qtd > 6 else 22), pady=10)
        lista.grid_columnconfigure(0, weight=1)
        for i, item in enumerate(venda["itens"]):
            tk.Label(lista, text=item["descricao"], bg=P["surface"], fg=P["text"], font=self._fonte_tk(13, True),
                     anchor="w", justify="left", wraplength=280).grid(row=2 * i, column=0, sticky="w", pady=(8 if i else 0, 0))
            unidade = (item["unidade"] or "UN").lower()
            detalhe = f"{_qtd(item['quantidade'])} {unidade} × {_reais(item['preco_unit_centavos'])}"
            if item["codigo"]:
                detalhe += f"  ·  {item['codigo']}"
            tk.Label(lista, text=detalhe, bg=P["surface"], fg=P["muted"], font=self._fonte_tk(11),
                     anchor="w").grid(row=2 * i + 1, column=0, sticky="w")
            tk.Label(lista, text=_reais(item["subtotal_centavos"]), bg=P["surface"], fg=P["text"],
                     font=self._fonte_tk(13, True), anchor="e").grid(row=2 * i, column=1, sticky="e", padx=(12, 0))

        separador()
        if venda["desconto_centavos"]:
            # Frame vazio do CTk ocupa 200 px: só cria o resumo quando há desconto.
            resumo = ctk.CTkFrame(recibo, fg_color=P["surface"])
            resumo.pack(fill="x", padx=22, pady=(10, 0))
            resumo.grid_columnconfigure(0, weight=1)
            for n, (texto, valor, cor) in enumerate((
                ("Subtotal", _reais(venda["total_centavos"] + venda["desconto_centavos"]), "text_soft"),
                ("Desconto", f"− {_reais(venda['desconto_centavos'])}", "danger"),
            )):
                self._rotulo(resumo, texto, 12, cor=cor).grid(row=n, column=0, sticky="w", pady=1)
                self._rotulo(resumo, valor, 12, cor=cor).grid(row=n, column=1, sticky="e", pady=1)
        caixa_total = ctk.CTkFrame(recibo, fg_color=P["canvas"], corner_radius=12)
        caixa_total.pack(fill="x", padx=22, pady=(10, 12))
        self._rotulo(caixa_total, "Total", 14, True, "text_soft").pack(side="left", padx=16)
        self._rotulo(caixa_total, _reais(venda["total_centavos"]), 28, True, "primary_900").pack(side="right", padx=16, pady=8)

        pagto = ctk.CTkFrame(recibo, fg_color=P["surface"])
        pagto.pack(fill="x", padx=22, pady=(0, 20))
        pagto.grid_columnconfigure(0, weight=1)
        self._rotulo(pagto, "PAGAMENTO", 10, True, "primary_700").grid(row=0, column=0, sticky="w", pady=(0, 4))
        for i, p in enumerate(venda["pagamentos"], start=1):
            self._rotulo(pagto, p["forma"], 12, True, "text").grid(row=i, column=0, sticky="w", pady=1)
            self._rotulo(pagto, _reais(p["valor_centavos"]), 12, True, "text").grid(row=i, column=1, sticky="e", pady=1)
        troco = venda.get("troco_centavos") or 0
        if troco:
            n = len(venda["pagamentos"]) + 1
            dinheiro = sum(p["valor_centavos"] for p in venda["pagamentos"] if p["forma"] == "Dinheiro")
            self._rotulo(pagto, "Recebido em dinheiro", 12, cor="text_soft").grid(row=n, column=0, sticky="w", pady=(6, 1))
            self._rotulo(pagto, _reais(dinheiro + troco), 12, cor="text_soft").grid(row=n, column=1, sticky="e", pady=(6, 1))
            caixa_troco = ctk.CTkFrame(pagto, fg_color=P["accent_soft"], corner_radius=10)
            caixa_troco.grid(row=n + 1, column=0, columnspan=2, sticky="ew", pady=(6, 0))
            self._rotulo(caixa_troco, "Troco", 13, True, "primary_900").pack(side="left", padx=14)
            self._rotulo(caixa_troco, _reais(troco), 18, True, "primary_900").pack(side="right", padx=14, pady=6)

        acoes = ctk.CTkFrame(janela, fg_color=P["canvas"])
        acoes.pack(fill="x", padx=22, pady=(0, 20))
        self._btn(acoes, "Fechar   Esc", janela.destroy, "secundario", 130, height=44).pack(side="right")
        for tecla in ("<Escape>", "<Return>", "<KP_Enter>"):
            janela.bind(tecla, lambda e: janela.destroy())
        # Mesma largura para todo recibo; a altura acompanha o conteúdo.
        janela.update_idletasks()
        janela.geometry(f"{largura}x{janela.winfo_reqheight()}")

        def focar():
            try:
                janela.grab_set()
            except tk.TclError:
                pass
            janela.focus_force()

        janela.after(120, focar)
        janela.wait_window()
        self.h_tabela.focus_set()

    def _exportar_vendas(self):
        if not getattr(self, "_vendas_filtradas", None):
            messagebox.showinfo("Exportar", "Não há vendas no período para exportar.")
            return
        caminho = filedialog.asksaveasfilename(
            title="Exportar vendas (CSV)", defaultextension=".csv",
            initialfile="vendas.csv", filetypes=[("CSV", "*.csv")],
        )
        if not caminho:
            return
        try:
            qtd = exportacao.exportar_vendas_csv(caminho, self._vendas_filtradas)
        except OSError as erro:
            messagebox.showerror("Erro", f"Não foi possível exportar.\n{erro}")
            return
        self._avisar(f"{qtd} venda(s) exportada(s)")

    # ==================================================================
    # Tela de Relatório do dia
    # ==================================================================
    def mostrar_relatorio(self):
        self._limpar_area("relatorio")
        rel = banco.relatorio_dia()
        dia = date.fromisoformat(rel["data"])
        pagina = self._pagina()
        pagina.grid_rowconfigure(2, weight=1)
        self._cabecalho(
            pagina, "DESEMPENHO", "Relatório do dia",
            f"Visão geral das vendas de {dia.day} de {MESES[dia.month - 1]} de {dia.year}.",
        ).grid(row=0, column=0, sticky="ew", pady=(0, 18))

        if rel["total_ontem"]:
            variacao = (rel["total"] - rel["total_ontem"]) / rel["total_ontem"] * 100
            comparacao = f"{variacao:+.1f}% comparado a ontem".replace(".", ",")
        else:
            comparacao = "Sem vendas ontem para comparar"
        ticket = rel["total"] // rel["qtd"] if rel["qtd"] else 0
        media = rel["itens"] / rel["qtd"] if rel["qtd"] else 0
        self._grade_kpis(pagina, [
            ("Total vendido", _reais(rel["total"]), comparacao, True),
            ("Vendas concluídas", str(rel["qtd"]), f"Ticket médio de {_reais(ticket)}"),
            ("Itens vendidos", _qtd(round(rel["itens"], 3)), f"Média de {media:.1f} itens por venda".replace(".", ",")),
        ]).grid(row=1, column=0, sticky="ew", pady=(0, 14))

        corpo = ctk.CTkFrame(pagina, fg_color="transparent")
        corpo.grid(row=2, column=0, sticky="nsew")
        corpo.grid_columnconfigure(0, weight=3, uniform="r")
        corpo.grid_columnconfigure(1, weight=2, uniform="r")

        formas = self._cartao_dados(corpo, "Por forma de pagamento", "Distribuição do faturamento de hoje")
        formas.grid(row=0, column=0, sticky="new", padx=(0, 7))
        lista = ctk.CTkFrame(formas, fg_color="transparent")
        lista.grid(row=2, column=0, sticky="ew", padx=18, pady=(6, 14))
        lista.grid_columnconfigure(2, weight=1)
        icones_forma = dict(FORMAS_PAGAMENTO)
        total_formas = sum(valor for _, valor, _ in rel["por_forma"]) or 1
        for i, (forma, valor, qtd) in enumerate(rel["por_forma"]):
            ctk.CTkLabel(lista, text="", image=icone(icones_forma.get(forma, "wallet"), 17, P["primary_700"]),
                         width=36, height=36, corner_radius=10, fg_color=P["primary_50"]).grid(row=i, column=0, pady=9)
            textos = ctk.CTkFrame(lista, fg_color="transparent")
            textos.grid(row=i, column=1, sticky="w", padx=(10, 16))
            self._rotulo(textos, forma, 12, True).pack(anchor="w")
            self._rotulo(textos, f"{qtd} venda{'s' if qtd != 1 else ''}", 10, cor="muted").pack(anchor="w")
            barra = ctk.CTkProgressBar(lista, height=6, corner_radius=3, fg_color=P["line_soft"],
                                       progress_color=P["accent"])
            barra.grid(row=i, column=2, sticky="ew")
            barra.set(valor / total_formas)
            self._rotulo(lista, _reais(valor), 12, True).grid(row=i, column=3, sticky="e", padx=(16, 10))
            self._rotulo(lista, f"{round(valor * 100 / total_formas)}%", 10, cor="muted", width=36).grid(row=i, column=4, sticky="e")
        if not rel["por_forma"]:
            self._rotulo(lista, "Sem vendas hoje.", 11, cor="muted").grid(row=0, column=0, columnspan=5, pady=16)

        ranking = self._cartao_dados(corpo, "Produtos mais vendidos", "Por quantidade hoje")
        ranking.grid(row=0, column=1, sticky="new", padx=(7, 0))
        lista = ctk.CTkFrame(ranking, fg_color="transparent")
        lista.grid(row=2, column=0, sticky="ew", padx=18, pady=(6, 14))
        lista.grid_columnconfigure(1, weight=1)
        for i, item in enumerate(rel["mais_vendidos"]):
            ctk.CTkLabel(lista, text=str(i + 1), width=26, height=26, corner_radius=8, fg_color=P["accent_soft"],
                         text_color=P["primary_700"], font=self._fonte(10, True)).grid(row=i, column=0, pady=8)
            textos = ctk.CTkFrame(lista, fg_color="transparent")
            textos.grid(row=i, column=1, sticky="w", padx=10)
            self._rotulo(textos, item["descricao"], 12, True).pack(anchor="w")
            self._rotulo(textos, f"{_qtd(round(item['quantidade'], 3))} {(item['unidade'] or 'un').lower()}.",
                         10, cor="muted").pack(anchor="w")
            self._rotulo(lista, _reais(item["valor"]), 12, True, "primary_800").grid(row=i, column=2, sticky="e")
        if not rel["mais_vendidos"]:
            self._rotulo(lista, "Sem vendas hoje.", 11, cor="muted").grid(row=0, column=0, columnspan=3, pady=16)

    # ==================================================================
    # Tela de Configuração da empresa (só master)
    # ==================================================================
    CRT_OPCOES = ["1 — Simples Nacional", "2 — Simples Nacional (excesso)", "3 — Regime Normal"]
    AMBIENTES = {"Homologação": "homologacao", "Produção": "producao"}

    def mostrar_config(self):
        if not self.eh_master:
            messagebox.showwarning("Acesso restrito", "Só o usuário master acessa a configuração.")
            return
        self._limpar_area("config")
        cfg = banco.ler_config_fiscal()
        pagina = self._pagina(rolavel=True)
        producao = cfg.get("ambiente") == "producao"
        self._cabecalho(
            pagina, "ADMINISTRAÇÃO", "Configurações da empresa", "Dados cadastrais, fiscais e de emissão da sua loja.",
            lambda p: self._pill(p, "Ambiente de produção" if producao else "Ambiente de homologação",
                                 "sucesso" if producao else "aviso"),
        ).grid(row=0, column=0, sticky="ew", pady=(0, 16), padx=(0, 14))

        self.cfg = {}
        abas = ctk.CTkFrame(pagina, fg_color="#e9f0ec", corner_radius=11, border_width=1, border_color=P["line"])
        abas.grid(row=1, column=0, sticky="w", pady=(0, 12))
        paineis = {"Dados da empresa": ctk.CTkFrame(pagina, fg_color="transparent"),
                   "Fiscal e NFC-e": ctk.CTkFrame(pagina, fg_color="transparent")}
        botoes_aba = {}

        def mostrar_aba(nome):
            for n, painel in paineis.items():
                if n == nome:
                    painel.grid(row=2, column=0, sticky="ew", padx=(0, 14))
                else:
                    painel.grid_remove()
                botoes_aba[n].configure(fg_color="#ffffff" if n == nome else "transparent",
                                        text_color=P["primary_900"] if n == nome else P["text_soft"])

        for nome in paineis:
            b = ctk.CTkButton(abas, text=nome, height=self._alvo(32, 44), width=10, corner_radius=8,
                              font=self._fonte(11, True),
                              hover_color="#ffffff", command=lambda n=nome: mostrar_aba(n))
            b.pack(side="left", padx=4, pady=4)
            botoes_aba[nome] = b

        def campos(corpo, lista, colunas=3):
            itens = []
            for chave, rotulo, obrigatorio in lista:
                campo = self._campo(corpo, rotulo, valor=cfg.get(chave) or "", obrigatorio=obrigatorio,
                                    senha=chave in ("certificado_senha", "csc"))
                itens.append((chave, campo))
            self._grade_campos(corpo, itens, colunas, self.cfg)

        empresa = paineis["Dados da empresa"]
        empresa.grid_columnconfigure(0, weight=1)
        card, corpo = self._secao(empresa, "Empresa", "Informações que identificam seu estabelecimento.")
        card.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        campos(corpo, [("razao_social", "Razão social", True), ("nome_fantasia", "Nome fantasia", False),
                       ("cnpj", "CNPJ", True), ("ie", "Inscrição Estadual", False),
                       ("im", "Inscrição Municipal", False)])
        crt = self._campo_select(corpo, "Regime tributário (CRT)", self.CRT_OPCOES)
        atual_crt = cfg.get("crt") or "1"
        crt.entrada.set(next((o for o in self.CRT_OPCOES if o.startswith(atual_crt)), self.CRT_OPCOES[0]))
        crt.grid(row=1, column=2, sticky="ew", padx=(6, 0), pady=6)
        self.cfg_crt = crt.entrada

        card, corpo = self._secao(empresa, "Logo da loja", "Aparece na tela de login e na barra lateral.")
        card.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        self.cfg_logo = self._seletor_imagem(
            corpo, cfg.get("logo_arquivo") or None, "Imagem da logo",
            "PNG, JPG ou WEBP. Uma imagem com fundo transparente fica melhor. "
            "O sistema guarda uma cópia: o arquivo original pode ser apagado ou movido.",
            imagens.LADO_LOGO, quadrada=False, icone_vazio="cart",
        )
        self.cfg_logo.pack(fill="x")

        card, corpo = self._secao(empresa, "Endereço e contato", "Dados usados nos documentos e comprovantes.")
        card.grid(row=2, column=0, sticky="ew", pady=(0, 18))
        campos(corpo, [("cep", "CEP", False), ("logradouro", "Logradouro", False), ("numero", "Número", False),
                       ("complemento", "Complemento", False), ("bairro", "Bairro", False),
                       ("municipio", "Município", False), ("cod_municipio", "Código IBGE", False)])
        uf = self._campo_select(corpo, "UF", UFS, cfg.get("uf") or "SP", obrigatorio=True)
        uf.grid(row=2, column=1, sticky="ew", padx=6, pady=6)
        self.cfg_uf = uf.entrada
        contato = ctk.CTkFrame(corpo, fg_color="transparent")
        contato.grid(row=3, column=0, columnspan=3, sticky="ew")
        campos(contato, [("telefone", "Telefone", False), ("email", "E-mail", False)], 2)

        fiscal = paineis["Fiscal e NFC-e"]
        fiscal.grid_columnconfigure(0, weight=1)
        tem_certificado = bool(cfg.get("certificado_caminho"))
        card, corpo = self._secao(fiscal, "Fiscal e NFC-e", "Credenciais e numeração dos documentos fiscais.",
                                  ("Certificado informado", "sucesso") if tem_certificado else ("Sem certificado", "aviso"))
        card.grid(row=0, column=0, sticky="ew", pady=(0, 18))
        ambiente = self._campo_select(corpo, "Ambiente", list(self.AMBIENTES),
                                      "Produção" if producao else "Homologação")
        self.cfg_ambiente = ambiente.entrada
        itens = [(None, ambiente)]
        for chave, rotulo in [("serie", "Série"), ("proximo_numero", "Próximo número NFC-e"),
                              ("csc", "CSC"), ("csc_id", "ID do CSC")]:
            itens.append((chave, self._campo(corpo, rotulo, valor=cfg.get(chave) or "", senha=chave == "csc")))
        self._grade_campos(corpo, itens, 3, self.cfg)
        self.cfg.pop(None)
        certificado = ctk.CTkFrame(corpo, fg_color="transparent")
        certificado.grid(row=2, column=0, columnspan=3, sticky="ew")
        certificado.grid_columnconfigure(0, weight=2)
        certificado.grid_columnconfigure(2, weight=1)
        caminho = self._campo(certificado, "Certificado (.pfx)", "Selecione o arquivo do certificado A1",
                              cfg.get("certificado_caminho") or "")
        caminho.grid(row=0, column=0, sticky="ew", pady=6)
        self.cfg["certificado_caminho"] = caminho.entrada
        self._btn(certificado, "Escolher", self._escolher_certificado, "secundario", 100).grid(
            row=0, column=1, sticky="s", padx=8, pady=6)
        senha = self._campo(certificado, "Senha do certificado", valor=cfg.get("certificado_senha") or "", senha=True)
        senha.grid(row=0, column=2, sticky="ew", pady=6)
        self.cfg["certificado_senha"] = senha.entrada

        mostrar_aba("Dados da empresa")

        alterado = cfg.get("atualizado_em")
        texto = (f"Última alteração em {datetime.fromisoformat(alterado):%d/%m/%Y às %H:%M}."
                 if alterado else "A configuração ainda não foi salva.")
        barra = self._barra_acoes(texto)
        self._btn(barra.botoes, "Salvar configurações", self._salvar_config, width=190).pack(side="right")

    def _escolher_certificado(self):
        caminho = filedialog.askopenfilename(
            title="Selecione o certificado digital",
            filetypes=[("Certificado", "*.pfx *.p12"), ("Todos", "*.*")],
        )
        if caminho:
            self.cfg["certificado_caminho"].delete(0, tk.END)
            self.cfg["certificado_caminho"].insert(0, caminho)

    def _salvar_config(self):
        dados = {chave: campo.get().strip() for chave, campo in self.cfg.items()}
        dados["certificado_senha"] = self.cfg["certificado_senha"].get()  # pode conter espaços
        dados["ambiente"] = self.AMBIENTES[self.cfg_ambiente.get()]
        dados["crt"] = self.cfg_crt.get().split(" ")[0]
        dados["uf"] = self.cfg_uf.get()
        for chave, nome in [("razao_social", "Razão social"), ("cnpj", "CNPJ"), ("uf", "UF")]:
            if not dados.get(chave):
                messagebox.showwarning("Campo obrigatório", f"Informe: {nome}.")
                return
        logo = self.cfg_logo.estado
        try:
            dados["logo_arquivo"] = self._gravar_imagem_escolhida(logo, "logo")
        except OSError as erro:
            messagebox.showerror("Erro", f"Não foi possível guardar a logo.\n{erro}")
            return
        banco.salvar_config_fiscal(dados)
        self._descartar_imagem_antiga(logo, dados["logo_arquivo"])
        self._atualizar_marca()
        self.mostrar_config()
        self._avisar("Configurações salvas com sucesso")

    # ==================================================================
    # Tela de Usuários (só master)
    # ==================================================================
    PAPEIS = {"Operador": "operador", "Master": "master"}

    def mostrar_usuarios(self):
        if not self.eh_master:
            messagebox.showwarning("Acesso restrito", "Só o usuário master gerencia usuários.")
            return
        self._limpar_area("usuarios")
        self.usuario_sel_id = None
        pagina = self._pagina()
        pagina.grid_rowconfigure(1, weight=1)
        self._cabecalho(
            pagina, "ADMINISTRAÇÃO", "Usuários", "Gerencie acessos, papéis e status da equipe.",
            lambda p: self._btn(p, "Novo usuário", self._limpar_user_form, width=150, icone_nome="plus"),
        ).grid(row=0, column=0, sticky="ew", pady=(0, 18))

        corpo = ctk.CTkFrame(pagina, fg_color="transparent")
        corpo.grid(row=1, column=0, sticky="nsew")
        corpo.grid_columnconfigure(0, weight=2, uniform="u")
        corpo.grid_columnconfigure(1, weight=3, uniform="u")

        self.u_equipe = self._cartao_dados(corpo, "Equipe")
        self.u_equipe.grid(row=0, column=0, sticky="new", padx=(0, 7))
        self.u_lista = ctk.CTkFrame(self.u_equipe, fg_color="transparent")
        self.u_lista.grid(row=2, column=0, sticky="ew", padx=6, pady=6)
        self.u_editor = self._card(corpo)
        self.u_editor.grid(row=0, column=1, sticky="new", padx=(7, 0))
        self._atualizar_usuarios()
        self._montar_editor_usuario(None)

    def _atualizar_usuarios(self):
        # A lista fica em memória: selecionar/editar não precisa consultar o banco de novo.
        self._usuarios = {u["id"]: u for u in banco.listar_usuarios()}
        self.u_equipe.subtitulo.configure(text=f"{len(self._usuarios)} usuário(s) cadastrado(s)")
        for w in self.u_lista.winfo_children():
            w.destroy()
        for u in self._usuarios.values():
            selecionado = u["id"] == self.usuario_sel_id
            linha = ctk.CTkFrame(self.u_lista, corner_radius=10, cursor="hand2", border_width=1,
                                 fg_color=P["primary_50"] if selecionado else "transparent",
                                 border_color=P["line"] if selecionado else P["surface"])
            linha.pack(fill="x", pady=1)
            nome = u.get("nome") or u["login"]
            avatar = ctk.CTkLabel(linha, text=_iniciais_nome(nome), width=34, height=34, corner_radius=17,
                                  fg_color=P["avatar"], text_color=P["primary_900"], font=self._fonte(10, True))
            avatar.pack(side="left", padx=(10, 10), pady=9)
            textos = tk.Frame(linha, bg=P["primary_50"] if selecionado else P["surface"])
            textos.pack(side="left", fill="x", expand=True)
            t1 = tk.Label(textos, text=nome, bg=textos["bg"], fg=P["text"], font=self._fonte_tk(12, True), anchor="w")
            t1.pack(anchor="w")
            t2 = tk.Label(textos, text=u.get("email") or f"login: {u['login']}", bg=textos["bg"], fg=P["muted"],
                          font=self._fonte_tk(10), anchor="w")
            t2.pack(anchor="w")
            self._pill(linha, "Ativo" if u["ativo"] else "Inativo", "sucesso" if u["ativo"] else "neutro").pack(side="right", padx=10)
            for w in (linha, avatar, textos, t1, t2):
                w.bind("<Button-1>", lambda e, uid=u["id"]: self._carregar_usuario_sel(uid))

    def _carregar_usuario_sel(self, usuario_id):
        self.usuario_sel_id = usuario_id
        self._atualizar_usuarios()
        self._montar_editor_usuario(self._usuarios.get(usuario_id))

    def _montar_editor_usuario(self, u):
        for w in self.u_editor.winfo_children():
            w.destroy()
        cab = ctk.CTkFrame(self.u_editor, fg_color="transparent")
        cab.pack(fill="x", padx=20, pady=(18, 0))
        self._rotulo(cab, "Editar usuário" if u else "Novo usuário", 13, True).pack(anchor="w")
        self._rotulo(cab, "Defina as informações e permissões de acesso.", 10, cor="muted").pack(anchor="w")
        ctk.CTkFrame(self.u_editor, height=1, fg_color=P["line_soft"]).pack(fill="x", padx=20, pady=14)

        corpo = ctk.CTkFrame(self.u_editor, fg_color="transparent")
        corpo.pack(fill="x", padx=20)
        campos = {}
        papel_atual = "Master" if u and u["papel"] == "master" else "Operador"
        itens = [
            ("login", self._campo(corpo, "Login", "Ex.: joao", u["login"] if u else "", obrigatorio=True)),
            ("nome", self._campo(corpo, "Nome completo", "Ex.: João Mendes", (u or {}).get("nome") or "")),
            ("email", self._campo(corpo, "E-mail", "nome@empresa.com.br", (u or {}).get("email") or "")),
            ("papel", self._campo_select(corpo, "Papel", list(self.PAPEIS), papel_atual,
                                         comando=lambda v: self._pintar_permissao(v))),
        ]
        if not u:
            itens.append(("senha", self._campo(corpo, "Senha inicial", f"Mín. {SENHA_MINIMA} caracteres",
                                               obrigatorio=True, senha=True)))
        self._grade_campos(corpo, itens, 2, campos)
        if u:
            campos["login"].configure(state="disabled", text_color=P["muted"])  # login não muda
        self.u_campos = campos

        self.u_permissao = ctk.CTkFrame(self.u_editor, fg_color=P["canvas"], corner_radius=11,
                                        border_width=1, border_color=P["line"])
        self.u_permissao.pack(fill="x", padx=20, pady=(14, 0))
        self._pintar_permissao(papel_atual)

        ctk.CTkFrame(self.u_editor, height=1, fg_color=P["line_soft"]).pack(fill="x", padx=20, pady=14)
        acoes = ctk.CTkFrame(self.u_editor, fg_color="transparent")
        acoes.pack(fill="x", padx=20, pady=(0, 18))
        self._btn(acoes, "Salvar usuário", self._salvar_usuario, width=150).pack(side="right")
        if u:
            self._btn(acoes, "Desativar" if u["ativo"] else "Reativar", self._alternar_ativo,
                      "perigo" if u["ativo"] else "secundario", 120).pack(side="right", padx=8)
            self._btn(acoes, "Trocar senha", self._trocar_senha_usuario, "secundario", 130).pack(side="right")

    def _pintar_permissao(self, papel):
        for w in self.u_permissao.winfo_children():
            w.destroy()
        master = papel == "Master"
        ctk.CTkLabel(self.u_permissao, text="", image=icone("settings" if master else "cart", 18, P["primary_700"])).pack(
            side="left", padx=(14, 10), pady=12)
        textos = ctk.CTkFrame(self.u_permissao, fg_color=P["canvas"])
        textos.pack(side="left", pady=8)
        self._rotulo(textos, "Acesso de Master" if master else "Acesso de Operador", 11, True).pack(anchor="w")
        self._rotulo(textos, "Pode gerenciar configurações, usuários e relatórios." if master
                     else "Pode vender, operar o caixa e consultar relatórios.", 10, cor="muted").pack(anchor="w")
        self._pill(self.u_permissao, "Total" if master else "Operação", "sucesso" if master else "neutro").pack(side="right", padx=14)

    def _limpar_user_form(self):
        self.usuario_sel_id = None
        self._atualizar_usuarios()
        self._montar_editor_usuario(None)
        self.u_campos["login"].focus()

    def _usuario_selecionado(self):
        return self._usuarios.get(self.usuario_sel_id)

    def _salvar_usuario(self):
        c = self.u_campos
        nome = c["nome"].get().strip() or None
        email = c["email"].get().strip() or None
        papel = self.PAPEIS[c["papel"].get()]
        u = self._usuario_selecionado()
        if u is None:
            self._criar_usuario(c["login"].get().strip(), c["senha"].get(), papel, nome, email)
        else:
            self._gravar_usuario(u["id"], nome, email, papel, u["ativo"], "Usuário salvo com sucesso")

    def _criar_usuario(self, login, senha, papel, nome, email):
        if not login or len(senha) < SENHA_MINIMA:
            messagebox.showwarning("Campos obrigatórios", f"Informe login e senha (mín. {SENHA_MINIMA} caracteres).")
            return
        try:
            banco.criar_usuario(login, senha, papel, nome, email, trocar_senha=True)
        except banco.LoginDuplicado:
            messagebox.showwarning("Login repetido", f"O login {login} já existe.")
            return
        self._limpar_user_form()
        self._avisar("Usuário criado — trocará a senha no 1º acesso")

    def _gravar_usuario(self, usuario_id, nome, email, papel, ativo, aviso):
        try:
            banco.atualizar_usuario(usuario_id, nome, email, papel, ativo)
        except banco.UltimoMaster:
            messagebox.showwarning("Não permitido", "O sistema precisa de pelo menos um master ativo.")
            return
        self._carregar_usuario_sel(usuario_id)
        self._avisar(aviso)

    def _alternar_ativo(self):
        u = self._usuario_selecionado()
        if u:
            self._gravar_usuario(u["id"], u.get("nome"), u.get("email"), u["papel"], not u["ativo"],
                                 "Usuário desativado" if u["ativo"] else "Usuário reativado")

    def _trocar_senha_usuario(self):
        u = self._usuario_selecionado()
        if not u:
            return
        nova = self._pedir_senha("Trocar senha", f"Nova senha de {u['login']}")
        if nova:
            # Senha definida pelo master é provisória: o usuário troca no próximo login.
            banco.alterar_senha_usuario(u["id"], nova, exigir_troca=True)
            self._avisar("Senha alterada — o usuário deverá trocá-la no próximo login")


class TelaLogin(_Estilo, ctk.CTk):
    """Janela de login mostrada antes de abrir o PDV (painel da marca + formulário)."""

    def __init__(self):
        super().__init__()
        self._fontes = {}
        self.usuario = None
        self.title("PDV Próprio — Entrar")
        self.geometry("1040x640")
        self.minsize(900, 580)
        self.configure(fg_color="#f8fbf9")
        self.protocol("WM_DELETE_WINDOW", self._fechar)
        self.grid_columnconfigure(0, weight=5, uniform="login")
        self.grid_columnconfigure(1, weight=6, uniform="login")
        self.grid_rowconfigure(0, weight=1)
        self._painel_marca().grid(row=0, column=0, sticky="nsew")
        self._painel_formulario().grid(row=0, column=1, sticky="nsew")

    def _painel_marca(self):
        painel = ctk.CTkFrame(self, fg_color=P["primary_950"], corner_radius=0)
        # Círculos decorativos no canto (criados antes: ficam atrás do texto).
        # Ficam no canto de cima, longe dos textos: o Tk não tem transparência real,
        # e um texto por cima de um círculo mostraria o retângulo do fundo.
        ctk.CTkFrame(painel, width=440, height=440, corner_radius=220, fg_color="#11312a",
                     border_width=1, border_color="#23432e").place(relx=1, x=-160, y=-280)
        ctk.CTkFrame(painel, width=240, height=240, corner_radius=120, fg_color="#153528",
                     bg_color="#11312a").place(relx=1, x=-60, y=-180)

        marca = ctk.CTkFrame(painel, fg_color="transparent")
        marca.place(x=42, y=34)
        self._selo_marca(marca, 56).pack(side="left")
        textos = ctk.CTkFrame(marca, fg_color="transparent")
        textos.pack(side="left", padx=14)
        loja = _nome_loja()
        if loja:
            self.title(f"{loja} — Entrar")
        self._rotulo(textos, loja or "PDV Próprio", 15, True, "#ffffff").pack(anchor="w")
        self._rotulo(textos, "PDV Próprio" if loja else "Seu negócio, no controle.", 11, cor="brand_sub").pack(anchor="w")

        mensagem = ctk.CTkFrame(painel, fg_color="transparent")
        mensagem.place(x=42, rely=0.5, anchor="w")
        self._rotulo(mensagem, "PONTO DE VENDA", 10, True, "accent").pack(anchor="w")
        self._rotulo(mensagem, "Vendas simples.\nGestão mais\ninteligente.", 38, True, "#ffffff",
                     justify="left").pack(anchor="w", pady=(10, 12))
        self._rotulo(mensagem, "Uma operação rápida, segura e organizada\npara o seu comércio.", 12,
                     cor="brand_sub", justify="left").pack(anchor="w")

        recurso = ctk.CTkFrame(painel, fg_color="transparent")
        recurso.place(x=42, rely=1, y=-34, anchor="sw")
        ctk.CTkLabel(recurso, text="", image=icone("check", 12, P["primary_950"]), width=20, height=20,
                     corner_radius=10, fg_color=P["accent"]).pack(side="left")
        self._rotulo(recurso, "Funciona mesmo sem internet", 11, cor="#d7e6df").pack(side="left", padx=8)
        return painel

    def _painel_formulario(self):
        painel = ctk.CTkFrame(self, fg_color="#f8fbf9", corner_radius=0)
        card = ctk.CTkFrame(painel, fg_color="transparent", width=360)
        card.place(relx=0.5, rely=0.5, anchor="center")

        self._rotulo(card, "BEM-VINDO DE VOLTA", 10, True, "primary_700").pack(anchor="w")
        self._rotulo(card, "Entre na sua conta", 28, True, "primary_950").pack(anchor="w", pady=(4, 2))
        self._rotulo(card, "Use seus dados para acessar o ponto de venda.", 12, cor="muted").pack(anchor="w", pady=(0, 20))

        lembrado = banco.ler_preferencia("ultimo_login")
        login = self._campo(card, "Usuário", "Seu login", lembrado or "", obrigatorio=True)
        login.pack(fill="x", pady=6)
        senha = self._campo(card, "Senha", "Sua senha", obrigatorio=True, senha=True)
        senha.pack(fill="x", pady=6)
        self.login, self.senha = login.entrada, senha.entrada
        for entrada in (self.login, self.senha):
            entrada.configure(width=360, height=46)
        self.btn_mostrar = self._link(self.senha, "Mostrar", self._alternar_senha, 10)
        self.btn_mostrar.place(relx=1, rely=0.5, x=-8, anchor="e")
        # Erro de login aparece aqui, embaixo da senha (sem janela pop-up para fechar).
        self.lbl_erro = self._rotulo(card, "", 11, True, "danger", justify="left", wraplength=360)
        self.lbl_erro.pack(anchor="w")

        self.lembrar = ctk.CTkCheckBox(card, text="Lembrar meu usuário neste computador", font=self._fonte(11),
                                       text_color=P["text_soft"], fg_color=P["primary_800"],
                                       hover_color=P["primary_900"], border_color=P["line_hover"],
                                       checkbox_width=18, checkbox_height=18, corner_radius=5)
        self.lembrar.pack(anchor="w", pady=(4, 18))
        self.lembrar.select()
        self._btn(card, "Entrar no PDV", self._entrar, height=48, icone_nome="chevron", lado="right").pack(fill="x")
        self._rotulo(card, "Operação local protegida · dados guardados neste computador", 10, cor="muted").pack(pady=(18, 0))

        self.login.bind("<Return>", lambda e: self.senha.focus())
        self.senha.bind("<Return>", lambda e: self._entrar())
        (self.senha if lembrado else self.login).focus()
        return painel

    def _alternar_senha(self):
        visivel = self.senha.cget("show") == ""
        self.senha.configure(show="•" if visivel else "")
        self.btn_mostrar.configure(text="Mostrar" if visivel else "Ocultar")

    def _entrar(self):
        login = self.login.get().strip()
        usuario = banco.autenticar(login, self.senha.get())
        self.senha.delete(0, tk.END)
        if not usuario:
            self.lbl_erro.configure(text="Usuário ou senha incorretos. Confira e tente de novo.")
            self.senha.configure(border_color=P["danger"])
            self.senha.focus()
            return
        self.lbl_erro.configure(text="")
        self.senha.configure(border_color=P["line"])
        if usuario.get("trocar_senha"):
            nova = self._pedir_senha("Troca de senha obrigatória", "Por segurança, defina uma nova senha")
            if not nova:
                return
            banco.alterar_senha_usuario(usuario["id"], nova)
        banco.salvar_preferencia("ultimo_login", login if self.lembrar.get() else None)
        self.usuario = usuario
        self._fechar()


def iniciar():
    """Fluxo: login -> PDV. Permite trocar de usuário sem fechar o programa."""
    banco.inicializar()
    while True:
        login = TelaLogin()
        login.mainloop()
        if login.usuario is None:
            break
        app = AppPDV(login.usuario)
        app.mainloop()
        if not app.relogar:
            break


if __name__ == "__main__":
    iniciar()

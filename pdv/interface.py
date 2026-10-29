"""PDV Próprio — aplicativo de desktop.

Janela feita com CustomTkinter, conversando direto com o banco SQLite pela
camada em banco.py. O visual segue o protótipo do Figma Make ("Aprimorar
Estética do PDV"): barra lateral verde-escura com ícones, cabeçalhos de página
com sobretítulo, cartões brancos de borda suave, indicadores (KPIs), pílulas de
status e avisos rápidos (toasts) no lugar de janelas de "OK".

Rodar com:  python3 -m pdv   (ou python3 pdv_app.py, na raiz)
"""

import threading
import tkinter as tk
import urllib.error
from datetime import date, datetime, timedelta
from tkinter import ttk, messagebox, filedialog

import customtkinter as ctk

from . import banco
from . import exportacao
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
    "muted": "#82938d",
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


def _centavos_ou_zero(texto):
    texto = (texto or "").strip()
    return banco.para_centavos(texto) if texto else 0


class _Estilo:
    """Componentes visuais compartilhados pela janela de login e pelo app."""

    def _fechar(self):
        """Fecha a janela cancelando antes os `after` pendentes do CustomTkinter.

        Sem isso, animações de clique e checagens de DPI disparam depois do destroy
        e o terminal mostra 'invalid command name ...'.
        """
        for agendado in self.tk.call("after", "info"):
            self.after_cancel(agendado)
        self.destroy()

    def _fonte(self, tamanho=13, negrito=False):
        # Reaproveita a mesma fonte: criar um CTkFont por widget custa caro.
        chave = (tamanho, negrito)
        if chave not in self._fontes:
            self._fontes[chave] = ctk.CTkFont(family=FONTE, size=tamanho, weight="bold" if negrito else "normal")
        return self._fontes[chave]

    @staticmethod
    def _fonte_tk(tamanho, negrito=False):
        """Fonte para widgets tk puros (mais leves que os CTk): tamanho em pixels."""
        return (FONTE, -tamanho, "bold" if negrito else "normal")

    def _rotulo(self, parent, texto, tamanho=12, negrito=False, cor="text", **kw):
        return ctk.CTkLabel(parent, text=texto, font=self._fonte(tamanho, negrito),
                            text_color=P.get(cor, cor), **kw)

    def _btn(self, parent, text, command, tipo="primario", width=140, height=40, icone_nome=None, lado="left"):
        estilo = _ESTILOS_BOTAO[tipo]
        imagem = icone(icone_nome, 17, estilo["text_color"]) if icone_nome else None
        return ctk.CTkButton(
            parent, text=text, command=command, width=width, height=height, corner_radius=12,
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
        return ctk.CTkEntry(parent, placeholder_text=placeholder, show="•" if senha else "", **{**opcoes, **kw})

    def _titulo_campo(self, parent, rotulo, obrigatorio=False):
        linha = ctk.CTkFrame(parent, fg_color="transparent")
        self._rotulo(linha, rotulo, 10, True, "text_soft").pack(side="left")
        if obrigatorio:
            self._rotulo(linha, " *", 10, True, "danger").pack(side="left")
        return linha

    def _campo(self, parent, rotulo, placeholder="", valor="", obrigatorio=False, senha=False):
        """Rótulo em cima + campo. O campo fica em `.entrada`."""
        quadro = ctk.CTkFrame(parent, fg_color="transparent")
        self._titulo_campo(quadro, rotulo, obrigatorio).pack(anchor="w", pady=(0, 5))
        quadro.entrada = self._entry(quadro, placeholder, senha=senha)
        quadro.entrada.pack(fill="x")
        if valor:
            quadro.entrada.insert(0, valor)
        return quadro

    def _select(self, parent, valores, comando=None):
        """Lista de opções com borda (OptionMenu dentro de uma moldura). Devolve (moldura, menu)."""
        moldura = ctk.CTkFrame(parent, fg_color="#ffffff", corner_radius=9, border_width=1,
                               border_color=P["line"], height=40)
        menu = ctk.CTkOptionMenu(
            moldura, values=valores, height=36, corner_radius=8, anchor="w",
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
        self.forma_venda = "Dinheiro"
        self.desconto = 0                 # centavos
        self.pagamento_dividido = None    # [{forma, valor_centavos}] ou None
        self.relogar = False
        self.tela = None
        self._busca_agendada = None
        self._relogio_agendado = None
        self._toast = None
        self._menu = {}

        self._estilizar_tabelas()
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._montar_barra_lateral()
        self.area = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self.area.grid(row=0, column=1, sticky="nsew")

        # Atalhos do caixa (como no protótipo): F2 busca, F4 finaliza.
        self.bind("<F2>", lambda e: self.tela == "vendas" and self.campo_venda_cod.focus())
        self.bind("<F4>", lambda e: self.tela == "vendas" and self.finalizar_venda())

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
            foreground=P["text_soft"], rowheight=40, borderwidth=0, font=self._fonte_tk(12),
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

    def _avisar(self, texto):
        """Toast na base da janela (some sozinho), para confirmações de sucesso."""
        if self._toast is not None:
            self._toast.destroy()
        toast = ctk.CTkFrame(self, fg_color=P["primary_950"], corner_radius=11)
        ctk.CTkLabel(toast, text="", image=icone("check", 17, P["accent"])).pack(side="left", padx=(16, 8), pady=10)
        ctk.CTkLabel(toast, text=texto, font=self._fonte(12, True), text_color="#ffffff").pack(side="left", padx=(0, 18))
        toast.place(relx=0.5, rely=1.0, x=111, y=-24, anchor="s")  # centro da área de trabalho
        toast.lift()
        self._toast = toast

        def sumir():
            if self._toast is toast:
                toast.destroy()
                self._toast = None

        self.after(2800, sumir)

    # ---------- Barra lateral ----------
    def _montar_barra_lateral(self):
        barra = ctk.CTkFrame(self, width=222, corner_radius=0, fg_color=P["primary_950"])
        barra.grid(row=0, column=0, sticky="nsew")
        barra.pack_propagate(False)

        marca = ctk.CTkFrame(barra, fg_color="transparent")
        marca.pack(fill="x", padx=20, pady=(24, 22))
        ctk.CTkLabel(marca, text="", image=icone("cart", 21, P["primary_950"]), width=42, height=42,
                     corner_radius=13, fg_color=P["accent"]).pack(side="left")
        textos = ctk.CTkFrame(marca, fg_color="transparent")
        textos.pack(side="left", padx=(12, 0))
        self._rotulo(textos, "PDV Próprio", 15, True, "#ffffff").pack(anchor="w")
        self._rotulo(textos, "Ponto de venda", 11, cor="brand_sub").pack(anchor="w")
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
            rodape, text="Sincronizar dados", command=self.sincronizar_agora, height=38, corner_radius=10,
            image=icone("sync", 16, P["primary_950"]), font=self._fonte(12, True), **_ESTILOS_BOTAO["accent"],
        )
        self.btn_sync.pack(fill="x", padx=12, pady=(14, 12))

        operador = ctk.CTkFrame(rodape, fg_color="transparent")
        operador.pack(fill="x", padx=14, pady=(0, 16))
        nome = self.usuario.get("nome") or self.usuario["login"]
        ctk.CTkLabel(operador, text=_iniciais_nome(nome), width=32, height=32, corner_radius=16,
                     fg_color=P["avatar"], text_color=P["primary_900"], font=self._fonte(10, True)).pack(side="left")
        textos = ctk.CTkFrame(operador, fg_color="transparent")
        textos.pack(side="left", padx=(10, 0), fill="x", expand=True)
        self._rotulo(textos, nome, 12, True, "#ffffff", anchor="w").pack(anchor="w")
        linha = ctk.CTkFrame(textos, fg_color="transparent")
        linha.pack(anchor="w")
        self._rotulo(linha, "Master" if self.eh_master else "Operador", 10, cor="brand_sub").pack(side="left")
        self._rotulo(linha, "  ·  ", 10, cor="brand_sub").pack(side="left")
        trocar = self._rotulo(linha, "Trocar senha", 10, True, "accent", cursor="hand2")
        trocar.pack(side="left")
        trocar.bind("<Button-1>", lambda e: self._trocar_minha_senha())
        ctk.CTkButton(operador, text="", image=icone("logout", 17, P["nav_text"]), width=30, height=30,
                      corner_radius=8, fg_color="transparent", hover_color=P["nav_hover"],
                      command=self._sair).pack(side="right")

    def _item_menu(self, parent, chave, texto, nome_icone, comando):
        item = ctk.CTkFrame(parent, height=42, corner_radius=10, fg_color="transparent", cursor="hand2")
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
        self.forma_venda = "Dinheiro"
        self.desconto = 0
        self.pagamento_dividido = None
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
            b = ctk.CTkButton(self.abas_categoria, text=nome, width=10, height=32, corner_radius=9,
                              font=self._fonte(11, True), command=lambda n=nome: self._selecionar_categoria(n))
            b.pack(side="left", padx=(0, 5))
            self.botoes_categoria[nome] = b
        self.lbl_qtd_catalogo = self._rotulo(cab, "", 10, cor="muted")
        self.lbl_qtd_catalogo.pack(side="right")
        self._pintar_categorias()

        self.grade = ctk.CTkScrollableFrame(catalogo, fg_color="transparent", corner_radius=0,
                                            scrollbar_button_color=P["line"], scrollbar_button_hover_color=P["line_hover"])
        self.grade.grid(row=2, column=0, sticky="nsew")
        for i in range(3):
            self.grade.grid_columnconfigure(i, weight=1, uniform="cards")
        return catalogo

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
        if not prods:
            vazio = ctk.CTkFrame(self.grade, fg_color="transparent")
            vazio.grid(row=0, column=0, columnspan=3, pady=60)
            ctk.CTkLabel(vazio, text="", image=icone("search", 26, P["primary_700"]), width=56, height=56,
                         corner_radius=18, fg_color=P["primary_50"]).pack()
            self._rotulo(vazio, "Nenhum produto encontrado", 13, True).pack(pady=(12, 2))
            self._rotulo(vazio, "Tente buscar com outro termo ou categoria.", 11, cor="muted").pack()
            return
        for idx, p in enumerate(prods[:LIMITE_CARTOES]):
            self._cartao_produto(p).grid(row=idx // 3, column=idx % 3, padx=5, pady=5, sticky="nsew")
        if len(prods) > LIMITE_CARTOES:
            self._rotulo(
                self.grade, f"+{len(prods) - LIMITE_CARTOES} produto(s) — refine a busca.", 11, cor="muted"
            ).grid(row=LIMITE_CARTOES // 3 + 1, column=0, columnspan=3, pady=10)

    def _cartao_produto(self, p):
        card = ctk.CTkFrame(self.grade, fg_color=P["surface"], corner_radius=13, border_width=1,
                            border_color=P["line"], height=104, cursor="hand2")
        card.pack_propagate(False)
        visual = ctk.CTkLabel(card, text=_iniciais(p["descricao"]), width=46, height=58, corner_radius=10,
                              fg_color=CORES_PRODUTO[p["id"] % len(CORES_PRODUTO)],
                              text_color=P["primary_900"], font=self._fonte(11, True))
        visual.pack(side="left", padx=(13, 11), pady=13)
        # Textos em tk.Label (leve): o catálogo pode ter dezenas de cartões.
        info = tk.Frame(card, bg=P["surface"])
        info.pack(side="left", fill="both", expand=True, pady=14, padx=(0, 10))
        nome = tk.Label(info, text=p["descricao"], bg=P["surface"], fg=P["text"], font=self._fonte_tk(12, True),
                        anchor="w", justify="left", wraplength=135)
        nome.pack(anchor="w", fill="x")
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
        rodape = ctk.CTkFrame(checkout, fg_color="transparent")
        rodape.grid(row=3, column=0, sticky="ew", padx=16, pady=(10, 12))
        rodape.grid_columnconfigure((0, 1, 2), weight=1, uniform="formas")

        titulo = ctk.CTkFrame(rodape, fg_color="transparent")
        titulo.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 6))
        self._rotulo(titulo, "Forma de pagamento", 11, True, "text_soft").pack(side="left")
        self._link(titulo, "Dividir pagamento", self._dividir_pagamento).pack(side="right")

        self.botoes_forma = {}
        for i, (forma, nome_icone) in enumerate(FORMAS_PAGAMENTO):
            b = ctk.CTkButton(rodape, text=forma, height=40, corner_radius=9, font=self._fonte(11, True),
                              command=lambda f=forma: self._selecionar_forma(f))
            b.grid(row=1, column=i, sticky="ew", padx=(0 if i == 0 else 3, 0 if i == 2 else 3))
            self.botoes_forma[forma] = (b, nome_icone)

        totais = ctk.CTkFrame(rodape, fg_color="transparent")
        totais.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(10, 0))
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

        ctk.CTkFrame(rodape, height=1, fg_color=P["line"]).grid(row=3, column=0, columnspan=3, sticky="ew", pady=8)
        total = ctk.CTkFrame(rodape, fg_color="transparent")
        total.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(0, 10))
        self._rotulo(total, "Total", 13, True).pack(side="left", anchor="s", pady=(0, 6))
        self.label_total = self._rotulo(total, "", 28, True, "primary_900")
        self.label_total.pack(side="right")

        self.btn_finalizar = self._btn(rodape, "Finalizar venda      F4", self.finalizar_venda, height=46)
        self.btn_finalizar.grid(row=5, column=0, columnspan=3, sticky="ew")
        self._btn(rodape, "Emitir NFC-e", self._emitir_nfce, "secundario", height=34,
                  icone_nome="receipt").grid(row=6, column=0, columnspan=3, sticky="ew", pady=(6, 0))
        self.lbl_dica = self._rotulo(rodape, "", 10, cor="muted", wraplength=320)
        self.lbl_dica.grid(row=7, column=0, columnspan=3, pady=(8, 0))
        return checkout

    def _selecionar_forma(self, forma):
        self.forma_venda = forma
        self.pagamento_dividido = None
        self._pintar_formas()

    def _pintar_formas(self):
        for forma, (b, nome_icone) in self.botoes_forma.items():
            ativo = self.pagamento_dividido is None and forma == self.forma_venda
            cor = "#ffffff" if ativo else P["text_soft"]
            b.configure(
                image=icone(nome_icone, 17, cor), text_color=cor,
                fg_color=P["primary_800"] if ativo else "#fbfdfc",
                hover_color=P["primary_900"] if ativo else P["primary_50"],
                border_width=0 if ativo else 1, border_color=P["line"],
            )
        if self.pagamento_dividido:
            partes = " + ".join(f"{p['forma']} {_reais(p['valor_centavos'])}" for p in self.pagamento_dividido)
            self.lbl_dica.configure(text=f"Pagamento dividido: {partes}.")
        else:
            self.lbl_dica.configure(text=f"Ao finalizar, a venda será registrada em {self.forma_venda}.")

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
            self.bell()  # nada encontrado
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
        self.pagamento_dividido = None
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
        if self.pagamento_dividido and sum(p["valor_centavos"] for p in self.pagamento_dividido) != total:
            self.pagamento_dividido = None  # o total mudou: a divisão antiga não vale mais

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
        self._pintar_formas()

    def _linha_carrinho(self, idx, item, sub):
        linha = ctk.CTkFrame(self.lista_carrinho, fg_color="#ffffff", corner_radius=12,
                             border_width=1, border_color=P["line_soft"])
        linha.grid(row=idx, column=0, sticky="ew", pady=4, padx=2)
        linha.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(linha, text=_iniciais(item["descricao"]), width=40, height=46, corner_radius=9,
                     fg_color=CORES_PRODUTO[item["produto_id"] % len(CORES_PRODUTO)],
                     text_color=P["primary_900"], font=self._fonte(10, True)).grid(row=0, column=0, rowspan=3, padx=(10, 10), pady=10, sticky="n")
        tk.Label(linha, text=item["descricao"], bg="#ffffff", fg=P["text"], font=self._fonte_tk(12, True),
                 anchor="w", justify="left", wraplength=200).grid(row=0, column=1, sticky="w", pady=(10, 0))
        tk.Label(linha, text=f"{_reais(item['preco_unit_centavos'])} / {item['unidade'].lower()}", bg="#ffffff", fg=P["muted"],
                 font=self._fonte_tk(10), anchor="w").grid(row=1, column=1, sticky="w")
        ctk.CTkButton(linha, text="", image=icone("trash", 15, P["muted"]), width=26, height=26, corner_radius=7,
                      fg_color="transparent", hover_color=P["danger_soft"],
                      command=lambda: self.remover_item(item)).grid(row=0, column=2, padx=(0, 6), pady=(6, 0), sticky="ne")

        base = ctk.CTkFrame(linha, fg_color="transparent")
        base.grid(row=2, column=1, columnspan=2, sticky="ew", padx=(0, 12), pady=(6, 10))
        stepper = ctk.CTkFrame(base, fg_color=P["primary_50"], corner_radius=7, border_width=1, border_color=P["line"])
        stepper.pack(side="left")
        passo = self._passo(item)
        for texto_icone, delta in (("minus", -passo), (None, 0), ("plus", passo)):
            if texto_icone:
                ctk.CTkButton(stepper, text="", image=icone(texto_icone, 14, P["primary_700"]), width=26, height=24,
                              corner_radius=6, fg_color="transparent", hover_color=P["accent_soft"],
                              command=lambda d=delta: self._alterar_qtd(item, d)).pack(side="left", padx=1, pady=1)
            else:
                ctk.CTkButton(stepper, text=_qtd(item["quantidade"]), width=34, height=24, corner_radius=0,
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

    def _dividir_pagamento(self):
        total = self._total_atual()
        if not self.carrinho or not total:
            messagebox.showinfo("Dividir pagamento", "Adicione produtos antes de dividir o pagamento.")
            return
        atuais = {p["forma"]: p["valor_centavos"] for p in (self.pagamento_dividido or [])}
        atuais = atuais or {self.forma_venda: total}

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
            return
        pagamentos = [{"forma": f, "valor_centavos": _centavos_ou_zero(t)} for f, t in resposta.items()]
        pagamentos = [p for p in pagamentos if p["valor_centavos"] > 0]
        if len(pagamentos) == 1:
            self._selecionar_forma(pagamentos[0]["forma"])
        else:
            self.pagamento_dividido = pagamentos
            self._pintar_formas()

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
        if not self.carrinho:
            return
        sessao = banco.sessao_aberta()
        total = self._total_atual()
        pagamentos = self.pagamento_dividido or [{"forma": self.forma_venda, "valor_centavos": total}]
        try:
            venda_id, total_gravado = banco.registrar_venda(
                self.carrinho, pagamentos, sessao and sessao["id"], self.desconto,
            )
        except Exception as erro:
            messagebox.showerror("Erro", f"Não foi possível registrar a venda.\n{erro}")
            return
        self._avisar(f"Venda #{venda_id} de {_reais(total_gravado)} concluída com sucesso")
        self._limpar_carrinho()
        self._atualizar_numero_venda()
        self.campo_venda_cod.focus()

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

        card, corpo = self._secao(pagina, "Dados fiscais", "Campos necessários para NFC-e e escrituração fiscal.",
                                  ("NFC-e / SPED", "neutro"))
        card.grid(row=2, column=0, sticky="ew", pady=(0, 18), padx=(0, 14))
        self._grade_campos(corpo, [
            (chave, self._campo(corpo, rotulo, exemplo, obrigatorio=chave in obrigatorios))
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
        try:
            if self.produto_sel_id is None:
                banco.cadastrar_produto(dados)
            else:
                banco.atualizar_produto(self.produto_sel_id, dados)
        except banco.CodigoDuplicado:
            self._marcar_erro("codigo", "Código repetido", f"Já existe um produto com o código {dados['codigo']}.")
            return
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
        inicio = self._campo(filtros, "Período inicial", "dd/mm/aaaa", (hoje - timedelta(days=30)).strftime("%d/%m/%Y"))
        inicio.grid(row=0, column=0, sticky="ew", padx=(16, 6), pady=16)
        fim = self._campo(filtros, "Período final", "dd/mm/aaaa", hoje.strftime("%d/%m/%Y"))
        fim.grid(row=0, column=1, sticky="ew", padx=6, pady=16)
        forma = self._campo_select(filtros, "Pagamento", ["Todas as formas", *(f for f, _ in FORMAS_PAGAMENTO)])
        forma.grid(row=0, column=2, sticky="ew", padx=6, pady=16)
        self.h_inicio, self.h_fim, self.h_forma = inicio.entrada, fim.entrada, forma.entrada
        self._btn(filtros, "Aplicar filtros", self._filtrar_historico, width=140).grid(
            row=0, column=3, sticky="s", padx=(6, 16), pady=16)

        dados = self._cartao_dados(pagina, "Vendas encontradas",
                                   direita=lambda p: self._rotulo(p, "", 20, True, "primary_900"))
        dados.grid(row=2, column=0, sticky="nsew")
        dados.grid_rowconfigure(2, weight=1)
        self.h_cartao, self.h_total = dados, dados.direita
        moldura, self.h_tabela = self._tabela(dados, [
            ("id", "Venda", 90, "w"), ("data", "Data e hora", 180, "w"),
            ("itens", "Itens", 90, "w"), ("formas", "Pagamento", 200, "w"),
            ("desconto", "Desconto", 110, "w"), ("total", "Total", 120, "w"),
        ])
        moldura.grid(row=2, column=0, sticky="nsew", padx=1)
        self.h_contagem = self._rodape_tabela(dados, "Vendas concluídas no período, mais recentes primeiro.")
        self._filtrar_historico()

    def _filtrar_historico(self):
        try:
            inicio, fim = _data_iso(self.h_inicio.get()), _data_iso(self.h_fim.get())
        except ValueError:
            messagebox.showwarning("Data inválida", "Use datas no formato dd/mm/aaaa.")
            return
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
            b = ctk.CTkButton(abas, text=nome, height=32, width=10, corner_radius=8, font=self._fonte(11, True),
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

        card, corpo = self._secao(empresa, "Endereço e contato", "Dados usados nos documentos e comprovantes.")
        card.grid(row=1, column=0, sticky="ew", pady=(0, 18))
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
        banco.salvar_config_fiscal(dados)
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
        ctk.CTkLabel(marca, text="", image=icone("cart", 23, P["primary_950"]), width=42, height=42,
                     corner_radius=13, fg_color=P["accent"]).pack(side="left")
        textos = ctk.CTkFrame(marca, fg_color="transparent")
        textos.pack(side="left", padx=12)
        self._rotulo(textos, "PDV Próprio", 15, True, "#ffffff").pack(anchor="w")
        self._rotulo(textos, "Seu negócio, no controle.", 11, cor="brand_sub").pack(anchor="w")

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

        self.lembrar = ctk.CTkCheckBox(card, text="Lembrar meu usuário neste computador", font=self._fonte(11),
                                       text_color=P["text_soft"], fg_color=P["primary_800"],
                                       hover_color=P["primary_900"], border_color=P["line_hover"],
                                       checkbox_width=18, checkbox_height=18, corner_radius=5)
        self.lembrar.pack(anchor="w", pady=(12, 18))
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
            messagebox.showwarning("Acesso negado", "Usuário ou senha incorretos.")
            self.senha.focus()
            return
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

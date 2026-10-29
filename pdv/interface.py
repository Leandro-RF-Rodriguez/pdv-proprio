"""PDV Próprio — aplicativo de desktop.

Janela feita com CustomTkinter, conversando direto com o banco SQLite
pela camada em banco.py. Visual inspirado no design (verde, clean, Manrope):
tela de Venda com catálogo em cartões à esquerda e checkout à direita.

Rodar com:  python3 -m pdv   (ou python3 pdv_app.py, na raiz)
"""

import threading
import tkinter as tk
import urllib.error
from tkinter import ttk, messagebox, filedialog

import customtkinter as ctk

from . import banco
from . import exportacao
from . import nfce
from . import sync

ctk.set_appearance_mode("light")

FORMAS_PAGAMENTO = ["Dinheiro", "Cartão", "Pix"]
FONTE = "Manrope"
SENHA_MINIMA = 4
LIMITE_CARTOES = 60      # cartões do catálogo desenhados de uma vez (widgets são pesados)
ATRASO_BUSCA_MS = 200    # espera o operador parar de digitar antes de redesenhar

P = {
    "primary": "#173f35",
    "primary_strong": "#0d2c25",
    "primary_soft": "#d8efe0",
    "accent": "#a9c95d",
    "accent_strong": "#52712f",
    "accent_soft": "#eaf3d8",
    "success": "#34755f",
    "text": "#18342d",
    "muted": "#728079",
    "border": "#cfe2d6",
    "surface": "#f8fdf9",
    "canvas": "#e6f5eb",
    "danger": "#b03a2e",
    "danger_strong": "#8c2d24",
}

_ESTILOS_BOTAO = {
    "primario": dict(fg_color=P["primary"], hover_color=P["primary_strong"], text_color="#ffffff"),
    "secundario": dict(fg_color=P["surface"], hover_color=P["primary_soft"], text_color=P["primary"], border_width=1, border_color=P["border"]),
    "perigo": dict(fg_color=P["danger"], hover_color=P["danger_strong"], text_color="#ffffff"),
    "sidebar": dict(fg_color="transparent", hover_color=P["primary_strong"], text_color="#ffffff", anchor="w"),
    "accent": dict(fg_color=P["accent"], hover_color=P["accent_strong"], text_color=P["primary_strong"]),
}


class _Estilo:
    """Helpers de estilo compartilhados pela janela de login e pelo app."""

    def _fonte(self, tamanho=13, negrito=False):
        # Reaproveita a mesma fonte: criar um CTkFont por widget custa caro.
        chave = (tamanho, negrito)
        if chave not in self._fontes:
            self._fontes[chave] = ctk.CTkFont(family=FONTE, size=tamanho, weight="bold" if negrito else "normal")
        return self._fontes[chave]

    def _btn(self, parent, text, command, tipo="primario", width=140):
        return ctk.CTkButton(
            parent, text=text, command=command, width=width,
            corner_radius=11, font=self._fonte(13, True), **_ESTILOS_BOTAO[tipo],
        )

    def _card(self, parent, **kw):
        opcoes = dict(fg_color=P["surface"], corner_radius=15, border_width=1, border_color=P["border"])
        return ctk.CTkFrame(parent, **{**opcoes, **kw})

    def _entry(self, parent, placeholder="", senha=False, **kw):
        return ctk.CTkEntry(
            parent, placeholder_text=placeholder, corner_radius=10, show="•" if senha else "",
            fg_color="#ffffff", border_color=P["border"], text_color=P["text"],
            font=self._fonte(13), **kw,
        )

    def _rotulo(self, parent, texto, tamanho=12, negrito=False, cor="text"):
        return ctk.CTkLabel(parent, text=texto, font=self._fonte(tamanho, negrito), text_color=P[cor])

    def _pedir_senha(self, titulo, texto="Defina a nova senha"):
        """Pede uma senha nova (mascarada, com confirmação). Devolve a senha ou None."""
        janela = ctk.CTkToplevel(self)
        janela.title(titulo)
        janela.resizable(False, False)
        janela.transient(self)
        janela.configure(fg_color=P["surface"])
        resultado = []

        self._rotulo(janela, texto, 13, True).pack(padx=20, pady=(18, 8))
        senha = self._entry(janela, "Nova senha", senha=True, width=260)
        senha.pack(padx=20, pady=4)
        confirmacao = self._entry(janela, "Repita a nova senha", senha=True, width=260)
        confirmacao.pack(padx=20, pady=4)
        aviso = self._rotulo(janela, "", 11, cor="danger")
        aviso.pack(padx=20)

        def confirmar(_evento=None):
            if len(senha.get()) < SENHA_MINIMA:
                aviso.configure(text=f"Use ao menos {SENHA_MINIMA} caracteres.")
            elif senha.get() != confirmacao.get():
                aviso.configure(text="As senhas não conferem.")
            else:
                resultado.append(senha.get())
                janela.destroy()

        self._btn(janela, "Confirmar", confirmar, width=260).pack(padx=20, pady=(6, 18))
        senha.bind("<Return>", lambda e: confirmacao.focus())
        confirmacao.bind("<Return>", confirmar)
        def focar():
            try:
                janela.grab_set()  # modal: bloqueia a janela de trás
            except tk.TclError:
                pass
            senha.focus()

        janela.after(120, focar)
        janela.wait_window()
        return resultado[0] if resultado else None


class AppPDV(_Estilo, ctk.CTk):
    def __init__(self, usuario):
        super().__init__()
        self._fontes = {}
        self.usuario = usuario
        self.eh_master = usuario.get("papel") == "master"
        self.title("PDV Próprio")
        self.geometry("1040x700")
        self.minsize(880, 580)
        self.configure(fg_color=P["canvas"])

        self.carrinho = []
        self.produto_sel_id = None
        self.forma_venda = "Dinheiro"
        self.relogar = False
        self._busca_agendada = None

        self._estilizar_tabelas()
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._montar_barra_lateral()
        self.area = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self.area.grid(row=0, column=1, sticky="nsew", padx=24, pady=24)

        self.mostrar_vendas()

    # ---------- Helpers de tela ----------
    def _option(self, parent, valores, width=140):
        return ctk.CTkOptionMenu(
            parent, values=valores, width=width, corner_radius=10,
            fg_color=P["primary"], button_color=P["primary_strong"],
            button_hover_color=P["primary_strong"], text_color="#ffffff",
            font=self._fonte(13, True),
        )

    def _estilizar_tabelas(self):
        estilo = ttk.Style()
        try:
            estilo.theme_use("default")
        except tk.TclError:
            pass
        estilo.configure(
            "Treeview", background=P["surface"], fieldbackground=P["surface"],
            foreground=P["text"], rowheight=30, borderwidth=0, font=(FONTE, 11),
        )
        estilo.configure(
            "Treeview.Heading", background=P["primary_soft"], foreground=P["primary"],
            relief="flat", font=(FONTE, 10, "bold"), padding=6,
        )
        estilo.map("Treeview", background=[("selected", P["primary_soft"])], foreground=[("selected", P["primary"])])
        estilo.map("Treeview.Heading", background=[("active", P["primary_soft"])])

    def _tabela(self, linha, colunas, rolagem=True, **kw):
        """Treeview na área principal. colunas: [(chave, título, largura, alinhamento)]."""
        tabela = ttk.Treeview(self.area, columns=[c[0] for c in colunas], show="headings", **kw)
        for chave, titulo, largura, alinhamento in colunas:
            tabela.heading(chave, text=titulo)
            tabela.column(chave, width=largura, anchor=alinhamento)
        tabela.grid(row=linha, column=0, sticky="nsew")
        if rolagem:
            rol = ttk.Scrollbar(self.area, orient="vertical", command=tabela.yview)
            tabela.configure(yscrollcommand=rol.set)
            rol.grid(row=linha, column=1, sticky="ns")
        return tabela

    @staticmethod
    def _preencher(tabela, linhas, vazio=None):
        tabela.delete(*tabela.get_children())
        for valores in linhas or ([vazio] if vazio else []):
            tabela.insert("", tk.END, values=valores)

    def _titulo(self, texto):
        return self._rotulo(self.area, texto, 26, True)

    def _limpar_area(self, linha_expande=None):
        """Esvazia a área principal e zera o layout (pesos não vazam entre telas)."""
        if self._busca_agendada:
            self.after_cancel(self._busca_agendada)
            self._busca_agendada = None
        for widget in self.area.winfo_children():
            widget.destroy()
        for i in range(6):
            self.area.grid_rowconfigure(i, weight=1 if i == linha_expande else 0)
            self.area.grid_columnconfigure(i, weight=1 if i == 0 else 0)

    def _pedir_valor(self, titulo, texto):
        resposta = ctk.CTkInputDialog(title=titulo, text=texto).get_input()
        if not resposta or not resposta.strip():
            return None
        try:
            return banco.para_centavos(resposta)
        except ValueError:
            messagebox.showwarning("Valor inválido", "Use um número, ex: 5,50.")
            return None

    # ---------- Barra lateral ----------
    def _montar_barra_lateral(self):
        barra = ctk.CTkFrame(self, width=200, corner_radius=0, fg_color=P["primary"])
        barra.grid(row=0, column=0, sticky="nsew")
        barra.grid_propagate(False)

        marca = ctk.CTkFrame(barra, fg_color="transparent")
        marca.pack(padx=20, pady=(26, 22), anchor="w")
        ctk.CTkLabel(
            marca, text="PDV", width=46, height=46, corner_radius=13,
            fg_color=P["accent"], text_color=P["primary_strong"], font=self._fonte(15, True),
        ).pack(side="left")
        textos = ctk.CTkFrame(marca, fg_color="transparent")
        textos.pack(side="left", padx=(10, 0))
        ctk.CTkLabel(textos, text="PDV Próprio", text_color="#ffffff", font=self._fonte(15, True)).pack(anchor="w")
        ctk.CTkLabel(textos, text="Ponto de venda", text_color="#8fb6a6", font=self._fonte(10)).pack(anchor="w")

        itens = [
            ("Venda", self.mostrar_vendas),
            ("Produtos", self.mostrar_produtos),
            ("Caixa", self.mostrar_caixa),
            ("Histórico", self.mostrar_historico),
            ("Relatório", self.mostrar_relatorio),
        ]
        # Telas sensíveis: só o master vê.
        if self.eh_master:
            itens += [("Configuração", self.mostrar_config), ("Usuários", self.mostrar_usuarios)]
        for texto, comando in itens:
            self._btn(barra, texto, comando, tipo="sidebar", width=168).pack(padx=16, pady=5, fill="x")

        # Usuário logado + sair (base da barra).
        rodape = ctk.CTkFrame(barra, fg_color="transparent")
        rodape.pack(side="bottom", fill="x", pady=(0, 14))
        self.btn_sync = self._btn(rodape, "Sincronizar", self.sincronizar_agora, tipo="accent", width=168)
        self.btn_sync.pack(padx=16, pady=(0, 10), fill="x")
        ctk.CTkLabel(
            rodape, text=f"{self.usuario['login']}  ·  {self.usuario['papel']}",
            text_color="#8fb6a6", font=self._fonte(10),
        ).pack(padx=16, anchor="w")
        self._btn(rodape, "Trocar senha", self._trocar_minha_senha, tipo="sidebar", width=168).pack(padx=16, pady=(2, 0), fill="x")
        self._btn(rodape, "Sair", self._sair, tipo="sidebar", width=168).pack(padx=16, pady=(2, 0), fill="x")

    def _trocar_minha_senha(self):
        nova = self._pedir_senha("Trocar senha")
        if nova:
            banco.alterar_senha_usuario(self.usuario["id"], nova)
            messagebox.showinfo("Senha", "Sua senha foi alterada.")

    def _sair(self):
        self.relogar = True  # iniciar() reabre a tela de login
        self.destroy()

    def sincronizar_agora(self):
        pendentes = banco.contar_pendentes()
        if not any(pendentes.values()):
            messagebox.showinfo("Sincronização", "Nada pendente para enviar.")
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
        self.btn_sync.configure(state="normal", text="Sincronizar")
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
            messagebox.showinfo(
                "Sincronização concluída",
                f"Enviado(s): {enviado['produtos']} produto(s) e {enviado['vendas']} venda(s).",
            )

    # ==================================================================
    # Tela de Venda  (catálogo em cartões + checkout)
    # ==================================================================
    def mostrar_vendas(self):
        self._limpar_area(linha_expande=1)
        self.carrinho = []
        self.forma_venda = "Dinheiro"
        self.produtos_venda = banco.listar_produtos()
        for p in self.produtos_venda:
            p["_busca"] = p["descricao"].lower()
        # Índices em memória: leitura de código e NFC-e sem ir ao banco.
        self._por_codigo = {p["codigo"]: p for p in self.produtos_venda if p["codigo"]}
        self._por_id = {p["id"]: p for p in self.produtos_venda}
        self._filtro_desenhado = None

        cabecalho = "Venda" if banco.sessao_aberta() else "Venda  (caixa fechado)"
        self._titulo(cabecalho).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 14))

        # ---- Catálogo (esquerda) ----
        catalogo = ctk.CTkFrame(self.area, fg_color="transparent")
        catalogo.grid(row=1, column=0, sticky="nsew", padx=(0, 16))
        catalogo.grid_columnconfigure(0, weight=1)
        catalogo.grid_rowconfigure(1, weight=1)

        busca = self._card(catalogo)
        busca.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        busca.grid_columnconfigure(0, weight=1)
        self.campo_venda_cod = self._entry(busca, "Ler código de barras ou buscar produto…")
        self.campo_venda_cod.grid(row=0, column=0, padx=(14, 6), pady=12, sticky="ew")
        self.campo_venda_cod.bind("<Return>", lambda e: self.adicionar_por_codigo())
        self.campo_venda_cod.bind("<KeyRelease>", self._agendar_busca)
        self._btn(busca, "Adicionar", self.adicionar_por_codigo, width=110).grid(row=0, column=1, padx=(6, 14), pady=12)

        self.grade = ctk.CTkScrollableFrame(catalogo, fg_color="transparent")
        self.grade.grid(row=1, column=0, sticky="nsew")
        for i in range(3):
            self.grade.grid_columnconfigure(i, weight=1, uniform="cards")
        self._desenhar_catalogo()

        # ---- Checkout (direita) ----
        checkout = self._card(self.area, width=350)
        checkout.grid(row=1, column=1, sticky="nsew")
        checkout.grid_propagate(False)
        checkout.grid_columnconfigure(0, weight=1)
        checkout.grid_rowconfigure(1, weight=1)

        self._rotulo(checkout, "Venda atual", 16, True).grid(row=0, column=0, padx=16, pady=(16, 8), sticky="w")

        self.lista_carrinho = ctk.CTkScrollableFrame(checkout, fg_color="transparent")
        self.lista_carrinho.grid(row=1, column=0, sticky="nsew", padx=10)
        self.lista_carrinho.grid_columnconfigure(0, weight=1)

        rodape = ctk.CTkFrame(checkout, fg_color="transparent")
        rodape.grid(row=2, column=0, sticky="ew", padx=16, pady=(8, 16))
        rodape.grid_columnconfigure((0, 1, 2), weight=1)

        self._rotulo(rodape, "Forma de pagamento", 11, cor="muted").grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 6))
        self.botoes_forma = {}
        for i, forma in enumerate(FORMAS_PAGAMENTO):
            b = ctk.CTkButton(
                rodape, text=forma, width=70, corner_radius=10, font=self._fonte(11, True),
                command=lambda f=forma: self._selecionar_forma(f),
            )
            b.grid(row=1, column=i, padx=2, pady=(0, 14), sticky="ew")
            self.botoes_forma[forma] = b
        self._selecionar_forma(self.forma_venda)

        self.label_total = self._rotulo(rodape, "R$ 0,00", 26, True, "primary")
        self.label_total.grid(row=2, column=0, columnspan=3, sticky="e")
        self.label_tributos = self._rotulo(rodape, "Trib. aprox.: R$ 0,00", 10, cor="muted")
        self.label_tributos.grid(row=3, column=0, columnspan=3, sticky="e", pady=(0, 10))

        self._btn(rodape, "Finalizar venda", self.finalizar_venda, "primario", 200).grid(row=4, column=0, columnspan=3, sticky="ew")
        self._btn(rodape, "Emitir NFC-e", self._emitir_nfce, "secundario", 200).grid(row=5, column=0, columnspan=3, sticky="ew", pady=(6, 0))

        self.campo_venda_cod.focus()
        self._redesenhar_carrinho()

    def _agendar_busca(self, _evento=None):
        """Debounce: só redesenha o catálogo quando o operador para de digitar."""
        if self._busca_agendada:
            self.after_cancel(self._busca_agendada)
        self._busca_agendada = self.after(
            ATRASO_BUSCA_MS, lambda: self._desenhar_catalogo(self.campo_venda_cod.get())
        )

    def _desenhar_catalogo(self, filtro=""):
        self._busca_agendada = None
        filtro = filtro.strip()
        if filtro == self._filtro_desenhado:
            return  # nada mudou (ex.: setas, Shift): evita recriar os cartões
        self._filtro_desenhado = filtro
        for w in self.grade.winfo_children():
            w.destroy()

        termo = filtro.lower()
        prods = [
            p for p in self.produtos_venda
            if termo in p["_busca"] or (p["codigo"] or "").startswith(filtro)
        ] if termo else self.produtos_venda

        if not prods:
            self._rotulo(self.grade, "Nenhum produto.", cor="muted").grid(row=0, column=0, pady=24)
            return
        for idx, p in enumerate(prods[:LIMITE_CARTOES]):
            ctk.CTkButton(
                self.grade,
                text=f"{p['descricao']}\nR$ {banco.formatar_reais(p['preco_centavos'])}",
                command=lambda pr=p: self._adicionar_ao_carrinho(pr),
                fg_color="#ffffff", hover_color=P["primary_soft"], text_color=P["text"],
                border_width=1, border_color=P["border"], corner_radius=15, height=78,
                font=self._fonte(12, True),
            ).grid(row=idx // 3, column=idx % 3, padx=6, pady=6, sticky="nsew")
        if len(prods) > LIMITE_CARTOES:
            self._rotulo(
                self.grade, f"+{len(prods) - LIMITE_CARTOES} produto(s) — refine a busca.", 11, cor="muted"
            ).grid(row=LIMITE_CARTOES // 3 + 1, column=0, columnspan=3, pady=10)

    def _selecionar_forma(self, forma):
        self.forma_venda = forma
        for f, b in self.botoes_forma.items():
            if f == forma:
                b.configure(fg_color=P["primary"], text_color="#ffffff", hover_color=P["primary_strong"], border_width=0)
            else:
                b.configure(fg_color=P["surface"], text_color=P["muted"], hover_color=P["primary_soft"], border_width=1, border_color=P["border"])

    def _adicionar_ao_carrinho(self, produto):
        item = next((i for i in self.carrinho if i["produto_id"] == produto["id"]), None)
        if item:
            item["quantidade"] += 1
        else:
            self.carrinho.append({
                "produto_id": produto["id"],
                "descricao": produto["descricao"],
                "quantidade": 1,
                "preco_unit_centavos": produto["preco_centavos"],
                "aliquota_aprox": produto.get("aliquota_aprox") or 0,
            })
        self._redesenhar_carrinho()

    def adicionar_por_codigo(self):
        codigo = self.campo_venda_cod.get().strip()
        if not codigo:
            return
        produto = self._por_codigo.get(codigo)
        if produto:
            self._adicionar_ao_carrinho(produto)
            self.campo_venda_cod.delete(0, tk.END)
            self._desenhar_catalogo()
        else:
            self.bell()  # código não encontrado
        self.campo_venda_cod.focus()

    def _alterar_qtd(self, item, delta):
        item["quantidade"] += delta
        if item["quantidade"] <= 0:
            self.carrinho.remove(item)
        self._redesenhar_carrinho()

    def remover_item(self, item):
        self.carrinho.remove(item)
        self._redesenhar_carrinho()

    def _mini_btn(self, parent, texto, comando, cor_texto, fundo):
        return ctk.CTkButton(parent, text=texto, width=26, height=24, corner_radius=8, fg_color=fundo,
                             text_color=cor_texto, hover_color=P["accent_soft"] if fundo != "transparent" else P["primary_soft"],
                             font=self._fonte(13, True), command=comando)

    def _redesenhar_carrinho(self):
        for w in self.lista_carrinho.winfo_children():
            w.destroy()

        if not self.carrinho:
            self._rotulo(self.lista_carrinho, "Carrinho vazio\nToque num produto para adicionar", cor="muted").grid(row=0, column=0, pady=40)

        total = tributos = 0
        for idx, item in enumerate(self.carrinho):
            sub = banco.subtotal_centavos(item)
            total += sub
            # Lei da Transparência: valor aproximado dos tributos sobre o total.
            tributos += round(sub * item["aliquota_aprox"] / 100)

            linha = ctk.CTkFrame(self.lista_carrinho, fg_color="#ffffff", corner_radius=12,
                                 border_width=1, border_color=P["border"])
            linha.grid(row=idx, column=0, sticky="ew", pady=5)
            linha.grid_columnconfigure(1, weight=1)
            ctk.CTkLabel(linha, text=item["descricao"], font=self._fonte(12, True), text_color=P["text"], anchor="w").grid(
                row=0, column=0, columnspan=3, padx=12, pady=(10, 2), sticky="w"
            )

            ctrl = ctk.CTkFrame(linha, fg_color="transparent")
            ctrl.grid(row=1, column=0, padx=10, pady=(0, 10), sticky="w")
            self._mini_btn(ctrl, "−", lambda it=item: self._alterar_qtd(it, -1), P["primary"], P["primary_soft"]).pack(side="left")
            ctk.CTkLabel(ctrl, text=f"{item['quantidade']:g}", width=32, font=self._fonte(12, True), text_color=P["text"]).pack(side="left", padx=2)
            self._mini_btn(ctrl, "+", lambda it=item: self._alterar_qtd(it, 1), P["primary"], P["primary_soft"]).pack(side="left")

            direita = ctk.CTkFrame(linha, fg_color="transparent")
            direita.grid(row=1, column=2, padx=10, pady=(0, 10), sticky="e")
            self._rotulo(direita, f"R$ {banco.formatar_reais(sub)}", 12, True, "primary").pack(side="left", padx=(0, 6))
            self._mini_btn(direita, "✕", lambda it=item: self.remover_item(it), P["danger"], "transparent").pack(side="left")

        self.label_total.configure(text=f"R$ {banco.formatar_reais(total)}")
        self.label_tributos.configure(text=f"Trib. aprox.: R$ {banco.formatar_reais(tributos)}")

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
            messagebox.showwarning("Carrinho vazio", "Adicione pelo menos um produto.")
            return
        sessao = banco.sessao_aberta()
        total = sum(banco.subtotal_centavos(i) for i in self.carrinho)
        pagamentos = [{"forma": self.forma_venda, "valor_centavos": total}]
        try:
            venda_id, total_gravado = banco.registrar_venda(self.carrinho, pagamentos, sessao and sessao["id"])
        except Exception as erro:
            messagebox.showerror("Erro", f"Não foi possível registrar a venda.\n{erro}")
            return
        messagebox.showinfo(
            "Venda registrada",
            f"Venda #{venda_id} concluída.\nTotal: R$ {banco.formatar_reais(total_gravado)}",
        )
        self.carrinho = []
        self._redesenhar_carrinho()
        self.campo_venda_cod.focus()

    # ==================================================================
    # Tela de Produtos (cadastrar, editar, excluir)
    # ==================================================================
    def mostrar_produtos(self):
        """Tela de PESQUISA de produtos (filtros + resultados + exportação)."""
        self._limpar_area(linha_expande=2)
        self._avancado_visivel = False
        self._produtos_filtrados = []

        self._titulo("Produtos").grid(row=0, column=0, sticky="w", pady=(0, 14))

        filtros = self._card(self.area)
        filtros.grid(row=1, column=0, sticky="ew", pady=(0, 14))
        filtros.grid_columnconfigure((0, 1, 2, 3), weight=1)

        self.flt_texto = self._entry(filtros, "Descrição, código EAN ou interno")
        self.flt_texto.grid(row=0, column=0, columnspan=2, padx=(14, 4), pady=(14, 6), sticky="ew")
        self.flt_texto.bind("<Return>", lambda e: self._pesquisar_produtos())
        self.flt_status = self._option(filtros, ["Ativos", "Inativos", "Todos"], width=120)
        self.flt_status.grid(row=0, column=2, padx=4, pady=(14, 6), sticky="w")
        self.flt_controla = self._option(filtros, ["Todos", "Controla estoque", "Não controla"], width=170)
        self.flt_controla.grid(row=0, column=3, padx=(4, 14), pady=(14, 6), sticky="w")

        # Filtro avançado (escondido por padrão)
        self.adv = ctk.CTkFrame(filtros, fg_color="transparent")
        self.adv.grid(row=1, column=0, columnspan=4, padx=10, pady=0, sticky="ew")
        self.flt_avancado = {}
        for i, (chave, rotulo) in enumerate([
            ("ncm", "NCM"), ("cfop", "CFOP"), ("cst", "CST/CSOSN"),
            ("origem", "Origem"), ("categoria", "Categoria (merc.)"),
        ]):
            self.adv.grid_columnconfigure(i, weight=1)
            self.flt_avancado[chave] = self._entry(self.adv, rotulo)
            self.flt_avancado[chave].grid(row=0, column=i, padx=4, pady=6, sticky="ew")
        self.adv.grid_remove()

        botoes = ctk.CTkFrame(filtros, fg_color="transparent")
        botoes.grid(row=2, column=0, columnspan=4, padx=14, pady=(2, 12), sticky="w")
        for texto, comando, tipo, largura in [
            ("Pesquisar", self._pesquisar_produtos, "primario", 110),
            ("Filtro avançado", self._toggle_avancado, "secundario", 140),
            ("Novo produto", lambda: self.mostrar_form_produto(None), "accent", 130),
            ("Exportar CSV", self._exportar_produtos, "secundario", 130),
        ]:
            self._btn(botoes, texto, comando, tipo, largura).pack(side="left", padx=(0, 12))

        self.tabela_prod = self._tabela(2, [
            ("id", "ID", 50, "center"), ("codigo", "Cód. EAN", 140, "center"),
            ("descricao", "Descrição", 300, "w"), ("unidade", "Un", 55, "center"),
            ("preco", "Preço (R$)", 100, "e"), ("estoque", "Estoque", 85, "e"),
            ("ativo", "Ativo", 60, "center"),
        ])
        self.tabela_prod.bind("<Double-1>", lambda e: self._editar_produto())

        self._rotulo(
            self.area, "Duplo clique num produto para editar. A exportação CSV usa o filtro atual (padrão SPED 0200).",
            11, cor="muted",
        ).grid(row=3, column=0, sticky="w", pady=(8, 0))

        self._pesquisar_produtos()
        self.flt_texto.focus()

    def _toggle_avancado(self):
        self._avancado_visivel = not self._avancado_visivel
        if self._avancado_visivel:
            self.adv.grid()
        else:
            self.adv.grid_remove()

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
            (
                p["id"], p.get("codigo") or "", p["descricao"], p.get("unidade") or "",
                banco.formatar_reais(p["preco_centavos"]), f"{p.get('estoque') or 0:g}",
                "Sim" if p.get("ativo") else "Não",
            )
            for p in self._produtos_filtrados
        ])

    def _editar_produto(self):
        selecao = self.tabela_prod.selection()
        if selecao:
            self.mostrar_form_produto(int(self.tabela_prod.item(selecao[0], "values")[0]))

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
        messagebox.showinfo("Exportação concluída", f"{qtd} produto(s) exportado(s) para:\n{caminho}")

    # ---------- Formulário de produto (novo / editar) ----------
    _CAMPOS_BASICOS = [
        ("descricao", "Descrição *"), ("codigo", "Código de barras (EAN)"),
        ("codigo_interno", "Código interno"), ("categoria", "Categoria (merc.)"),
        ("unidade", "Unidade *"), ("preco", "Preço venda * (R$)"),
        ("custo", "Custo (R$)"), ("estoque", "Estoque"),
    ]
    _CAMPOS_FISCAIS = [
        ("ncm", "NCM *"), ("cest", "CEST"), ("cfop", "CFOP *"), ("origem", "Origem * (0-8)"),
        ("cst", "CST/CSOSN *"), ("tipo_item", "Tipo item (00-99)"),
        ("aliquota_icms", "ICMS %"), ("aliquota_aprox", "Tributos aprox. %"),
    ]
    _CAMPOS_NUMERICOS = ("estoque", "aliquota_icms", "aliquota_aprox")

    def mostrar_form_produto(self, produto_id=None):
        self._limpar_area(linha_expande=1)
        self.produto_sel_id = produto_id
        self._titulo("Editar produto" if produto_id else "Novo produto").grid(row=0, column=0, sticky="w", pady=(0, 10))

        painel = ctk.CTkScrollableFrame(self.area, fg_color="transparent")
        painel.grid(row=1, column=0, sticky="nsew")
        painel.grid_columnconfigure(0, weight=1)

        form = self._card(painel)
        form.pack(fill="x")
        form.grid_columnconfigure((0, 1, 2, 3), weight=1)
        self.pf = {}

        def secao(titulo, campos, linha):
            self._rotulo(form, titulo, 11, True, "muted").grid(row=linha, column=0, columnspan=4, padx=14, pady=(12, 0), sticky="w")
            for i, (chave, rotulo) in enumerate(campos):
                self.pf[chave] = self._entry(form, rotulo)
                self.pf[chave].grid(row=linha + 1 + i // 4, column=i % 4,
                                    padx=(14 if i % 4 == 0 else 4, 14 if i % 4 == 3 else 4), pady=5, sticky="ew")
            return linha + 1 + (len(campos) - 1) // 4

        ln = secao("Dados básicos", self._CAMPOS_BASICOS, 0)
        self.pf_controla = ctk.CTkCheckBox(form, text="Controla estoque", font=self._fonte(11), text_color=P["text"], fg_color=P["primary"], hover_color=P["primary_strong"])
        self.pf_controla.grid(row=ln + 1, column=0, columnspan=2, padx=14, pady=(4, 2), sticky="w")
        ln = secao("Fiscal (NFC-e / SPED)", self._CAMPOS_FISCAIS, ln + 2)

        botoes = ctk.CTkFrame(form, fg_color="transparent")
        botoes.grid(row=ln + 1, column=0, columnspan=4, padx=14, pady=(8, 14), sticky="w")
        self._btn(botoes, "Salvar", self._salvar_form, width=110).pack(side="left", padx=(0, 6))
        if produto_id:
            self._btn(botoes, "Excluir", self.excluir_produto, "perigo", 90).pack(side="left", padx=6)
        self._btn(botoes, "Voltar", self.mostrar_produtos, "secundario", 90).pack(side="left", padx=6)

        if produto_id:
            self._carregar_produto_no_form(produto_id)
        self.pf["descricao"].focus()

    def _ler_form_produto(self):
        v = {chave: campo.get().strip() for chave, campo in self.pf.items()}

        # Campos obrigatórios (os mesmos que a NFC-e exige)
        for chave, nome in nfce.PRODUTO_OBRIGATORIO.items():
            if not v[chave]:
                messagebox.showwarning("Campo obrigatório", f"Informe: {nome}.")
                self.pf[chave].focus()
                return None

        try:
            preco_centavos = banco.para_centavos(v["preco"])
        except ValueError:
            messagebox.showwarning("Preço inválido", "Preço de venda: use um número, ex: 5,50.")
            self.pf["preco"].focus()
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
            unidade=v["unidade"] or "UN",
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
            messagebox.showwarning("Código repetido", f"Já existe um produto com o código {dados['codigo']}.")
            self.pf["codigo"].focus()
            return
        messagebox.showinfo("Produto", "Produto salvo.")
        self.mostrar_produtos()

    def excluir_produto(self):
        if self.produto_sel_id is None:
            return
        if messagebox.askyesno("Excluir produto", "Deseja mesmo excluir este produto?"):
            banco.inativar_produto(self.produto_sel_id)
            self.mostrar_produtos()

    def _carregar_produto_no_form(self, produto_id):
        produto = banco.obter_produto(produto_id)
        if not produto:
            return
        valores = {chave: produto.get(chave) or "" for chave in self.pf}
        valores["tipo_item"] = produto.get("tipo_item") or "00"
        valores["preco"] = banco.formatar_reais(produto.get("preco_centavos") or 0)
        valores["custo"] = banco.formatar_reais(produto.get("custo_centavos") or 0)
        for chave in self._CAMPOS_NUMERICOS:
            valores[chave] = f"{produto[chave]:g}" if produto.get(chave) else ""
        for chave, campo in self.pf.items():
            campo.delete(0, tk.END)
            campo.insert(0, valores[chave])
        (self.pf_controla.select if produto.get("controla_estoque") else self.pf_controla.deselect)()

    # ==================================================================
    # Tela de Caixa
    # ==================================================================
    def mostrar_caixa(self):
        self._limpar_area()
        self._titulo("Caixa").grid(row=0, column=0, sticky="w", pady=(0, 14))
        sessao = banco.sessao_aberta()
        if sessao is None:
            self._tela_abrir_caixa()
        else:
            self._tela_caixa_aberto(sessao)

    def _tela_abrir_caixa(self):
        caixa = self._card(self.area)
        caixa.grid(row=1, column=0, sticky="ew")
        caixa.grid_columnconfigure(1, weight=1)
        self._rotulo(caixa, "Caixa fechado. Abra para começar a operar.", 13).grid(row=0, column=0, columnspan=2, padx=14, pady=(16, 8), sticky="w")
        self._rotulo(caixa, "Operador:").grid(row=1, column=0, padx=14, pady=8, sticky="e")
        self.campo_operador = self._entry(caixa, "Nome do operador")
        self.campo_operador.grid(row=1, column=1, padx=14, pady=8, sticky="ew")
        self._rotulo(caixa, "Fundo de troco (R$):").grid(row=2, column=0, padx=14, pady=8, sticky="e")
        self.campo_abertura = self._entry(caixa, "ex: 100,00")
        self.campo_abertura.grid(row=2, column=1, padx=14, pady=8, sticky="ew")
        self._btn(caixa, "Abrir caixa", self.abrir_caixa, width=130).grid(row=3, column=1, padx=14, pady=(8, 16), sticky="e")
        self.campo_operador.focus()

    def abrir_caixa(self):
        operador = self.campo_operador.get().strip() or None
        texto = self.campo_abertura.get().strip()
        try:
            abertura = banco.para_centavos(texto) if texto else 0
        except ValueError:
            messagebox.showwarning("Valor inválido", "Fundo de troco: use um número, ex: 100,00.")
            return
        try:
            banco.abrir_caixa(operador, abertura)
        except banco.CaixaJaAberto:
            messagebox.showwarning("Caixa já aberto", "Já existe um caixa aberto.")
        self.mostrar_caixa()

    def _tela_caixa_aberto(self, sessao):
        info = self._card(self.area)
        info.grid(row=1, column=0, sticky="ew", pady=(0, 14))
        self._rotulo(
            info, f"Caixa aberto por {sessao['operador'] or '—'}  ·  desde {sessao['aberto_em']}", 14, True, "primary",
        ).pack(padx=14, pady=14, anchor="w")

        resumo = banco.resumo_caixa(sessao["id"])
        painel = self._card(self.area)
        painel.grid(row=2, column=0, sticky="ew", pady=(0, 14))
        painel.grid_columnconfigure(1, weight=1)
        for i, (rotulo, chave) in enumerate([
            ("Fundo de troco (abertura)", "abertura"),
            ("Suprimentos (+)", "suprimentos"),
            ("Sangrias (−)", "sangrias"),
            ("Vendas em dinheiro (+)", "vendas_dinheiro"),
            ("Esperado na gaveta", "esperado_gaveta"),
            ("Total vendido (todas as formas)", "vendas_total"),
        ]):
            destaque = chave == "esperado_gaveta"
            cor = "primary" if destaque else "text"
            self._rotulo(painel, rotulo, 14, destaque, cor).grid(row=i, column=0, padx=14, pady=6, sticky="w")
            self._rotulo(painel, f"R$ {banco.formatar_reais(resumo[chave])}", 14, destaque, cor).grid(row=i, column=1, padx=14, pady=6, sticky="e")

        botoes = ctk.CTkFrame(self.area, fg_color="transparent")
        botoes.grid(row=3, column=0, sticky="ew")
        self._btn(botoes, "Suprimento", lambda: self._movimento(sessao, "suprimento"), "secundario", 120).pack(side="left", padx=(0, 6), pady=6)
        self._btn(botoes, "Sangria", lambda: self._movimento(sessao, "sangria"), "secundario", 120).pack(side="left", padx=6, pady=6)
        self._btn(botoes, "Fechar caixa", lambda: self.fechar_caixa(sessao), "perigo", 140).pack(side="right", pady=6)

    def _movimento(self, sessao, tipo):
        valor = self._pedir_valor(tipo.capitalize(), f"Valor do {tipo} (R$):")
        if valor and valor > 0:
            banco.registrar_movimento_caixa(sessao["id"], tipo, valor)
            self.mostrar_caixa()

    def fechar_caixa(self, sessao):
        esperado = banco.resumo_caixa(sessao["id"])["esperado_gaveta"]
        contado = self._pedir_valor(
            "Fechar caixa",
            f"Esperado na gaveta: R$ {banco.formatar_reais(esperado)}\nDigite o valor contado (R$):",
        )
        if contado is None:
            return
        banco.fechar_caixa(sessao["id"], contado)
        diferenca = contado - esperado
        if diferenca == 0:
            situacao = "Caixa bateu certo."
        else:
            situacao = f"{'Sobra' if diferenca > 0 else 'Falta'} de R$ {banco.formatar_reais(abs(diferenca))}."
        messagebox.showinfo("Caixa fechado", situacao)
        self.mostrar_caixa()

    # ==================================================================
    # Tela de Histórico de vendas
    # ==================================================================
    def mostrar_historico(self):
        self._limpar_area(linha_expande=1)
        self._titulo("Histórico de vendas").grid(row=0, column=0, sticky="w", pady=(0, 14))
        tabela = self._tabela(1, [
            ("id", "Venda", 70, "center"), ("data", "Data/hora", 170, "center"),
            ("itens", "Itens", 70, "center"), ("formas", "Pagamento", 160, "w"),
            ("total", "Total (R$)", 120, "e"),
        ])
        self._preencher(tabela, [
            (f"#{v['id']}", v["criado_em"].replace("T", " "), v["qtd_itens"],
             v["formas"] or "", banco.formatar_reais(v["total_centavos"]))
            for v in banco.listar_vendas()
        ], vazio=("", "(nenhuma venda ainda)", "", "", ""))

    # ==================================================================
    # Tela de Relatório
    # ==================================================================
    def mostrar_relatorio(self):
        self._limpar_area()
        rel = banco.relatorio_dia()
        self._titulo(f"Relatório do dia  ·  {rel['data']}").grid(row=0, column=0, sticky="w", pady=(0, 14))

        topo = self._card(self.area)
        topo.grid(row=1, column=0, sticky="ew", pady=(0, 14))
        topo.grid_columnconfigure((0, 1), weight=1)
        for coluna, (rotulo, valor, lado) in enumerate([
            ("Vendas concluídas", str(rel["qtd"]), "w"),
            ("Total vendido", f"R$ {banco.formatar_reais(rel['total'])}", "e"),
        ]):
            self._rotulo(topo, rotulo, 14, cor="muted").grid(row=0, column=coluna, padx=14, pady=(14, 2), sticky=lado)
            self._rotulo(topo, valor, 22, True, "primary").grid(row=1, column=coluna, padx=14, pady=(0, 14), sticky=lado)

        self._rotulo(self.area, "Por forma de pagamento", 16, True).grid(row=2, column=0, sticky="w", pady=(0, 6))
        tabela = self._tabela(3, [("forma", "Forma", 200, "w"), ("valor", "Valor (R$)", 160, "e")], rolagem=False, height=4)
        self._preencher(
            tabela, [(forma, banco.formatar_reais(valor)) for forma, valor in rel["por_forma"]],
            vazio=("(sem vendas hoje)", ""),
        )

    # ==================================================================
    # Tela de Configuração fiscal (só master)
    # ==================================================================
    CRT_OPCOES = ["1 - Simples Nacional", "2 - Simples Nacional (excesso)", "3 - Regime Normal"]

    def mostrar_config(self):
        if not self.eh_master:
            messagebox.showwarning("Acesso restrito", "Só o usuário master acessa a configuração.")
            return
        self._limpar_area(linha_expande=1)
        self._titulo("Configuração da empresa").grid(row=0, column=0, sticky="w", pady=(0, 10))

        cfg = banco.ler_config_fiscal()
        painel = ctk.CTkScrollableFrame(self.area, fg_color="transparent")
        painel.grid(row=1, column=0, sticky="nsew")
        painel.grid_columnconfigure(0, weight=1)
        self.cfg = {}

        def secao(titulo, campos):
            """campos: [(chave, rótulo)]; chave None = só a linha do rótulo (widget à parte)."""
            self._rotulo(painel, titulo, 15, True, "primary").pack(anchor="w", pady=(10, 4))
            card = self._card(painel)
            card.pack(fill="x", pady=(0, 6))
            card.grid_columnconfigure(1, weight=1)
            for linha, (chave, rotulo) in enumerate(campos):
                self._rotulo(card, rotulo + ":").grid(row=linha, column=0, padx=(14, 6), pady=6, sticky="e")
                if chave:
                    entrada = self._entry(card, senha=chave == "certificado_senha")
                    entrada.insert(0, cfg.get(chave) or "")
                    entrada.grid(row=linha, column=1, columnspan=1 if chave == "certificado_caminho" else 2,
                                 padx=(0, 6 if chave == "certificado_caminho" else 14), pady=6, sticky="ew")
                    self.cfg[chave] = entrada
            return card

        c = secao("Empresa", [
            ("razao_social", "Razão social *"), ("nome_fantasia", "Nome fantasia"), ("cnpj", "CNPJ *"),
            ("ie", "Inscrição Estadual"), ("im", "Inscrição Municipal"), (None, "Regime (CRT)"),
        ])
        self.cfg_crt = self._option(c, self.CRT_OPCOES, width=240)
        atual_crt = cfg.get("crt") or "1"
        self.cfg_crt.set(next((o for o in self.CRT_OPCOES if o.startswith(atual_crt)), self.CRT_OPCOES[0]))
        self.cfg_crt.grid(row=5, column=1, padx=(0, 14), pady=6, sticky="w")

        secao("Endereço", [
            ("cep", "CEP"), ("logradouro", "Logradouro"), ("numero", "Número"),
            ("complemento", "Complemento"), ("bairro", "Bairro"), ("municipio", "Município"),
            ("cod_municipio", "Cód. município (IBGE)"), ("uf", "UF *"),
        ])
        secao("Contato", [("telefone", "Telefone"), ("email", "E-mail")])

        c = secao("Fiscal / NFC-e", [
            (None, "Ambiente"), ("serie", "Série"), ("proximo_numero", "Próximo número NFC-e"),
            ("csc", "CSC"), ("csc_id", "ID do CSC"), ("certificado_caminho", "Certificado (.pfx)"),
            ("certificado_senha", "Senha do certificado"),
        ])
        self.cfg_ambiente = self._option(c, ["homologacao", "producao"], width=160)
        self.cfg_ambiente.set(cfg.get("ambiente") or "homologacao")
        self.cfg_ambiente.grid(row=0, column=1, padx=(0, 14), pady=6, sticky="w")
        self._btn(c, "Escolher", self._escolher_certificado, "secundario", 100).grid(row=5, column=2, padx=(0, 14), pady=6)

        self._btn(painel, "Salvar configuração", self._salvar_config, "primario", 200).pack(anchor="w", pady=(10, 14))

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
        dados["ambiente"] = self.cfg_ambiente.get()
        dados["crt"] = self.cfg_crt.get().split(" ")[0]
        for chave, nome in [("razao_social", "Razão social"), ("cnpj", "CNPJ"), ("uf", "UF")]:
            if not dados.get(chave):
                messagebox.showwarning("Campo obrigatório", f"Informe: {nome}.")
                return
        banco.salvar_config_fiscal(dados)
        messagebox.showinfo("Configuração", "Dados da empresa salvos.")

    # ==================================================================
    # Tela de Usuários (só master)
    # ==================================================================
    def mostrar_usuarios(self):
        if not self.eh_master:
            messagebox.showwarning("Acesso restrito", "Só o usuário master gerencia usuários.")
            return
        self._limpar_area(linha_expande=2)
        self.usuario_sel_id = None
        self._titulo("Usuários").grid(row=0, column=0, sticky="w", pady=(0, 14))

        form = self._card(self.area)
        form.grid(row=1, column=0, sticky="ew", pady=(0, 14))
        form.grid_columnconfigure((0, 1, 2, 3), weight=1)

        self.u_login = self._entry(form, "Login *")
        self.u_nome = self._entry(form, "Nome completo")
        self.u_email = self._entry(form, "E-mail")
        self.u_senha = self._entry(form, "Senha (no cadastro) *", senha=True)
        for i, campo in enumerate((self.u_login, self.u_nome, self.u_email, self.u_senha)):
            campo.grid(row=0, column=i, padx=(14 if i == 0 else 4, 14 if i == 3 else 4), pady=(12, 6), sticky="ew")

        self._rotulo(form, "Papel:").grid(row=1, column=0, padx=(14, 4), pady=6, sticky="e")
        self.u_papel = self._option(form, ["operador", "master"], width=130)
        self.u_papel.grid(row=1, column=1, padx=4, pady=6, sticky="w")

        botoes = ctk.CTkFrame(form, fg_color="transparent")
        botoes.grid(row=2, column=0, columnspan=4, padx=14, pady=(4, 12), sticky="w")
        for texto, comando, tipo, largura in [
            ("Criar", self._criar_usuario, "primario", 90),
            ("Salvar", self._salvar_usuario, "secundario", 90),
            ("Trocar senha", self._trocar_senha_usuario, "secundario", 120),
            ("Ativar/Desativar", self._alternar_ativo, "secundario", 150),
            ("Limpar", self._limpar_user_form, "secundario", 80),
        ]:
            self._btn(botoes, texto, comando, tipo, largura).pack(side="left", padx=(0, 12))

        self.tab_users = self._tabela(2, [
            ("login", "Login", 160, "w"), ("nome", "Nome", 260, "w"),
            ("papel", "Papel", 120, "center"), ("ativo", "Ativo", 80, "center"),
        ])
        self.tab_users.bind("<<TreeviewSelect>>", self._carregar_usuario_sel)
        self._rotulo(self.area, "Clique num usuário para editar. A senha só muda em 'Trocar senha'.", 11, cor="muted").grid(row=3, column=0, sticky="w", pady=(8, 0))
        self._atualizar_usuarios()

    def _atualizar_usuarios(self):
        # A lista fica em memória: selecionar/editar não precisa consultar o banco de novo.
        self._usuarios = {u["login"]: u for u in banco.listar_usuarios()}
        self._preencher(self.tab_users, [
            (u["login"], u.get("nome") or "", u["papel"], "sim" if u["ativo"] else "não")
            for u in self._usuarios.values()
        ])

    def _usuario_selecionado(self):
        """Usuário selecionado na lista, ou None (avisando o operador)."""
        u = next((x for x in self._usuarios.values() if x["id"] == self.usuario_sel_id), None)
        if u is None:
            messagebox.showinfo("Selecione um usuário", "Clique num usuário da lista primeiro.")
        return u

    def _carregar_usuario_sel(self, _evento=None):
        selecao = self.tab_users.selection()
        u = selecao and self._usuarios.get(self.tab_users.item(selecao[0], "values")[0])
        if not u:
            return
        self.usuario_sel_id = u["id"]
        for campo, valor in ((self.u_login, u["login"]), (self.u_nome, u.get("nome")), (self.u_email, u.get("email"))):
            campo.delete(0, tk.END)
            campo.insert(0, valor or "")
        self.u_papel.set(u["papel"])

    def _limpar_user_form(self):
        self.usuario_sel_id = None
        for campo in (self.u_login, self.u_nome, self.u_email, self.u_senha):
            campo.delete(0, tk.END)
        self.u_papel.set("operador")
        if self.tab_users.selection():
            self.tab_users.selection_remove(self.tab_users.selection())

    def _criar_usuario(self):
        login = self.u_login.get().strip()
        senha = self.u_senha.get()
        if not login or len(senha) < SENHA_MINIMA:
            messagebox.showwarning("Campos obrigatórios", f"Informe login e senha (mín. {SENHA_MINIMA} caracteres).")
            return
        try:
            banco.criar_usuario(login, senha, self.u_papel.get(), self.u_nome.get().strip() or None,
                                self.u_email.get().strip() or None, trocar_senha=True)
        except banco.LoginDuplicado:
            messagebox.showwarning("Login repetido", f"O login {login} já existe.")
            return
        self._limpar_user_form()
        self._atualizar_usuarios()

    def _gravar_usuario(self, usuario_id, nome, email, papel, ativo):
        try:
            banco.atualizar_usuario(usuario_id, nome, email, papel, ativo)
        except banco.UltimoMaster:
            messagebox.showwarning("Não permitido", "O sistema precisa de pelo menos um master ativo.")
            return
        self._limpar_user_form()
        self._atualizar_usuarios()

    def _salvar_usuario(self):
        u = self._usuario_selecionado()
        if u:
            self._gravar_usuario(u["id"], self.u_nome.get().strip() or None,
                                 self.u_email.get().strip() or None, self.u_papel.get(), u["ativo"])

    def _alternar_ativo(self):
        u = self._usuario_selecionado()
        if u:
            self._gravar_usuario(u["id"], u.get("nome"), u.get("email"), u["papel"], not u["ativo"])

    def _trocar_senha_usuario(self):
        u = self._usuario_selecionado()
        if not u:
            return
        nova = self._pedir_senha("Trocar senha", f"Nova senha de {u['login']}")
        if nova:
            # Senha definida pelo master é provisória: o usuário troca no próximo login.
            banco.alterar_senha_usuario(u["id"], nova, exigir_troca=True)
            messagebox.showinfo("Senha", "Senha alterada. O usuário deverá trocá-la no próximo login.")


class TelaLogin(_Estilo, ctk.CTk):
    """Janela de login mostrada antes de abrir o PDV."""

    def __init__(self):
        super().__init__()
        self._fontes = {}
        self.usuario = None
        self.title("PDV Próprio — Entrar")
        self.geometry("380x460")
        self.resizable(False, False)
        self.configure(fg_color=P["canvas"])

        card = self._card(self, corner_radius=16)
        card.pack(expand=True, fill="both", padx=24, pady=24)

        ctk.CTkLabel(card, text="PDV", width=56, height=56, corner_radius=15, fg_color=P["accent"],
                     text_color=P["primary_strong"], font=self._fonte(18, True)).pack(pady=(30, 10))
        self._rotulo(card, "PDV Próprio", 18, True).pack()
        self._rotulo(card, "Entre para continuar", 11, cor="muted").pack(pady=(2, 20))

        self.login = self._entry(card, "Usuário", width=250)
        self.login.pack(pady=6)
        self.senha = self._entry(card, "Senha", senha=True, width=250)
        self.senha.pack(pady=6)
        self._btn(card, "Entrar", self._entrar, width=250).pack(pady=(16, 6))

        self.login.bind("<Return>", lambda e: self.senha.focus())
        self.senha.bind("<Return>", lambda e: self._entrar())
        self.login.focus()

    def _entrar(self):
        usuario = banco.autenticar(self.login.get().strip(), self.senha.get())
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
        self.usuario = usuario
        self.destroy()


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

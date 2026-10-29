"""PDV Próprio — aplicativo de desktop.

Janela feita com CustomTkinter, conversando direto com o banco SQLite
pela camada em banco.py. Visual inspirado no design (verde, clean, Manrope):
tela de Venda com catálogo em cartões à esquerda e checkout à direita.

Rodar com:  python3 -m pdv   (ou python3 pdv_app.py, na raiz)
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog

import urllib.error

import customtkinter as ctk

from . import banco
from . import exportacao
from . import nfce
from . import sync

ctk.set_appearance_mode("light")

FORMAS_PAGAMENTO = ["Dinheiro", "Cartão", "Pix"]
FONTE = "Manrope"

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


class AppPDV(ctk.CTk):
    def __init__(self, usuario):
        super().__init__()
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

        self._estilizar_tabelas()
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._montar_barra_lateral()
        self.area = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self.area.grid(row=0, column=1, sticky="nsew", padx=24, pady=24)

        self.mostrar_vendas()

    # ---------- Helpers de estilo ----------
    def _fonte(self, tamanho=13, negrito=False):
        return ctk.CTkFont(family=FONTE, size=tamanho, weight="bold" if negrito else "normal")

    def _btn(self, parent, text, command, tipo="primario", width=140):
        estilos = {
            "primario": dict(fg_color=P["primary"], hover_color=P["primary_strong"], text_color="#ffffff"),
            "secundario": dict(fg_color=P["surface"], hover_color=P["primary_soft"], text_color=P["primary"], border_width=1, border_color=P["border"]),
            "perigo": dict(fg_color=P["danger"], hover_color=P["danger_strong"], text_color="#ffffff"),
            "sidebar": dict(fg_color="transparent", hover_color=P["primary_strong"], text_color="#ffffff", anchor="w"),
            "accent": dict(fg_color=P["accent"], hover_color=P["accent_strong"], text_color=P["primary_strong"]),
        }
        return ctk.CTkButton(
            parent, text=text, command=command, width=width,
            corner_radius=11, font=self._fonte(13, True), **estilos[tipo],
        )

    def _card(self, parent):
        return ctk.CTkFrame(parent, fg_color=P["surface"], corner_radius=15,
                            border_width=1, border_color=P["border"])

    def _entry(self, parent, placeholder):
        return ctk.CTkEntry(
            parent, placeholder_text=placeholder, corner_radius=10,
            fg_color="#ffffff", border_color=P["border"], text_color=P["text"],
            font=self._fonte(13),
        )

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

    def _titulo(self, texto):
        return ctk.CTkLabel(self.area, text=texto, font=self._fonte(26, True), text_color=P["text"])

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
        self._btn(rodape, "Sincronizar", self.sincronizar_agora, tipo="accent", width=168).pack(padx=16, pady=(0, 10), fill="x")
        ctk.CTkLabel(
            rodape, text=f"{self.usuario['login']}  ·  {self.usuario['papel']}",
            text_color="#8fb6a6", font=self._fonte(10),
        ).pack(padx=16, anchor="w")
        self._btn(rodape, "Trocar senha", self._trocar_minha_senha, tipo="sidebar", width=168).pack(padx=16, pady=(2, 0), fill="x")
        self._btn(rodape, "Sair", self._sair, tipo="sidebar", width=168).pack(padx=16, pady=(2, 0), fill="x")

    def _trocar_minha_senha(self):
        dialogo = ctk.CTkInputDialog(title="Trocar senha", text="Nova senha:")
        nova = dialogo.get_input()
        if nova:
            banco.alterar_senha_usuario(self.usuario["id"], nova)
            messagebox.showinfo("Senha", "Sua senha foi alterada.")

    def _sair(self):
        self.destroy()
        iniciar()  # volta para a tela de login

    def sincronizar_agora(self):
        pendentes = banco.contar_pendentes()
        if pendentes["produtos"] == 0 and pendentes["vendas"] == 0:
            messagebox.showinfo("Sincronização", "Nada pendente para enviar.")
            return
        try:
            resultado = sync.sincronizar()
        except urllib.error.URLError:
            messagebox.showwarning(
                "Servidor indisponível",
                "Não foi possível conectar ao servidor central.\n"
                "Os registros continuam pendentes e serão enviados depois.",
            )
            return
        messagebox.showinfo(
            "Sincronização concluída",
            f"Enviado(s): {resultado['produtos']} produto(s) e {resultado['vendas']} venda(s).",
        )

    def _limpar_area(self):
        for widget in self.area.winfo_children():
            widget.destroy()

    def _pedir_valor(self, titulo, texto):
        dialogo = ctk.CTkInputDialog(title=titulo, text=texto)
        resposta = dialogo.get_input()
        if resposta is None or resposta.strip() == "":
            return None
        try:
            return banco.para_centavos(resposta)
        except ValueError:
            messagebox.showwarning("Valor inválido", "Use um número, ex: 5,50.")
            return None

    # ==================================================================
    # Tela de Venda  (catálogo em cartões + checkout)
    # ==================================================================
    def mostrar_vendas(self):
        self._limpar_area()
        self.carrinho = []
        self.forma_venda = "Dinheiro"
        self.produtos_venda = banco.listar_produtos()

        self.area.grid_columnconfigure(0, weight=1)
        self.area.grid_columnconfigure(1, weight=0)
        self.area.grid_rowconfigure(1, weight=1)

        sessao = banco.sessao_aberta()
        cabecalho = "Venda" if sessao else "Venda  (caixa fechado)"
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
        self.campo_venda_cod.bind("<KeyRelease>", lambda e: self._desenhar_catalogo(self.campo_venda_cod.get()))
        self._btn(busca, "Adicionar", self.adicionar_por_codigo, width=110).grid(row=0, column=1, padx=(6, 14), pady=12)

        self.grade = ctk.CTkScrollableFrame(catalogo, fg_color="transparent")
        self.grade.grid(row=1, column=0, sticky="nsew")
        for i in range(3):
            self.grade.grid_columnconfigure(i, weight=1, uniform="cards")
        self._desenhar_catalogo()

        # ---- Checkout (direita) ----
        self.checkout = self._card(self.area)
        self.checkout.configure(width=350)
        self.checkout.grid(row=1, column=1, sticky="nsew")
        self.checkout.grid_propagate(False)
        self.checkout.grid_columnconfigure(0, weight=1)
        self.checkout.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(self.checkout, text="Venda atual", font=self._fonte(16, True), text_color=P["text"]).grid(
            row=0, column=0, padx=16, pady=(16, 8), sticky="w"
        )

        self.lista_carrinho = ctk.CTkScrollableFrame(self.checkout, fg_color="transparent")
        self.lista_carrinho.grid(row=1, column=0, sticky="nsew", padx=10)
        self.lista_carrinho.grid_columnconfigure(0, weight=1)

        rodape = ctk.CTkFrame(self.checkout, fg_color="transparent")
        rodape.grid(row=2, column=0, sticky="ew", padx=16, pady=(8, 16))
        rodape.grid_columnconfigure((0, 1, 2), weight=1)

        ctk.CTkLabel(rodape, text="Forma de pagamento", font=self._fonte(11), text_color=P["muted"]).grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 6)
        )
        self.botoes_forma = {}
        for i, forma in enumerate(FORMAS_PAGAMENTO):
            b = ctk.CTkButton(
                rodape, text=forma, width=70, corner_radius=10, font=self._fonte(11, True),
                command=lambda f=forma: self._selecionar_forma(f),
            )
            b.grid(row=1, column=i, padx=2, pady=(0, 14), sticky="ew")
            self.botoes_forma[forma] = b
        self._selecionar_forma(self.forma_venda)

        self.label_total = ctk.CTkLabel(rodape, text="R$ 0,00", font=self._fonte(26, True), text_color=P["primary"])
        self.label_total.grid(row=2, column=0, columnspan=3, sticky="e", pady=(0, 0))

        self.label_tributos = ctk.CTkLabel(rodape, text="Trib. aprox.: R$ 0,00", font=self._fonte(10), text_color=P["muted"])
        self.label_tributos.grid(row=3, column=0, columnspan=3, sticky="e", pady=(0, 10))

        self._btn(rodape, "Finalizar venda", self.finalizar_venda, "primario", 200).grid(
            row=4, column=0, columnspan=3, sticky="ew"
        )
        self._btn(rodape, "Emitir NFC-e", self._emitir_nfce, "secundario", 200).grid(
            row=5, column=0, columnspan=3, sticky="ew", pady=(6, 0)
        )

        self.campo_venda_cod.focus()
        self._redesenhar_carrinho()

    def _desenhar_catalogo(self, filtro=""):
        for w in self.grade.winfo_children():
            w.destroy()
        termo = filtro.strip().lower()
        prods = [
            p for p in self.produtos_venda
            if termo in p["descricao"].lower() or (p["codigo"] or "").startswith(filtro.strip())
        ] if termo else self.produtos_venda

        if not prods:
            ctk.CTkLabel(self.grade, text="Nenhum produto.", text_color=P["muted"], font=self._fonte(12)).grid(
                row=0, column=0, pady=24
            )
            return
        for idx, p in enumerate(prods):
            card = ctk.CTkButton(
                self.grade,
                text=f"{p['descricao']}\nR$ {banco.formatar_reais(p['preco_centavos'])}",
                command=lambda pr=p: self._adicionar_ao_carrinho(pr),
                fg_color="#ffffff", hover_color=P["primary_soft"], text_color=P["text"],
                border_width=1, border_color=P["border"], corner_radius=15, height=78,
                font=self._fonte(12, True),
            )
            card.grid(row=idx // 3, column=idx % 3, padx=6, pady=6, sticky="nsew")

    def _selecionar_forma(self, forma):
        self.forma_venda = forma
        for f, b in self.botoes_forma.items():
            if f == forma:
                b.configure(fg_color=P["primary"], text_color="#ffffff", hover_color=P["primary_strong"], border_width=0)
            else:
                b.configure(fg_color=P["surface"], text_color=P["muted"], hover_color=P["primary_soft"], border_width=1, border_color=P["border"])

    def _adicionar_ao_carrinho(self, produto):
        for item in self.carrinho:
            if item["produto_id"] == produto["id"]:
                item["quantidade"] += 1
                self._redesenhar_carrinho()
                return
        self.carrinho.append(
            {
                "produto_id": produto["id"],
                "descricao": produto["descricao"],
                "quantidade": 1,
                "preco_unit_centavos": produto["preco_centavos"],
                "aliquota_aprox": produto.get("aliquota_aprox") or 0,
            }
        )
        self._redesenhar_carrinho()

    def adicionar_por_codigo(self):
        codigo = self.campo_venda_cod.get().strip()
        if not codigo:
            return
        produto = banco.buscar_produto_por_codigo(codigo)
        if produto:
            self._adicionar_ao_carrinho(produto)
            self.campo_venda_cod.delete(0, tk.END)
            self._desenhar_catalogo()
        self.campo_venda_cod.focus()

    def _alterar_qtd(self, item, delta):
        item["quantidade"] += delta
        if item["quantidade"] <= 0:
            self.carrinho.remove(item)
        self._redesenhar_carrinho()

    def remover_item(self, item):
        self.carrinho.remove(item)
        self._redesenhar_carrinho()

    def _total_centavos(self):
        return sum(round(i["quantidade"] * i["preco_unit_centavos"]) for i in self.carrinho)

    def _tributos_centavos(self):
        # Lei da Transparência: valor aproximado dos tributos sobre o total.
        return sum(
            round(i["quantidade"] * i["preco_unit_centavos"] * (i.get("aliquota_aprox") or 0) / 100)
            for i in self.carrinho
        )

    def _redesenhar_carrinho(self):
        for w in self.lista_carrinho.winfo_children():
            w.destroy()

        if not self.carrinho:
            ctk.CTkLabel(
                self.lista_carrinho, text="Carrinho vazio\nToque num produto para adicionar",
                text_color=P["muted"], font=self._fonte(12),
            ).grid(row=0, column=0, pady=40)
        else:
            for idx, item in enumerate(self.carrinho):
                sub = round(item["quantidade"] * item["preco_unit_centavos"])
                linha = ctk.CTkFrame(self.lista_carrinho, fg_color="#ffffff", corner_radius=12,
                                     border_width=1, border_color=P["border"])
                linha.grid(row=idx, column=0, sticky="ew", pady=5)
                linha.grid_columnconfigure(1, weight=1)

                ctk.CTkLabel(linha, text=item["descricao"], font=self._fonte(12, True), text_color=P["text"], anchor="w").grid(
                    row=0, column=0, columnspan=3, padx=12, pady=(10, 2), sticky="w"
                )

                ctrl = ctk.CTkFrame(linha, fg_color="transparent")
                ctrl.grid(row=1, column=0, padx=10, pady=(0, 10), sticky="w")
                ctk.CTkButton(ctrl, text="−", width=26, height=24, corner_radius=8, fg_color=P["primary_soft"],
                              text_color=P["primary"], hover_color=P["accent_soft"], font=self._fonte(13, True),
                              command=lambda it=item: self._alterar_qtd(it, -1)).pack(side="left")
                ctk.CTkLabel(ctrl, text=f"{item['quantidade']:g}", width=32, font=self._fonte(12, True), text_color=P["text"]).pack(side="left", padx=2)
                ctk.CTkButton(ctrl, text="+", width=26, height=24, corner_radius=8, fg_color=P["primary_soft"],
                              text_color=P["primary"], hover_color=P["accent_soft"], font=self._fonte(13, True),
                              command=lambda it=item: self._alterar_qtd(it, 1)).pack(side="left")

                direita = ctk.CTkFrame(linha, fg_color="transparent")
                direita.grid(row=1, column=2, padx=10, pady=(0, 10), sticky="e")
                ctk.CTkLabel(direita, text=f"R$ {banco.formatar_reais(sub)}", font=self._fonte(12, True), text_color=P["primary"]).pack(side="left", padx=(0, 6))
                ctk.CTkButton(direita, text="✕", width=26, height=24, corner_radius=8, fg_color="transparent",
                              text_color=P["danger"], hover_color=P["primary_soft"], font=self._fonte(12, True),
                              command=lambda it=item: self.remover_item(it)).pack(side="left")

        self.label_total.configure(text=f"R$ {banco.formatar_reais(self._total_centavos())}")
        self.label_tributos.configure(text=f"Trib. aprox.: R$ {banco.formatar_reais(self._tributos_centavos())}")

    def _emitir_nfce(self):
        if not self.carrinho:
            messagebox.showwarning("Emitir NFC-e", "Carrinho vazio.")
            return
        config = banco.ler_config_fiscal()
        produtos = [banco.obter_produto(i["produto_id"]) for i in self.carrinho]
        produtos = [p for p in produtos if p]
        pendencias = nfce.pendencias_emissao(config, produtos)
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
        total = self._total_centavos()
        sessao = banco.sessao_aberta()
        sessao_id = sessao["id"] if sessao else None
        pagamentos = [{"forma": self.forma_venda, "valor_centavos": total}]
        try:
            venda_id, total_gravado = banco.registrar_venda(self.carrinho, pagamentos, sessao_id)
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
        self._limpar_area()
        self._avancado_visivel = False
        self._produtos_filtrados = []
        self.area.grid_columnconfigure(0, weight=1)
        self.area.grid_rowconfigure(2, weight=1)

        self._titulo("Produtos").grid(row=0, column=0, sticky="w", pady=(0, 14))

        filtros = self._card(self.area)
        filtros.grid(row=1, column=0, sticky="ew", pady=(0, 14))
        for i in range(4):
            filtros.grid_columnconfigure(i, weight=1)

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
        for i in range(5):
            self.adv.grid_columnconfigure(i, weight=1)
        self.flt_ncm = self._entry(self.adv, "NCM")
        self.flt_cfop = self._entry(self.adv, "CFOP")
        self.flt_cst = self._entry(self.adv, "CST/CSOSN")
        self.flt_origem = self._entry(self.adv, "Origem")
        self.flt_categoria = self._entry(self.adv, "Categoria (merc.)")
        for i, campo in enumerate([self.flt_ncm, self.flt_cfop, self.flt_cst, self.flt_origem, self.flt_categoria]):
            campo.grid(row=0, column=i, padx=4, pady=6, sticky="ew")
        self.adv.grid_remove()

        botoes = ctk.CTkFrame(filtros, fg_color="transparent")
        botoes.grid(row=2, column=0, columnspan=4, padx=14, pady=(2, 12), sticky="w")
        self._btn(botoes, "Pesquisar", self._pesquisar_produtos, width=110).pack(side="left", padx=(0, 6))
        self._btn(botoes, "Filtro avançado", self._toggle_avancado, "secundario", 140).pack(side="left", padx=6)
        self._btn(botoes, "Novo produto", self._novo_produto, "accent", 130).pack(side="left", padx=6)
        self._btn(botoes, "Exportar CSV", self._exportar_produtos, "secundario", 130).pack(side="left", padx=6)

        colunas = ("id", "codigo", "descricao", "unidade", "preco", "estoque", "ativo")
        self.tabela_prod = ttk.Treeview(self.area, columns=colunas, show="headings")
        for chave, titulo, larg, anchor in [
            ("id", "ID", 50, "center"), ("codigo", "Cód. EAN", 140, "center"),
            ("descricao", "Descrição", 300, "w"), ("unidade", "Un", 55, "center"),
            ("preco", "Preço (R$)", 100, "e"), ("estoque", "Estoque", 85, "e"),
            ("ativo", "Ativo", 60, "center"),
        ]:
            self.tabela_prod.heading(chave, text=titulo)
            self.tabela_prod.column(chave, width=larg, anchor=anchor)
        self.tabela_prod.grid(row=2, column=0, sticky="nsew")
        self.tabela_prod.bind("<Double-1>", lambda e: self._editar_produto())

        rol = ttk.Scrollbar(self.area, orient="vertical", command=self.tabela_prod.yview)
        self.tabela_prod.configure(yscrollcommand=rol.set)
        rol.grid(row=2, column=1, sticky="ns")

        ctk.CTkLabel(
            self.area,
            text="Duplo clique num produto para editar. A exportação CSV usa o filtro atual (padrão SPED 0200).",
            text_color=P["muted"], font=self._fonte(11),
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
        status = {"Ativos": "ativos", "Inativos": "inativos", "Todos": "todos"}.get(self.flt_status.get(), "ativos")
        controla = {"Todos": None, "Controla estoque": 1, "Não controla": 0}.get(self.flt_controla.get())
        filtros = {"texto": self.flt_texto.get().strip(), "status": status, "controla": controla}
        if self._avancado_visivel:
            filtros.update(
                ncm=self.flt_ncm.get().strip(), cfop=self.flt_cfop.get().strip(),
                cst=self.flt_cst.get().strip(), origem=self.flt_origem.get().strip(),
                categoria=self.flt_categoria.get().strip(),
            )
        return filtros

    def _pesquisar_produtos(self):
        self._produtos_filtrados = banco.buscar_produtos(self._coletar_filtros())
        for linha in self.tabela_prod.get_children():
            self.tabela_prod.delete(linha)
        for p in self._produtos_filtrados:
            estoque = p.get("estoque") or 0
            self.tabela_prod.insert(
                "", tk.END,
                values=(
                    p["id"], p.get("codigo") or "", p["descricao"], p.get("unidade") or "",
                    banco.formatar_reais(p["preco_centavos"]), f"{estoque:g}",
                    "Sim" if p.get("ativo") else "Não",
                ),
            )

    def _novo_produto(self):
        self.mostrar_form_produto(None)

    def _editar_produto(self):
        selecao = self.tabela_prod.selection()
        if not selecao:
            return
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
        except Exception as erro:
            messagebox.showerror("Erro", f"Não foi possível exportar.\n{erro}")
            return
        messagebox.showinfo("Exportação concluída", f"{qtd} produto(s) exportado(s) para:\n{caminho}")

    # ---------- Formulário de produto (novo / editar) ----------
    def mostrar_form_produto(self, produto_id=None):
        self._limpar_area()
        self.produto_sel_id = produto_id
        self.area.grid_columnconfigure(0, weight=1)
        self.area.grid_rowconfigure(1, weight=1)
        self._titulo("Editar produto" if produto_id else "Novo produto").grid(row=0, column=0, sticky="w", pady=(0, 10))

        painel = ctk.CTkScrollableFrame(self.area, fg_color="transparent")
        painel.grid(row=1, column=0, sticky="nsew")
        painel.grid_columnconfigure(0, weight=1)

        form = self._card(painel)
        form.pack(fill="x")
        for i in range(4):
            form.grid_columnconfigure(i, weight=1)

        self.pf = {}

        def add_campos(campos, linha_inicial):
            for i, (chave, rotulo) in enumerate(campos):
                campo = self._entry(form, rotulo)
                campo.grid(row=linha_inicial + i // 4, column=i % 4,
                           padx=(14 if i % 4 == 0 else 4, 14 if i % 4 == 3 else 4), pady=5, sticky="ew")
                self.pf[chave] = campo
            return linha_inicial + (len(campos) - 1) // 4

        basicos = [
            ("descricao", "Descrição *"), ("codigo", "Código de barras (EAN)"),
            ("codigo_interno", "Código interno"), ("categoria", "Categoria (merc.)"),
            ("unidade", "Unidade *"), ("preco", "Preço venda * (R$)"),
            ("custo", "Custo (R$)"), ("estoque", "Estoque"),
        ]
        fiscais = [
            ("ncm", "NCM *"), ("cest", "CEST"), ("cfop", "CFOP *"), ("origem", "Origem * (0-8)"),
            ("cst", "CST/CSOSN *"), ("tipo_item", "Tipo item (00-99)"),
            ("aliquota_icms", "ICMS %"), ("aliquota_aprox", "Tributos aprox. %"),
        ]

        ctk.CTkLabel(form, text="Dados básicos", text_color=P["muted"], font=self._fonte(11, True)).grid(row=0, column=0, columnspan=4, padx=14, pady=(12, 0), sticky="w")
        ln = add_campos(basicos, 1)
        self.pf_controla = ctk.CTkCheckBox(form, text="Controla estoque", font=self._fonte(11), text_color=P["text"], fg_color=P["primary"], hover_color=P["primary_strong"])
        self.pf_controla.grid(row=ln + 1, column=0, columnspan=2, padx=14, pady=(4, 2), sticky="w")

        ctk.CTkLabel(form, text="Fiscal (NFC-e / SPED)", text_color=P["muted"], font=self._fonte(11, True)).grid(row=ln + 2, column=0, columnspan=4, padx=14, pady=(8, 0), sticky="w")
        ln = add_campos(fiscais, ln + 3)

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
        def v(chave):
            return self.pf[chave].get().strip()

        # Campos obrigatórios
        obrigatorios = {
            "descricao": "Descrição", "unidade": "Unidade", "ncm": "NCM",
            "cfop": "CFOP", "origem": "Origem", "cst": "CST/CSOSN",
        }
        for chave, nome in obrigatorios.items():
            if not v(chave):
                messagebox.showwarning("Campo obrigatório", f"Informe: {nome}.")
                self.pf[chave].focus()
                return None

        # Preço de venda: obrigatório e válido
        try:
            preco_centavos = banco.para_centavos(v("preco"))
        except ValueError:
            messagebox.showwarning("Preço inválido", "Preço de venda: use um número, ex: 5,50.")
            self.pf["preco"].focus()
            return None

        def numero(chave, padrao=0.0):
            texto = v(chave).replace(",", ".")
            try:
                return float(texto) if texto else padrao
            except ValueError:
                return padrao

        def centavos(chave):
            try:
                return banco.para_centavos(v(chave)) if v(chave) else 0
            except ValueError:
                return 0

        return {
            "descricao": v("descricao"),
            "codigo": v("codigo") or None,
            "codigo_interno": v("codigo_interno") or None,
            "categoria": v("categoria") or None,
            "unidade": v("unidade") or "UN",
            "tipo_item": v("tipo_item") or "00",
            "preco_centavos": preco_centavos,
            "custo_centavos": centavos("custo"),
            "estoque": numero("estoque"),
            "controla_estoque": 1 if self.pf_controla.get() else 0,
            "ncm": v("ncm"),
            "cest": v("cest") or None,
            "cfop": v("cfop"),
            "origem": v("origem") or "0",
            "cst": v("cst"),
            "aliquota_icms": numero("aliquota_icms"),
            "aliquota_aprox": numero("aliquota_aprox"),
        }

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
        if not messagebox.askyesno("Excluir produto", "Deseja mesmo excluir este produto?"):
            return
        banco.inativar_produto(self.produto_sel_id)
        self.mostrar_produtos()

    def _carregar_produto_no_form(self, produto_id):
        produto = banco.obter_produto(produto_id)
        if not produto:
            return

        def num(valor):
            return "" if not valor else f"{valor:g}"

        valores = {
            "descricao": produto.get("descricao") or "",
            "codigo": produto.get("codigo") or "",
            "codigo_interno": produto.get("codigo_interno") or "",
            "categoria": produto.get("categoria") or "",
            "unidade": produto.get("unidade") or "",
            "tipo_item": produto.get("tipo_item") or "00",
            "preco": banco.formatar_reais(produto.get("preco_centavos") or 0),
            "custo": banco.formatar_reais(produto.get("custo_centavos") or 0),
            "estoque": num(produto.get("estoque")),
            "ncm": produto.get("ncm") or "",
            "cest": produto.get("cest") or "",
            "cfop": produto.get("cfop") or "",
            "origem": produto.get("origem") or "",
            "cst": produto.get("cst") or "",
            "aliquota_icms": num(produto.get("aliquota_icms")),
            "aliquota_aprox": num(produto.get("aliquota_aprox")),
        }
        for chave, campo in self.pf.items():
            campo.delete(0, tk.END)
            campo.insert(0, valores.get(chave, ""))

        if produto.get("controla_estoque"):
            self.pf_controla.select()
        else:
            self.pf_controla.deselect()

    # ==================================================================
    # Tela de Caixa
    # ==================================================================
    def mostrar_caixa(self):
        self._limpar_area()
        self.area.grid_columnconfigure(0, weight=1)
        self.area.grid_columnconfigure(1, weight=0)
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
        ctk.CTkLabel(caixa, text="Caixa fechado. Abra para começar a operar.", text_color=P["text"], font=self._fonte(13)).grid(
            row=0, column=0, columnspan=2, padx=14, pady=(16, 8), sticky="w"
        )
        ctk.CTkLabel(caixa, text="Operador:", text_color=P["text"], font=self._fonte(12)).grid(row=1, column=0, padx=14, pady=8, sticky="e")
        self.campo_operador = self._entry(caixa, "Nome do operador")
        self.campo_operador.grid(row=1, column=1, padx=14, pady=8, sticky="ew")
        ctk.CTkLabel(caixa, text="Fundo de troco (R$):", text_color=P["text"], font=self._fonte(12)).grid(row=2, column=0, padx=14, pady=8, sticky="e")
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
        operador = sessao["operador"] or "—"
        ctk.CTkLabel(
            info, text=f"Caixa aberto por {operador}  ·  desde {sessao['aberto_em']}",
            font=self._fonte(14, True), text_color=P["primary"],
        ).pack(padx=14, pady=14, anchor="w")

        resumo = banco.resumo_caixa(sessao["id"])
        painel = self._card(self.area)
        painel.grid(row=2, column=0, sticky="ew", pady=(0, 14))
        painel.grid_columnconfigure(1, weight=1)
        linhas = [
            ("Fundo de troco (abertura)", resumo["abertura"]),
            ("Suprimentos (+)", resumo["suprimentos"]),
            ("Sangrias (−)", resumo["sangrias"]),
            ("Vendas em dinheiro (+)", resumo["vendas_dinheiro"]),
            ("Esperado na gaveta", resumo["esperado_gaveta"]),
            ("Total vendido (todas as formas)", resumo["vendas_total"]),
        ]
        for i, (rotulo, centavos) in enumerate(linhas):
            negrito = rotulo == "Esperado na gaveta"
            fonte = self._fonte(14, negrito)
            cor = P["primary"] if negrito else P["text"]
            ctk.CTkLabel(painel, text=rotulo, font=fonte, text_color=cor).grid(row=i, column=0, padx=14, pady=6, sticky="w")
            ctk.CTkLabel(painel, text=f"R$ {banco.formatar_reais(centavos)}", font=fonte, text_color=cor).grid(row=i, column=1, padx=14, pady=6, sticky="e")

        botoes = ctk.CTkFrame(self.area, fg_color="transparent")
        botoes.grid(row=3, column=0, sticky="ew")
        self._btn(botoes, "Suprimento", lambda: self._movimento(sessao, "suprimento"), "secundario", 120).pack(side="left", padx=(0, 6), pady=6)
        self._btn(botoes, "Sangria", lambda: self._movimento(sessao, "sangria"), "secundario", 120).pack(side="left", padx=6, pady=6)
        self._btn(botoes, "Fechar caixa", lambda: self.fechar_caixa(sessao), "perigo", 140).pack(side="right", padx=0, pady=6)

    def _movimento(self, sessao, tipo):
        valor = self._pedir_valor(tipo.capitalize(), f"Valor do {tipo} (R$):")
        if valor is None or valor <= 0:
            return
        banco.registrar_movimento_caixa(sessao["id"], tipo, valor)
        self.mostrar_caixa()

    def fechar_caixa(self, sessao):
        resumo = banco.resumo_caixa(sessao["id"])
        contado = self._pedir_valor(
            "Fechar caixa",
            f"Esperado na gaveta: R$ {banco.formatar_reais(resumo['esperado_gaveta'])}\n"
            "Digite o valor contado (R$):",
        )
        if contado is None:
            return
        banco.fechar_caixa(sessao["id"], contado)
        diferenca = contado - resumo["esperado_gaveta"]
        if diferenca == 0:
            situacao = "Caixa bateu certo."
        elif diferenca > 0:
            situacao = f"Sobra de R$ {banco.formatar_reais(diferenca)}."
        else:
            situacao = f"Falta de R$ {banco.formatar_reais(-diferenca)}."
        messagebox.showinfo("Caixa fechado", situacao)
        self.mostrar_caixa()

    # ==================================================================
    # Tela de Histórico de vendas
    # ==================================================================
    def mostrar_historico(self):
        self._limpar_area()
        self.area.grid_columnconfigure(0, weight=1)
        self.area.grid_columnconfigure(1, weight=0)
        self.area.grid_rowconfigure(1, weight=1)

        self._titulo("Histórico de vendas").grid(row=0, column=0, sticky="w", pady=(0, 14))

        colunas = ("id", "data", "itens", "formas", "total")
        tabela = ttk.Treeview(self.area, columns=colunas, show="headings")
        tabela.heading("id", text="Venda")
        tabela.heading("data", text="Data/hora")
        tabela.heading("itens", text="Itens")
        tabela.heading("formas", text="Pagamento")
        tabela.heading("total", text="Total (R$)")
        tabela.column("id", width=70, anchor="center")
        tabela.column("data", width=170, anchor="center")
        tabela.column("itens", width=70, anchor="center")
        tabela.column("formas", width=160)
        tabela.column("total", width=120, anchor="e")
        tabela.grid(row=1, column=0, sticky="nsew")
        rol = ttk.Scrollbar(self.area, orient="vertical", command=tabela.yview)
        tabela.configure(yscrollcommand=rol.set)
        rol.grid(row=1, column=1, sticky="ns")

        vendas = banco.listar_vendas()
        if not vendas:
            tabela.insert("", tk.END, values=("", "(nenhuma venda ainda)", "", "", ""))
        for venda in vendas:
            data = venda["criado_em"].replace("T", " ")
            tabela.insert(
                "",
                tk.END,
                values=(
                    f"#{venda['id']}",
                    data,
                    venda["qtd_itens"],
                    venda["formas"] or "",
                    banco.formatar_reais(venda["total_centavos"]),
                ),
            )

    # ==================================================================
    # Tela de Relatório
    # ==================================================================
    def mostrar_relatorio(self):
        self._limpar_area()
        self.area.grid_columnconfigure(0, weight=1)
        self.area.grid_columnconfigure(1, weight=0)

        rel = banco.relatorio_dia()
        self._titulo(f"Relatório do dia  ·  {rel['data']}").grid(row=0, column=0, sticky="w", pady=(0, 14))

        topo = self._card(self.area)
        topo.grid(row=1, column=0, sticky="ew", pady=(0, 14))
        topo.grid_columnconfigure((0, 1), weight=1)
        ctk.CTkLabel(topo, text="Vendas concluídas", font=self._fonte(14), text_color=P["muted"]).grid(row=0, column=0, padx=14, pady=(14, 2), sticky="w")
        ctk.CTkLabel(topo, text=str(rel["qtd"]), font=self._fonte(22, True), text_color=P["primary"]).grid(row=1, column=0, padx=14, pady=(0, 14), sticky="w")
        ctk.CTkLabel(topo, text="Total vendido", font=self._fonte(14), text_color=P["muted"]).grid(row=0, column=1, padx=14, pady=(14, 2), sticky="e")
        ctk.CTkLabel(topo, text=f"R$ {banco.formatar_reais(rel['total'])}", font=self._fonte(22, True), text_color=P["primary"]).grid(row=1, column=1, padx=14, pady=(0, 14), sticky="e")

        ctk.CTkLabel(self.area, text="Por forma de pagamento", font=self._fonte(16, True), text_color=P["text"]).grid(row=2, column=0, sticky="w", pady=(0, 6))

        tabela = ttk.Treeview(self.area, columns=("forma", "valor"), show="headings", height=4)
        tabela.heading("forma", text="Forma")
        tabela.heading("valor", text="Valor (R$)")
        tabela.column("forma", width=200)
        tabela.column("valor", width=160, anchor="e")
        tabela.grid(row=3, column=0, sticky="ew")
        if rel["por_forma"]:
            for forma, valor in rel["por_forma"]:
                tabela.insert("", tk.END, values=(forma, banco.formatar_reais(valor)))
        else:
            tabela.insert("", tk.END, values=("(sem vendas hoje)", ""))

    # ==================================================================
    # Tela de Configuração fiscal (só master)
    # ==================================================================
    CRT_OPCOES = ["1 - Simples Nacional", "2 - Simples Nacional (excesso)", "3 - Regime Normal"]

    def mostrar_config(self):
        if not self.eh_master:
            messagebox.showwarning("Acesso restrito", "Só o usuário master acessa a configuração.")
            return
        self._limpar_area()
        self.area.grid_columnconfigure(0, weight=1)
        self.area.grid_rowconfigure(1, weight=1)
        self._titulo("Configuração da empresa").grid(row=0, column=0, sticky="w", pady=(0, 10))

        cfg = banco.ler_config_fiscal()
        painel = ctk.CTkScrollableFrame(self.area, fg_color="transparent")
        painel.grid(row=1, column=0, sticky="nsew")
        painel.grid_columnconfigure(0, weight=1)

        self.cfg = {}

        def secao(titulo):
            ctk.CTkLabel(painel, text=titulo, text_color=P["primary"], font=self._fonte(15, True)).pack(anchor="w", pady=(10, 4))
            card = self._card(painel)
            card.pack(fill="x", pady=(0, 6))
            card.grid_columnconfigure(1, weight=1)
            return card

        def campo(card, chave, rotulo, linha, senha=False):
            ctk.CTkLabel(card, text=rotulo + ":", text_color=P["text"], font=self._fonte(12)).grid(row=linha, column=0, padx=(14, 6), pady=6, sticky="e")
            if senha:
                entrada = ctk.CTkEntry(card, show="•", corner_radius=10, fg_color="#ffffff", border_color=P["border"], text_color=P["text"], font=self._fonte(13))
            else:
                entrada = self._entry(card, "")
            entrada.insert(0, cfg.get(chave) or "")
            entrada.grid(row=linha, column=1, columnspan=2, padx=(0, 14), pady=6, sticky="ew")
            self.cfg[chave] = entrada
            return entrada

        # Empresa
        c = secao("Empresa")
        campo(c, "razao_social", "Razão social *", 0)
        campo(c, "nome_fantasia", "Nome fantasia", 1)
        campo(c, "cnpj", "CNPJ *", 2)
        campo(c, "ie", "Inscrição Estadual", 3)
        campo(c, "im", "Inscrição Municipal", 4)
        ctk.CTkLabel(c, text="Regime (CRT):", text_color=P["text"], font=self._fonte(12)).grid(row=5, column=0, padx=(14, 6), pady=6, sticky="e")
        self.cfg_crt = self._option(c, self.CRT_OPCOES, width=240)
        atual_crt = cfg.get("crt") or "1"
        self.cfg_crt.set(next((o for o in self.CRT_OPCOES if o.startswith(atual_crt)), self.CRT_OPCOES[0]))
        self.cfg_crt.grid(row=5, column=1, padx=(0, 14), pady=6, sticky="w")

        # Endereço
        c = secao("Endereço")
        campo(c, "cep", "CEP", 0)
        campo(c, "logradouro", "Logradouro", 1)
        campo(c, "numero", "Número", 2)
        campo(c, "complemento", "Complemento", 3)
        campo(c, "bairro", "Bairro", 4)
        campo(c, "municipio", "Município", 5)
        campo(c, "cod_municipio", "Cód. município (IBGE)", 6)
        campo(c, "uf", "UF *", 7)

        # Contato
        c = secao("Contato")
        campo(c, "telefone", "Telefone", 0)
        campo(c, "email", "E-mail", 1)

        # Fiscal / NFC-e
        c = secao("Fiscal / NFC-e")
        ctk.CTkLabel(c, text="Ambiente:", text_color=P["text"], font=self._fonte(12)).grid(row=0, column=0, padx=(14, 6), pady=6, sticky="e")
        self.cfg_ambiente = self._option(c, ["homologacao", "producao"], width=160)
        self.cfg_ambiente.set(cfg.get("ambiente") or "homologacao")
        self.cfg_ambiente.grid(row=0, column=1, padx=(0, 14), pady=6, sticky="w")
        campo(c, "serie", "Série", 1)
        campo(c, "proximo_numero", "Próximo número NFC-e", 2)
        campo(c, "csc", "CSC", 3)
        campo(c, "csc_id", "ID do CSC", 4)
        ctk.CTkLabel(c, text="Certificado (.pfx):", text_color=P["text"], font=self._fonte(12)).grid(row=5, column=0, padx=(14, 6), pady=6, sticky="e")
        self.cfg["certificado_caminho"] = self._entry(c, "")
        self.cfg["certificado_caminho"].insert(0, cfg.get("certificado_caminho") or "")
        self.cfg["certificado_caminho"].grid(row=5, column=1, padx=(0, 6), pady=6, sticky="ew")
        self._btn(c, "Escolher", self._escolher_certificado, "secundario", 100).grid(row=5, column=2, padx=(0, 14), pady=6)
        campo(c, "certificado_senha", "Senha do certificado", 6, senha=True)

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
        self._limpar_area()
        self.usuario_sel_id = None
        self.area.grid_columnconfigure(0, weight=1)
        self.area.grid_rowconfigure(2, weight=1)
        self._titulo("Usuários").grid(row=0, column=0, sticky="w", pady=(0, 14))

        form = self._card(self.area)
        form.grid(row=1, column=0, sticky="ew", pady=(0, 14))
        for i in range(4):
            form.grid_columnconfigure(i, weight=1)

        self.u_login = self._entry(form, "Login *")
        self.u_nome = self._entry(form, "Nome completo")
        self.u_email = self._entry(form, "E-mail")
        self.u_senha = ctk.CTkEntry(form, placeholder_text="Senha (no cadastro) *", show="•", corner_radius=10, fg_color="#ffffff", border_color=P["border"], text_color=P["text"], font=self._fonte(13))
        self.u_login.grid(row=0, column=0, padx=(14, 4), pady=(12, 6), sticky="ew")
        self.u_nome.grid(row=0, column=1, padx=4, pady=(12, 6), sticky="ew")
        self.u_email.grid(row=0, column=2, padx=4, pady=(12, 6), sticky="ew")
        self.u_senha.grid(row=0, column=3, padx=(4, 14), pady=(12, 6), sticky="ew")

        ctk.CTkLabel(form, text="Papel:", text_color=P["text"], font=self._fonte(12)).grid(row=1, column=0, padx=(14, 4), pady=6, sticky="e")
        self.u_papel = self._option(form, ["operador", "master"], width=130)
        self.u_papel.grid(row=1, column=1, padx=4, pady=6, sticky="w")

        botoes = ctk.CTkFrame(form, fg_color="transparent")
        botoes.grid(row=2, column=0, columnspan=4, padx=14, pady=(4, 12), sticky="w")
        self._btn(botoes, "Criar", self._criar_usuario, width=90).pack(side="left", padx=(0, 6))
        self._btn(botoes, "Salvar", self._salvar_usuario, "secundario", 90).pack(side="left", padx=6)
        self._btn(botoes, "Trocar senha", self._trocar_senha_usuario, "secundario", 120).pack(side="left", padx=6)
        self._btn(botoes, "Ativar/Desativar", self._alternar_ativo, "secundario", 150).pack(side="left", padx=6)
        self._btn(botoes, "Limpar", self._limpar_user_form, "secundario", 80).pack(side="left", padx=6)

        colunas = ("login", "nome", "papel", "ativo")
        self.tab_users = ttk.Treeview(self.area, columns=colunas, show="headings")
        self.tab_users.heading("login", text="Login")
        self.tab_users.heading("nome", text="Nome")
        self.tab_users.heading("papel", text="Papel")
        self.tab_users.heading("ativo", text="Ativo")
        self.tab_users.column("login", width=160)
        self.tab_users.column("nome", width=260)
        self.tab_users.column("papel", width=120, anchor="center")
        self.tab_users.column("ativo", width=80, anchor="center")
        self.tab_users.grid(row=2, column=0, sticky="nsew")
        self.tab_users.bind("<<TreeviewSelect>>", self._carregar_usuario_sel)
        ctk.CTkLabel(self.area, text="Clique num usuário para editar. A senha só muda em 'Trocar senha'.", text_color=P["muted"], font=self._fonte(11)).grid(row=3, column=0, sticky="w", pady=(8, 0))
        self._atualizar_usuarios()

    def _atualizar_usuarios(self):
        for linha in self.tab_users.get_children():
            self.tab_users.delete(linha)
        for u in banco.listar_usuarios():
            self.tab_users.insert("", tk.END, values=(u["login"], u.get("nome") or "", u["papel"], "sim" if u["ativo"] else "não"))

    def _carregar_usuario_sel(self, evento=None):
        selecao = self.tab_users.selection()
        if not selecao:
            return
        login = self.tab_users.item(selecao[0], "values")[0]
        u = next((x for x in banco.listar_usuarios() if x["login"] == login), None)
        if not u:
            return
        self.usuario_sel_id = u["id"]
        self.u_login.delete(0, tk.END); self.u_login.insert(0, u["login"])
        self.u_nome.delete(0, tk.END); self.u_nome.insert(0, u.get("nome") or "")
        self.u_email.delete(0, tk.END); self.u_email.insert(0, u.get("email") or "")
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
        if not login or not senha:
            messagebox.showwarning("Campos obrigatórios", "Informe login e senha.")
            return
        try:
            banco.criar_usuario(login, senha, self.u_papel.get(), self.u_nome.get().strip() or None, self.u_email.get().strip() or None)
        except banco.LoginDuplicado:
            messagebox.showwarning("Login repetido", f"O login {login} já existe.")
            return
        self._limpar_user_form()
        self._atualizar_usuarios()

    def _salvar_usuario(self):
        if self.usuario_sel_id is None:
            messagebox.showinfo("Selecione um usuário", "Clique num usuário da lista para editar.")
            return
        atual = next((x for x in banco.listar_usuarios() if x["id"] == self.usuario_sel_id), None)
        ativo = atual["ativo"] if atual else 1
        banco.atualizar_usuario(self.usuario_sel_id, self.u_nome.get().strip() or None, self.u_email.get().strip() or None, self.u_papel.get(), ativo)
        self._limpar_user_form()
        self._atualizar_usuarios()

    def _trocar_senha_usuario(self):
        if self.usuario_sel_id is None:
            messagebox.showinfo("Selecione um usuário", "Clique num usuário da lista primeiro.")
            return
        dialogo = ctk.CTkInputDialog(title="Trocar senha", text="Nova senha:")
        nova = dialogo.get_input()
        if nova:
            banco.alterar_senha_usuario(self.usuario_sel_id, nova)
            messagebox.showinfo("Senha", "Senha alterada.")

    def _alternar_ativo(self):
        if self.usuario_sel_id is None:
            messagebox.showinfo("Selecione um usuário", "Clique num usuário da lista primeiro.")
            return
        u = next((x for x in banco.listar_usuarios() if x["id"] == self.usuario_sel_id), None)
        if not u:
            return
        banco.atualizar_usuario(u["id"], u.get("nome"), u.get("email"), u["papel"], 0 if u["ativo"] else 1)
        self._limpar_user_form()
        self._atualizar_usuarios()


class TelaLogin(ctk.CTk):
    """Janela de login mostrada antes de abrir o PDV."""

    def __init__(self):
        super().__init__()
        self.usuario = None
        self.title("PDV Próprio — Entrar")
        self.geometry("380x460")
        self.resizable(False, False)
        self.configure(fg_color=P["canvas"])

        card = ctk.CTkFrame(self, fg_color=P["surface"], corner_radius=16, border_width=1, border_color=P["border"])
        card.pack(expand=True, fill="both", padx=24, pady=24)

        ctk.CTkLabel(card, text="PDV", width=56, height=56, corner_radius=15, fg_color=P["accent"], text_color=P["primary_strong"], font=ctk.CTkFont(family=FONTE, size=18, weight="bold")).pack(pady=(30, 10))
        ctk.CTkLabel(card, text="PDV Próprio", text_color=P["text"], font=ctk.CTkFont(family=FONTE, size=18, weight="bold")).pack()
        ctk.CTkLabel(card, text="Entre para continuar", text_color=P["muted"], font=ctk.CTkFont(family=FONTE, size=11)).pack(pady=(2, 20))

        self.login = ctk.CTkEntry(card, placeholder_text="Usuário", width=250, corner_radius=10, fg_color="#ffffff", border_color=P["border"], text_color=P["text"], font=ctk.CTkFont(family=FONTE, size=13))
        self.login.pack(pady=6)
        self.senha = ctk.CTkEntry(card, placeholder_text="Senha", show="•", width=250, corner_radius=10, fg_color="#ffffff", border_color=P["border"], text_color=P["text"], font=ctk.CTkFont(family=FONTE, size=13))
        self.senha.pack(pady=6)

        ctk.CTkButton(card, text="Entrar", width=250, corner_radius=11, fg_color=P["primary"], hover_color=P["primary_strong"], text_color="#ffffff", font=ctk.CTkFont(family=FONTE, size=13, weight="bold"), command=self._entrar).pack(pady=(16, 6))

        self.login.bind("<Return>", lambda e: self.senha.focus())
        self.senha.bind("<Return>", lambda e: self._entrar())
        self.login.focus()

    def _entrar(self):
        usuario = banco.autenticar(self.login.get().strip(), self.senha.get())
        if usuario:
            self.usuario = usuario
            self.destroy()
        else:
            messagebox.showwarning("Acesso negado", "Usuário ou senha incorretos.")
            self.senha.delete(0, tk.END)
            self.senha.focus()


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

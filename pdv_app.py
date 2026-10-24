"""PDV Próprio — aplicativo de desktop.

Janela feita com CustomTkinter, conversando direto com o banco SQLite
pela camada em banco.py. Visual inspirado no design (verde, clean, Manrope):
tela de Venda com catálogo em cartões à esquerda e checkout à direita.

Rodar com:  python3 pdv_app.py
"""

import tkinter as tk
from tkinter import ttk, messagebox

import urllib.error

import customtkinter as ctk

import banco
import sync

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
    def __init__(self):
        super().__init__()
        self.title("PDV Próprio")
        self.geometry("1040x700")
        self.minsize(880, 580)
        self.configure(fg_color=P["canvas"])

        self.carrinho = []
        self.produto_sel_id = None
        self.forma_venda = "Dinheiro"

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

        for texto, comando in [
            ("Venda", self.mostrar_vendas),
            ("Produtos", self.mostrar_produtos),
            ("Caixa", self.mostrar_caixa),
            ("Histórico", self.mostrar_historico),
            ("Relatório", self.mostrar_relatorio),
        ]:
            self._btn(barra, texto, comando, tipo="sidebar", width=168).pack(padx=16, pady=5, fill="x")

        self._btn(barra, "Sincronizar", self.sincronizar_agora, tipo="accent", width=168).pack(
            padx=16, pady=(20, 18), side="bottom", fill="x"
        )

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
        self.label_total.grid(row=2, column=0, columnspan=3, sticky="e", pady=(0, 10))

        self._btn(rodape, "Finalizar venda", self.finalizar_venda, "primario", 200).grid(
            row=3, column=0, columnspan=3, sticky="ew"
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
        self._limpar_area()
        self.produto_sel_id = None
        self.area.grid_columnconfigure(0, weight=1)
        self.area.grid_columnconfigure(1, weight=0)
        self.area.grid_rowconfigure(2, weight=1)

        self._titulo("Produtos").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 14))

        form = self._card(self.area)
        form.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 14))
        form.grid_columnconfigure(0, weight=3)
        form.grid_columnconfigure(1, weight=2)
        form.grid_columnconfigure(2, weight=1)

        self.campo_desc = self._entry(form, "Descrição do produto")
        self.campo_cod = self._entry(form, "Código de barras")
        self.campo_preco = self._entry(form, "Preço (ex: 5,50)")
        self.campo_desc.grid(row=0, column=0, padx=(14, 6), pady=(14, 6), sticky="ew")
        self.campo_cod.grid(row=0, column=1, padx=6, pady=(14, 6), sticky="ew")
        self.campo_preco.grid(row=0, column=2, padx=(6, 14), pady=(14, 6), sticky="ew")

        botoes = ctk.CTkFrame(form, fg_color="transparent")
        botoes.grid(row=1, column=0, columnspan=3, padx=14, pady=(0, 14), sticky="w")
        self._btn(botoes, "Adicionar", self.adicionar_produto, width=110).pack(side="left", padx=(0, 6))
        self._btn(botoes, "Salvar alteração", self.salvar_produto, "secundario", 140).pack(side="left", padx=6)
        self._btn(botoes, "Excluir", self.excluir_produto, "perigo", 90).pack(side="left", padx=6)
        self._btn(botoes, "Limpar", self.limpar_form_produto, "secundario", 90).pack(side="left", padx=6)

        colunas = ("id", "codigo", "descricao", "preco")
        self.tabela_prod = ttk.Treeview(self.area, columns=colunas, show="headings")
        self.tabela_prod.heading("id", text="ID")
        self.tabela_prod.heading("codigo", text="Código")
        self.tabela_prod.heading("descricao", text="Descrição")
        self.tabela_prod.heading("preco", text="Preço (R$)")
        self.tabela_prod.column("id", width=50, anchor="center")
        self.tabela_prod.column("codigo", width=160, anchor="center")
        self.tabela_prod.column("descricao", width=360)
        self.tabela_prod.column("preco", width=110, anchor="e")
        self.tabela_prod.grid(row=2, column=0, sticky="nsew")
        self.tabela_prod.bind("<<TreeviewSelect>>", self._carregar_produto_selecionado)

        rol = ttk.Scrollbar(self.area, orient="vertical", command=self.tabela_prod.yview)
        self.tabela_prod.configure(yscrollcommand=rol.set)
        rol.grid(row=2, column=1, sticky="ns")

        ctk.CTkLabel(
            self.area, text="Clique num produto para editar ou excluir.",
            text_color=P["muted"], font=self._fonte(11),
        ).grid(row=3, column=0, sticky="w", pady=(8, 0))

        self.atualizar_tabela_produtos()
        self.campo_desc.focus()

    def _ler_form_produto(self):
        descricao = self.campo_desc.get().strip()
        codigo = self.campo_cod.get().strip() or None
        texto_preco = self.campo_preco.get().strip()
        if not descricao:
            messagebox.showwarning("Campo obrigatório", "Informe a descrição do produto.")
            self.campo_desc.focus()
            return None
        try:
            preco_centavos = banco.para_centavos(texto_preco) if texto_preco else 0
        except ValueError:
            messagebox.showwarning("Preço inválido", "Use um número, ex: 5,50.")
            self.campo_preco.focus()
            return None
        return descricao, codigo, preco_centavos

    def adicionar_produto(self):
        dados = self._ler_form_produto()
        if dados is None:
            return
        try:
            banco.cadastrar_produto(*dados)
        except banco.CodigoDuplicado:
            messagebox.showwarning("Código repetido", f"Já existe um produto com o código {dados[1]}.")
            self.campo_cod.focus()
            return
        self.limpar_form_produto()
        self.atualizar_tabela_produtos()

    def salvar_produto(self):
        if self.produto_sel_id is None:
            messagebox.showinfo("Selecione um produto", "Clique num produto da lista para editar.")
            return
        dados = self._ler_form_produto()
        if dados is None:
            return
        try:
            banco.atualizar_produto(self.produto_sel_id, *dados)
        except banco.CodigoDuplicado:
            messagebox.showwarning("Código repetido", f"Já existe um produto com o código {dados[1]}.")
            self.campo_cod.focus()
            return
        self.limpar_form_produto()
        self.atualizar_tabela_produtos()

    def excluir_produto(self):
        if self.produto_sel_id is None:
            messagebox.showinfo("Selecione um produto", "Clique num produto da lista para excluir.")
            return
        if not messagebox.askyesno("Excluir produto", "Deseja mesmo excluir este produto?"):
            return
        banco.inativar_produto(self.produto_sel_id)
        self.limpar_form_produto()
        self.atualizar_tabela_produtos()

    def limpar_form_produto(self):
        self.produto_sel_id = None
        self.campo_desc.delete(0, tk.END)
        self.campo_cod.delete(0, tk.END)
        self.campo_preco.delete(0, tk.END)
        if self.tabela_prod.selection():
            self.tabela_prod.selection_remove(self.tabela_prod.selection())
        self.campo_desc.focus()

    def _carregar_produto_selecionado(self, evento=None):
        selecao = self.tabela_prod.selection()
        if not selecao:
            return
        valores = self.tabela_prod.item(selecao[0], "values")
        self.produto_sel_id = int(valores[0])
        self.campo_desc.delete(0, tk.END)
        self.campo_desc.insert(0, valores[2])
        self.campo_cod.delete(0, tk.END)
        self.campo_cod.insert(0, valores[1])
        self.campo_preco.delete(0, tk.END)
        self.campo_preco.insert(0, valores[3])

    def atualizar_tabela_produtos(self):
        for linha in self.tabela_prod.get_children():
            self.tabela_prod.delete(linha)
        for produto in banco.listar_produtos():
            self.tabela_prod.insert(
                "",
                tk.END,
                values=(
                    produto["id"],
                    produto["codigo"] or "",
                    produto["descricao"],
                    banco.formatar_reais(produto["preco_centavos"]),
                ),
            )

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


if __name__ == "__main__":
    banco.inicializar()
    AppPDV().mainloop()

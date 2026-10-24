"""PDV Próprio — aplicativo de desktop.

Janela feita com CustomTkinter (visual moderno e leve), conversando
direto com o banco SQLite pela camada em banco.py.

Rodar com:  python3 pdv_app.py
"""

import tkinter as tk
from tkinter import ttk, messagebox

import customtkinter as ctk

import banco

ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")

FORMAS_PAGAMENTO = ["Dinheiro", "Cartão", "Pix"]


class AppPDV(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("PDV Próprio")
        self.geometry("980x660")
        self.minsize(820, 540)

        self.carrinho = []

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._montar_barra_lateral()

        self.area = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self.area.grid(row=0, column=1, sticky="nsew", padx=20, pady=20)

        self.mostrar_vendas()

    # ---------- Barra lateral ----------
    def _montar_barra_lateral(self):
        barra = ctk.CTkFrame(self, width=190, corner_radius=0)
        barra.grid(row=0, column=0, sticky="nsew")
        barra.grid_propagate(False)

        ctk.CTkLabel(
            barra, text="PDV Próprio", font=ctk.CTkFont(size=20, weight="bold")
        ).pack(padx=20, pady=(26, 20))

        ctk.CTkButton(barra, text="Venda", command=self.mostrar_vendas).pack(
            padx=16, pady=6, fill="x"
        )
        ctk.CTkButton(barra, text="Produtos", command=self.mostrar_produtos).pack(
            padx=16, pady=6, fill="x"
        )
        ctk.CTkButton(barra, text="Caixa", command=self.mostrar_caixa).pack(
            padx=16, pady=6, fill="x"
        )
        ctk.CTkButton(barra, text="Relatório", command=self.mostrar_relatorio).pack(
            padx=16, pady=6, fill="x"
        )

    def _limpar_area(self):
        for widget in self.area.winfo_children():
            widget.destroy()

    def _pedir_valor(self, titulo, texto):
        """Abre um diálogo pedindo um valor em reais; devolve centavos ou None."""
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
    # Tela de Produtos
    # ==================================================================
    def mostrar_produtos(self):
        self._limpar_area()
        self.area.grid_columnconfigure(0, weight=1)
        self.area.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(
            self.area, text="Produtos", font=ctk.CTkFont(size=26, weight="bold")
        ).grid(row=0, column=0, sticky="w", pady=(0, 14))

        form = ctk.CTkFrame(self.area)
        form.grid(row=1, column=0, sticky="ew", pady=(0, 14))
        form.grid_columnconfigure(0, weight=3)
        form.grid_columnconfigure(1, weight=2)
        form.grid_columnconfigure(2, weight=1)

        self.campo_desc = ctk.CTkEntry(form, placeholder_text="Descrição do produto")
        self.campo_cod = ctk.CTkEntry(form, placeholder_text="Código de barras")
        self.campo_preco = ctk.CTkEntry(form, placeholder_text="Preço (ex: 5,50)")
        self.campo_desc.grid(row=0, column=0, padx=(12, 6), pady=12, sticky="ew")
        self.campo_cod.grid(row=0, column=1, padx=6, pady=12, sticky="ew")
        self.campo_preco.grid(row=0, column=2, padx=6, pady=12, sticky="ew")

        ctk.CTkButton(form, text="Adicionar", width=120, command=self.adicionar_produto).grid(
            row=0, column=3, padx=(6, 12), pady=12
        )
        for campo in (self.campo_desc, self.campo_cod, self.campo_preco):
            campo.bind("<Return>", lambda evento: self.adicionar_produto())
        self.campo_desc.focus()

        colunas = ("id", "codigo", "descricao", "preco")
        self.tabela_prod = ttk.Treeview(self.area, columns=colunas, show="headings")
        self.tabela_prod.heading("id", text="ID")
        self.tabela_prod.heading("codigo", text="Código")
        self.tabela_prod.heading("descricao", text="Descrição")
        self.tabela_prod.heading("preco", text="Preço (R$)")
        self.tabela_prod.column("id", width=50, anchor="center")
        self.tabela_prod.column("codigo", width=160, anchor="center")
        self.tabela_prod.column("descricao", width=380)
        self.tabela_prod.column("preco", width=110, anchor="e")
        self.tabela_prod.grid(row=2, column=0, sticky="nsew")
        rol = ttk.Scrollbar(self.area, orient="vertical", command=self.tabela_prod.yview)
        self.tabela_prod.configure(yscrollcommand=rol.set)
        rol.grid(row=2, column=1, sticky="ns")

        self.atualizar_tabela_produtos()

    def adicionar_produto(self):
        descricao = self.campo_desc.get().strip()
        codigo = self.campo_cod.get().strip() or None
        texto_preco = self.campo_preco.get().strip()

        if not descricao:
            messagebox.showwarning("Campo obrigatório", "Informe a descrição do produto.")
            self.campo_desc.focus()
            return
        try:
            preco_centavos = banco.para_centavos(texto_preco) if texto_preco else 0
        except ValueError:
            messagebox.showwarning("Preço inválido", "Use um número, ex: 5,50.")
            self.campo_preco.focus()
            return
        try:
            banco.cadastrar_produto(descricao, codigo, preco_centavos)
        except banco.CodigoDuplicado:
            messagebox.showwarning(
                "Código repetido", f"Já existe um produto com o código {codigo}."
            )
            self.campo_cod.focus()
            return

        self.campo_desc.delete(0, tk.END)
        self.campo_cod.delete(0, tk.END)
        self.campo_preco.delete(0, tk.END)
        self.campo_desc.focus()
        self.atualizar_tabela_produtos()

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
    # Tela de Venda
    # ==================================================================
    def mostrar_vendas(self):
        self._limpar_area()
        self.carrinho = []
        self.area.grid_columnconfigure(0, weight=1)
        self.area.grid_rowconfigure(2, weight=1)

        cabecalho = "Venda"
        sessao = banco.sessao_aberta()
        if sessao is None:
            cabecalho = "Venda  (caixa fechado)"
        ctk.CTkLabel(
            self.area, text=cabecalho, font=ctk.CTkFont(size=26, weight="bold")
        ).grid(row=0, column=0, sticky="w", pady=(0, 14))

        controles = ctk.CTkFrame(self.area)
        controles.grid(row=1, column=0, sticky="ew", pady=(0, 14))
        controles.grid_columnconfigure(1, weight=2)
        controles.grid_columnconfigure(3, weight=2)

        ctk.CTkLabel(controles, text="Código:").grid(row=0, column=0, padx=(12, 4), pady=12)
        self.campo_venda_cod = ctk.CTkEntry(controles, placeholder_text="Leia ou digite o código")
        self.campo_venda_cod.grid(row=0, column=1, padx=4, pady=12, sticky="ew")
        self.campo_venda_cod.bind("<Return>", lambda e: self.adicionar_por_codigo())

        self.produtos_venda = banco.listar_produtos()
        nomes = [p["descricao"] for p in self.produtos_venda] or ["(sem produtos)"]
        ctk.CTkLabel(controles, text="ou:").grid(row=0, column=2, padx=(16, 4), pady=12)
        self.sel_produto = ctk.CTkOptionMenu(controles, values=nomes)
        self.sel_produto.grid(row=0, column=3, padx=4, pady=12, sticky="ew")
        ctk.CTkButton(controles, text="Adicionar", width=110, command=self.adicionar_por_nome).grid(
            row=0, column=4, padx=(4, 12), pady=12
        )

        colunas = ("descricao", "qtd", "unit", "subtotal")
        self.tabela_venda = ttk.Treeview(self.area, columns=colunas, show="headings")
        self.tabela_venda.heading("descricao", text="Produto")
        self.tabela_venda.heading("qtd", text="Qtd")
        self.tabela_venda.heading("unit", text="Unitário (R$)")
        self.tabela_venda.heading("subtotal", text="Subtotal (R$)")
        self.tabela_venda.column("descricao", width=380)
        self.tabela_venda.column("qtd", width=70, anchor="center")
        self.tabela_venda.column("unit", width=120, anchor="e")
        self.tabela_venda.column("subtotal", width=130, anchor="e")
        self.tabela_venda.grid(row=2, column=0, sticky="nsew")
        rol = ttk.Scrollbar(self.area, orient="vertical", command=self.tabela_venda.yview)
        self.tabela_venda.configure(yscrollcommand=rol.set)
        rol.grid(row=2, column=1, sticky="ns")

        rodape = ctk.CTkFrame(self.area)
        rodape.grid(row=3, column=0, sticky="ew", pady=(14, 0))
        rodape.grid_columnconfigure(1, weight=1)

        ctk.CTkButton(
            rodape, text="Remover item", width=120, fg_color="gray40",
            command=self.remover_item,
        ).grid(row=0, column=0, padx=12, pady=12)

        self.label_total = ctk.CTkLabel(
            rodape, text="Total: R$ 0,00", font=ctk.CTkFont(size=22, weight="bold")
        )
        self.label_total.grid(row=0, column=1, padx=12, pady=12, sticky="e")

        self.sel_forma = ctk.CTkOptionMenu(rodape, values=FORMAS_PAGAMENTO, width=130)
        self.sel_forma.grid(row=0, column=2, padx=6, pady=12)

        ctk.CTkButton(
            rodape, text="Finalizar venda", width=150,
            fg_color="#1f8f4e", hover_color="#176b3a",
            command=self.finalizar_venda,
        ).grid(row=0, column=3, padx=(6, 12), pady=12)

        self.campo_venda_cod.focus()
        self.atualizar_carrinho()

    def _adicionar_ao_carrinho(self, produto):
        for item in self.carrinho:
            if item["produto_id"] == produto["id"]:
                item["quantidade"] += 1
                self.atualizar_carrinho()
                return
        self.carrinho.append(
            {
                "produto_id": produto["id"],
                "descricao": produto["descricao"],
                "quantidade": 1,
                "preco_unit_centavos": produto["preco_centavos"],
            }
        )
        self.atualizar_carrinho()

    def adicionar_por_codigo(self):
        codigo = self.campo_venda_cod.get().strip()
        if not codigo:
            return
        produto = banco.buscar_produto_por_codigo(codigo)
        if not produto:
            messagebox.showwarning("Não encontrado", f"Nenhum produto com o código {codigo}.")
        else:
            self._adicionar_ao_carrinho(produto)
        self.campo_venda_cod.delete(0, tk.END)
        self.campo_venda_cod.focus()

    def adicionar_por_nome(self):
        if not self.produtos_venda:
            return
        nome = self.sel_produto.get()
        produto = next((p for p in self.produtos_venda if p["descricao"] == nome), None)
        if produto:
            self._adicionar_ao_carrinho(produto)

    def remover_item(self):
        selecao = self.tabela_venda.selection()
        if not selecao:
            return
        indice = self.tabela_venda.index(selecao[0])
        del self.carrinho[indice]
        self.atualizar_carrinho()

    def _total_centavos(self):
        return sum(round(i["quantidade"] * i["preco_unit_centavos"]) for i in self.carrinho)

    def atualizar_carrinho(self):
        for linha in self.tabela_venda.get_children():
            self.tabela_venda.delete(linha)
        for item in self.carrinho:
            subtotal = round(item["quantidade"] * item["preco_unit_centavos"])
            self.tabela_venda.insert(
                "",
                tk.END,
                values=(
                    item["descricao"],
                    f"{item['quantidade']:g}",
                    banco.formatar_reais(item["preco_unit_centavos"]),
                    banco.formatar_reais(subtotal),
                ),
            )
        self.label_total.configure(
            text=f"Total: R$ {banco.formatar_reais(self._total_centavos())}"
        )

    def finalizar_venda(self):
        if not self.carrinho:
            messagebox.showwarning("Carrinho vazio", "Adicione pelo menos um produto.")
            return

        total = self._total_centavos()
        sessao = banco.sessao_aberta()
        sessao_id = sessao["id"] if sessao else None
        pagamentos = [{"forma": self.sel_forma.get(), "valor_centavos": total}]

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
        self.atualizar_carrinho()
        self.campo_venda_cod.focus()

    # ==================================================================
    # Tela de Caixa
    # ==================================================================
    def mostrar_caixa(self):
        self._limpar_area()
        self.area.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self.area, text="Caixa", font=ctk.CTkFont(size=26, weight="bold")
        ).grid(row=0, column=0, sticky="w", pady=(0, 14))

        sessao = banco.sessao_aberta()
        if sessao is None:
            self._tela_abrir_caixa()
        else:
            self._tela_caixa_aberto(sessao)

    def _tela_abrir_caixa(self):
        caixa = ctk.CTkFrame(self.area)
        caixa.grid(row=1, column=0, sticky="ew")
        caixa.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(caixa, text="Caixa fechado. Abra para começar a operar.").grid(
            row=0, column=0, columnspan=2, padx=12, pady=(14, 8), sticky="w"
        )
        ctk.CTkLabel(caixa, text="Operador:").grid(row=1, column=0, padx=12, pady=8, sticky="e")
        self.campo_operador = ctk.CTkEntry(caixa, placeholder_text="Nome do operador")
        self.campo_operador.grid(row=1, column=1, padx=12, pady=8, sticky="ew")

        ctk.CTkLabel(caixa, text="Fundo de troco (R$):").grid(row=2, column=0, padx=12, pady=8, sticky="e")
        self.campo_abertura = ctk.CTkEntry(caixa, placeholder_text="ex: 100,00")
        self.campo_abertura.grid(row=2, column=1, padx=12, pady=8, sticky="ew")

        ctk.CTkButton(caixa, text="Abrir caixa", command=self.abrir_caixa).grid(
            row=3, column=1, padx=12, pady=(8, 14), sticky="e"
        )
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
        info = ctk.CTkFrame(self.area)
        info.grid(row=1, column=0, sticky="ew", pady=(0, 14))
        operador = sessao["operador"] or "—"
        ctk.CTkLabel(
            info,
            text=f"Caixa aberto por {operador}  ·  desde {sessao['aberto_em']}",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(padx=12, pady=12, anchor="w")

        resumo = banco.resumo_caixa(sessao["id"])
        painel = ctk.CTkFrame(self.area)
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
            fonte = ctk.CTkFont(size=14, weight="bold" if negrito else "normal")
            ctk.CTkLabel(painel, text=rotulo, font=fonte).grid(
                row=i, column=0, padx=12, pady=6, sticky="w"
            )
            ctk.CTkLabel(painel, text=f"R$ {banco.formatar_reais(centavos)}", font=fonte).grid(
                row=i, column=1, padx=12, pady=6, sticky="e"
            )

        botoes = ctk.CTkFrame(self.area)
        botoes.grid(row=3, column=0, sticky="ew")
        ctk.CTkButton(botoes, text="Suprimento", command=lambda: self._movimento(sessao, "suprimento")).pack(
            side="left", padx=12, pady=12
        )
        ctk.CTkButton(botoes, text="Sangria", command=lambda: self._movimento(sessao, "sangria")).pack(
            side="left", padx=4, pady=12
        )
        ctk.CTkButton(
            botoes, text="Fechar caixa", fg_color="#b03a2e", hover_color="#8c2d24",
            command=lambda: self.fechar_caixa(sessao),
        ).pack(side="right", padx=12, pady=12)

    def _movimento(self, sessao, tipo):
        valor = self._pedir_valor(
            tipo.capitalize(), f"Valor do {tipo} (R$):"
        )
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
    # Tela de Relatório
    # ==================================================================
    def mostrar_relatorio(self):
        self._limpar_area()
        self.area.grid_columnconfigure(0, weight=1)

        rel = banco.relatorio_dia()
        ctk.CTkLabel(
            self.area, text=f"Relatório do dia  ·  {rel['data']}",
            font=ctk.CTkFont(size=26, weight="bold"),
        ).grid(row=0, column=0, sticky="w", pady=(0, 14))

        topo = ctk.CTkFrame(self.area)
        topo.grid(row=1, column=0, sticky="ew", pady=(0, 14))
        topo.grid_columnconfigure((0, 1), weight=1)
        ctk.CTkLabel(topo, text="Vendas concluídas", font=ctk.CTkFont(size=14)).grid(
            row=0, column=0, padx=12, pady=(12, 2), sticky="w"
        )
        ctk.CTkLabel(topo, text=str(rel["qtd"]), font=ctk.CTkFont(size=22, weight="bold")).grid(
            row=1, column=0, padx=12, pady=(0, 12), sticky="w"
        )
        ctk.CTkLabel(topo, text="Total vendido", font=ctk.CTkFont(size=14)).grid(
            row=0, column=1, padx=12, pady=(12, 2), sticky="e"
        )
        ctk.CTkLabel(
            topo, text=f"R$ {banco.formatar_reais(rel['total'])}",
            font=ctk.CTkFont(size=22, weight="bold"),
        ).grid(row=1, column=1, padx=12, pady=(0, 12), sticky="e")

        ctk.CTkLabel(
            self.area, text="Por forma de pagamento", font=ctk.CTkFont(size=16, weight="bold")
        ).grid(row=2, column=0, sticky="w", pady=(0, 6))

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
    banco.inicializar()  # cria o banco na primeira execução, se preciso
    AppPDV().mainloop()

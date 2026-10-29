"""Emissão de NFC-e (Fase 4).

Passo 1 (implementado): validação de pré-emissão — diz o que falta para emitir.
Passo 2 (com certificado, na máquina do usuário): montar o XML, assinar e
transmitir à SEFAZ em homologação via PyNFe, gravar chave/protocolo e imprimir
o DANFE. O meu ambiente não alcança a SEFAZ, então o passo 2 valida aí.
"""

CONFIG_OBRIGATORIA = {
    "razao_social": "Razão social", "cnpj": "CNPJ", "ie": "Inscrição Estadual",
    "uf": "UF", "cod_municipio": "Código IBGE do município",
    "csc": "CSC", "csc_id": "ID do CSC",
    "certificado_caminho": "Certificado (.pfx)", "certificado_senha": "Senha do certificado",
}

PRODUTO_OBRIGATORIO = {
    "descricao": "Descrição", "ncm": "NCM", "cfop": "CFOP",
    "origem": "Origem", "cst": "CST/CSOSN", "unidade": "Unidade",
}


def _vazio(valor):
    return not str(valor if valor is not None else "").strip()


def validar_config(config):
    """Campos da empresa que faltam para emitir."""
    return [nome for campo, nome in CONFIG_OBRIGATORIA.items() if _vazio(config.get(campo))]


def validar_produto(produto):
    """Campos fiscais que faltam no produto."""
    return [nome for campo, nome in PRODUTO_OBRIGATORIO.items() if _vazio(produto.get(campo))]


def pendencias_emissao(config, produtos):
    """Lista de pendências (texto) que impedem emitir a NFC-e. Vazia = pronto."""
    pendencias = [f"Empresa: {nome}" for nome in validar_config(config)]
    for produto in produtos:
        rotulo = produto.get("descricao") or f"id {produto.get('id')}"
        for nome in validar_produto(produto):
            pendencias.append(f"Produto '{rotulo}': {nome}")
    return pendencias

"""Exportação do cadastro de produtos.

O cabeçalho segue o Registro 0200 do SPED Fiscal (EFD-ICMS/IPI), que é o
padrão oficial de identificação do item/produto, acrescido de colunas
detalhadas (preço, custo, estoque, categoria, tributos).

Arquivo: CSV com separador ';' e BOM (utf-8-sig), abre direto no Excel/BR.
"""

import csv

from . import banco

# Colunas 0200 do SPED (COD_ITEM, DESCR_ITEM, COD_BARRA, UNID_INV, TIPO_ITEM,
# COD_NCM, EX_IPI, CEST, ALIQ_ICMS) + dados complementares.
CABECALHO = [
    "COD_ITEM", "DESCR_ITEM", "COD_BARRA", "UNID_INV", "TIPO_ITEM",
    "COD_NCM", "EX_IPI", "CEST", "ALIQ_ICMS",
    "CFOP", "CST_CSOSN", "ORIGEM", "CATEGORIA",
    "PRECO_VENDA", "CUSTO", "ESTOQUE", "CONTROLA_ESTOQUE",
    "TRIBUTOS_APROX_PCT", "ATIVO", "UUID", "CRIADO_EM", "ATUALIZADO_EM",
]


def _linha(p):
    return [
        p.get("codigo_interno") or p.get("id"),      # COD_ITEM (código próprio)
        p.get("descricao") or "",                     # DESCR_ITEM
        p.get("codigo") or "",                        # COD_BARRA (GTIN/EAN)
        p.get("unidade") or "",                       # UNID_INV
        p.get("tipo_item") or "00",                   # TIPO_ITEM
        p.get("ncm") or "",                           # COD_NCM
        "",                                            # EX_IPI (não controlado)
        p.get("cest") or "",                          # CEST
        p.get("aliquota_icms") or 0,                  # ALIQ_ICMS
        p.get("cfop") or "",
        p.get("cst") or "",
        p.get("origem") or "",
        p.get("categoria") or "",
        banco.formatar_reais(p.get("preco_centavos") or 0),
        banco.formatar_reais(p.get("custo_centavos") or 0),
        p.get("estoque") or 0,
        "Sim" if p.get("controla_estoque") else "Não",
        p.get("aliquota_aprox") or 0,
        "Sim" if p.get("ativo") else "Não",
        p.get("uuid") or "",
        p.get("criado_em") or "",
        p.get("atualizado_em") or "",
    ]


def _seguro(valor):
    """Evita injeção de fórmula no Excel: texto iniciado por = + - @ vira literal."""
    if isinstance(valor, str) and valor[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + valor
    return valor


def exportar_produtos_csv(caminho, produtos):
    """Grava os produtos num CSV. Devolve a quantidade exportada."""
    with open(caminho, "w", newline="", encoding="utf-8-sig") as arquivo:
        escritor = csv.writer(arquivo, delimiter=";")
        escritor.writerow(CABECALHO)
        escritor.writerows([_seguro(v) for v in _linha(p)] for p in produtos)
    return len(produtos)


CABECALHO_VENDAS = ["VENDA", "DATA_HORA", "ITENS", "PAGAMENTO", "DESCONTO", "TOTAL"]


def exportar_vendas_csv(caminho, vendas):
    """Grava o histórico de vendas (o filtro atual da tela) num CSV. Devolve a quantidade."""
    with open(caminho, "w", newline="", encoding="utf-8-sig") as arquivo:
        escritor = csv.writer(arquivo, delimiter=";")
        escritor.writerow(CABECALHO_VENDAS)
        escritor.writerows(
            [_seguro(v) for v in (
                venda["id"], venda["criado_em"].replace("T", " "), venda["qtd_itens"],
                venda.get("formas") or "", banco.formatar_reais(venda.get("desconto_centavos") or 0),
                banco.formatar_reais(venda["total_centavos"]),
            )]
            for venda in vendas
        )
    return len(vendas)

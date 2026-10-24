"""Sincronizador do PDV (Fase 2).

Envia os registros pendentes (sincronizado = 0) ao servidor central e,
quando o envio é confirmado, marca cada registro como sincronizado.

Usa apenas a biblioteca padrão (urllib), sem dependências novas.

Uso:
    import sync
    resultado = sync.sincronizar()           # servidor padrão (localhost:5001)
    resultado = sync.sincronizar("http://192.168.0.50:5001")
"""

import json
import urllib.error
import urllib.request

import banco

SERVIDOR_PADRAO = "http://127.0.0.1:5001"


def _postar(url, dados):
    corpo = json.dumps(dados).encode("utf-8")
    req = urllib.request.Request(
        url, data=corpo, headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=10) as resposta:
        return json.loads(resposta.read().decode("utf-8"))


def sincronizar(servidor=SERVIDOR_PADRAO):
    """Envia produtos e vendas pendentes. Devolve um resumo do que foi enviado.

    Em caso de falha de rede, os registros continuam pendentes (nada se perde).
    """
    enviados_produtos = 0
    enviados_vendas = 0

    # Produtos
    produtos = banco.produtos_pendentes()
    if produtos:
        _postar(f"{servidor}/sync/produtos", produtos)
        for p in produtos:
            banco.marcar_produto_sincronizado(p["uuid"])
            enviados_produtos += 1

    # Vendas (cada uma com seus itens e pagamentos)
    vendas = banco.vendas_pendentes()
    if vendas:
        _postar(f"{servidor}/sync/vendas", vendas)
        for v in vendas:
            banco.marcar_venda_sincronizada(v["uuid"])
            enviados_vendas += 1

    return {"produtos": enviados_produtos, "vendas": enviados_vendas}


if __name__ == "__main__":
    banco.inicializar()
    try:
        resultado = sincronizar()
        print(
            f"Sincronizado: {resultado['produtos']} produto(s), "
            f"{resultado['vendas']} venda(s)."
        )
    except urllib.error.URLError as erro:
        print(f"Não foi possível conectar ao servidor central: {erro}")
        print("Os registros continuam pendentes e serão enviados na próxima vez.")

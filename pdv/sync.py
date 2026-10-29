"""Sincronizador do PDV (Fase 2).

Envia os registros pendentes (sincronizado = 0) ao servidor central e,
quando o envio é confirmado, marca cada registro como sincronizado.

Usa apenas a biblioteca padrão (urllib), sem dependências novas.

Configuração por variável de ambiente (nada de chave escrita no código):
    PDV_SERVIDOR     endereço do central (padrão http://127.0.0.1:5001)
    PDV_SYNC_TOKEN   token compartilhado com o central (opcional)

Uso:
    from pdv import sync
    resultado = sync.sincronizar()
    resultado = sync.sincronizar("http://192.168.0.50:5001")
"""

import json
import os
import urllib.error
import urllib.request

from . import banco

SERVIDOR_PADRAO = os.environ.get("PDV_SERVIDOR", "http://127.0.0.1:5001")


def _postar(url, dados):
    cabecalhos = {"Content-Type": "application/json"}
    token = os.environ.get("PDV_SYNC_TOKEN")
    if token:
        cabecalhos["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=json.dumps(dados).encode("utf-8"), headers=cabecalhos, method="POST")
    with urllib.request.urlopen(req, timeout=5) as resposta:
        return json.loads(resposta.read().decode("utf-8"))


def sincronizar(servidor=SERVIDOR_PADRAO):
    """Envia produtos e vendas pendentes. Devolve um resumo do que foi enviado.

    Em caso de falha de rede, os registros continuam pendentes (nada se perde).
    """
    produtos = banco.produtos_pendentes()
    if produtos:
        _postar(f"{servidor}/sync/produtos", produtos)
        banco.marcar_produtos_sincronizados(produtos)

    # Vendas (cada uma com seus itens e pagamentos)
    vendas = banco.vendas_pendentes()
    if vendas:
        _postar(f"{servidor}/sync/vendas", vendas)
        banco.marcar_vendas_sincronizadas(vendas)

    return {"produtos": len(produtos), "vendas": len(vendas)}


if __name__ == "__main__":
    banco.inicializar()
    try:
        resultado = sincronizar()
        print(f"Sincronizado: {resultado['produtos']} produto(s), {resultado['vendas']} venda(s).")
    except urllib.error.URLError as erro:
        print(f"Não foi possível conectar ao servidor central: {erro}")
        print("Os registros continuam pendentes e serão enviados na próxima vez.")

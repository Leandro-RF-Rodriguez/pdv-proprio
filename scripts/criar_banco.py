"""Cria/migra o banco local manualmente (opcional; o app já faz isso sozinho).

Rodar com:  python3 -m scripts.criar_banco   (a partir da raiz do projeto)
"""

from pdv import banco


def criar_banco():
    banco.inicializar()
    print(f"Banco pronto em {banco.CAMINHO_BANCO}")


if __name__ == "__main__":
    criar_banco()

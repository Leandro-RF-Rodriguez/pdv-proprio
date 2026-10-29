"""Ponto de entrada do PDV Próprio (também usado pelo PyInstaller).

Rodar com:  python3 pdv_app.py   (equivale a python3 -m pdv)
"""

from pdv.interface import iniciar

if __name__ == "__main__":
    iniciar()

"""Ícones de traço (estilo do protótipo do Figma) desenhados com Pillow.

Cada ícone é descrito como no SVG original (viewBox 24×24, traço 1,8, pontas
redondas). Um mini-rasterizador converte os caminhos em linhas e desenha com
supersampling para ficar suave em qualquer tamanho e cor — sem arquivos de
imagem nem dependências além do Pillow.

Uso:  icone("cart", 18, "#ffffff")  ->  CTkImage pronto para botão/rótulo
"""

import math
import re
from functools import lru_cache

import customtkinter as ctk
from PIL import Image, ImageDraw

# Primitivas: ("p", caminho SVG) | ("c", cx, cy, r) | ("r", x, y, w, h, rx)
ICONES = {
    "cart": [("c", 9, 20, 1), ("c", 19, 20, 1), ("p", "M3 4h2l2.4 10.4a2 2 0 0 0 2 1.6h7.7a2 2 0 0 0 1.9-1.4L21 8H7")],
    "package": [
        ("p", "m16.5 9.4-9-5.2"),
        ("p", "M21 16V8a2 2 0 0 0-1-1.7l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.7l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z"),
        ("p", "M3.3 7 12 12l8.7-5"), ("p", "M12 22V12"),
    ],
    "wallet": [("p", "M20 7V5a2 2 0 0 0-2-2H5a3 3 0 0 0 0 6h15v10a2 2 0 0 1-2 2H5a3 3 0 0 1-3-3V6"), ("p", "M16 13h2")],
    "history": [("p", "M3 12a9 9 0 1 0 3-6.7L3 8"), ("p", "M3 3v5h5"), ("p", "M12 7v5l3 2")],
    "chart": [("p", "M3 3v18h18"), ("p", "m7 16 4-5 4 3 5-7")],
    "settings": [
        ("c", 12, 12, 3),
        ("p", "M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1-2.8 2.8-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.6v.2h-4V21"
              "a1.7 1.7 0 0 0-1-1.6 1.7 1.7 0 0 0-1.9.3l-.1.1L4.2 17l.1-.1a1.7 1.7 0 0 0 .3-1.9A1.7 1.7 0 0 0 3 14"
              "H2.8v-4H3a1.7 1.7 0 0 0 1.6-1 1.7 1.7 0 0 0-.3-1.9L4.2 7 7 4.2l.1.1a1.7 1.7 0 0 0 1.9.3A1.7 1.7 0 0 0 10 3"
              "V2.8h4V3a1.7 1.7 0 0 0 1 1.6 1.7 1.7 0 0 0 1.9-.3l.1-.1L19.8 7l-.1.1a1.7 1.7 0 0 0-.3 1.9 1.7 1.7 0 0 0 1.6 1"
              "h.2v4H21a1.7 1.7 0 0 0-1.6 1Z"),
    ],
    "users": [
        ("p", "M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"), ("c", 9, 7, 4),
        ("p", "M22 21v-2a4 4 0 0 0-3-3.9"), ("p", "M16 3.1a4 4 0 0 1 0 7.8"),
    ],
    "sync": [
        ("p", "M20 2v5h-5"), ("p", "M19.1 9A8 8 0 0 0 5.3 5.3L4 7"),
        ("p", "M4 22v-5h5"), ("p", "M4.9 15A8 8 0 0 0 18.7 18.7L20 17"),
    ],
    "logout": [("p", "M10 17l5-5-5-5"), ("p", "M15 12H3"), ("p", "M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4")],
    "search": [("c", 11, 11, 7), ("p", "m20 20-4-4")],
    "scan": [
        ("p", "M3 7V5a2 2 0 0 1 2-2h2"), ("p", "M17 3h2a2 2 0 0 1 2 2v2"),
        ("p", "M21 17v2a2 2 0 0 1-2 2h-2"), ("p", "M7 21H5a2 2 0 0 1-2-2v-2"),
        ("p", "M7 8v8M10 8v8M14 8v8M17 8v8"),
    ],
    "plus": [("p", "M12 5v14M5 12h14")],
    "minus": [("p", "M5 12h14")],
    "trash": [("p", "M3 6h18M8 6V4h8v2M19 6l-1 15H6L5 6M10 11v5M14 11v5")],
    "cash": [("r", 2, 6, 20, 12, 2), ("c", 12, 12, 2.5), ("p", "M6 9h.01M18 15h.01")],
    "card": [("r", 2, 5, 20, 14, 2), ("p", "M2 10h20")],
    "pix": [
        ("p", "m12 3 3.5 3.5a2.1 2.1 0 0 0 3 0L20 8l-3.5 3.5a2.1 2.1 0 0 1-3 0L10 8 6.5 11.5a2.1 2.1 0 0 1-3 0L2 10"),
        ("p", "m12 21-3.5-3.5a2.1 2.1 0 0 0-3 0L4 16l3.5-3.5a2.1 2.1 0 0 1 3 0L14 16l3.5-3.5a2.1 2.1 0 0 1 3 0L22 14"),
    ],
    "chevron": [("p", "m9 18 6-6-6-6")],
    "check": [("p", "m5 12 4 4L19 6")],
    "lock": [("r", 4, 11, 16, 10, 2), ("p", "M8 11V7a4 4 0 0 1 8 0v4")],
    "user": [("c", 12, 8, 4), ("p", "M5 21a7 7 0 0 1 14 0")],
    "receipt": [("p", "M5 3h14v18l-3-2-2 2-2-2-2 2-2-2-3 2Z"), ("p", "M9 8h6M9 12h6")],
}

_TOKEN = re.compile(r"[A-Za-z]|-?(?:\d+\.?\d*|\.\d+)")
_PASSOS_CURVA = 14


def _arco(x1, y1, rx, ry, phi, grande, horario, x2, y2):
    """Pontos de um arco SVG (conversão de extremos para centro, SVG 1.1 F.6.5)."""
    if rx == 0 or ry == 0 or (x1, y1) == (x2, y2):
        return [(x2, y2)]
    phi = math.radians(phi)
    cos, sin = math.cos(phi), math.sin(phi)
    dx, dy = (x1 - x2) / 2, (y1 - y2) / 2
    x1p, y1p = cos * dx + sin * dy, -sin * dx + cos * dy
    rx, ry = abs(rx), abs(ry)
    escala = (x1p ** 2) / rx ** 2 + (y1p ** 2) / ry ** 2
    if escala > 1:
        rx, ry = rx * math.sqrt(escala), ry * math.sqrt(escala)
    num = rx ** 2 * ry ** 2 - rx ** 2 * y1p ** 2 - ry ** 2 * x1p ** 2
    den = rx ** 2 * y1p ** 2 + ry ** 2 * x1p ** 2
    coef = math.sqrt(max(0, num / den)) * (-1 if grande == horario else 1)
    cxp, cyp = coef * rx * y1p / ry, -coef * ry * x1p / rx
    cx = cos * cxp - sin * cyp + (x1 + x2) / 2
    cy = sin * cxp + cos * cyp + (y1 + y2) / 2

    def angulo(ux, uy, vx, vy):
        a = math.atan2(ux * vy - uy * vx, ux * vx + uy * vy)
        return a

    t1 = angulo(1, 0, (x1p - cxp) / rx, (y1p - cyp) / ry)
    dt = angulo((x1p - cxp) / rx, (y1p - cyp) / ry, (-x1p - cxp) / rx, (-y1p - cyp) / ry)
    if not horario and dt > 0:
        dt -= 2 * math.pi
    elif horario and dt < 0:
        dt += 2 * math.pi
    passos = max(4, int(abs(dt) / (math.pi / 16)))
    pontos = []
    for i in range(1, passos + 1):
        t = t1 + dt * i / passos
        x, y = rx * math.cos(t), ry * math.sin(t)
        pontos.append((cos * x - sin * y + cx, sin * x + cos * y + cy))
    return pontos


def _caminho(d):
    """Converte um caminho SVG (M L H V C A Z, absolutos e relativos) em polilinhas."""
    tokens = _TOKEN.findall(d)
    linhas, atual = [], []
    x = y = inicio_x = inicio_y = 0.0
    cmd, i = None, 0

    def numeros(n):
        nonlocal i
        valores = [float(t) for t in tokens[i:i + n]]
        i += n
        return valores

    while i < len(tokens):
        if tokens[i].isalpha():
            cmd = tokens[i]
            i += 1
        rel = cmd.islower()
        c = cmd.upper()
        if c == "M":
            nx, ny = numeros(2)
            x, y = (x + nx, y + ny) if rel else (nx, ny)
            if len(atual) > 1:
                linhas.append(atual)
            atual = [(x, y)]
            inicio_x, inicio_y = x, y
            cmd = "l" if rel else "L"  # pares seguintes são linhas
        elif c == "L":
            nx, ny = numeros(2)
            x, y = (x + nx, y + ny) if rel else (nx, ny)
            atual.append((x, y))
        elif c == "H":
            (nx,) = numeros(1)
            x = x + nx if rel else nx
            atual.append((x, y))
        elif c == "V":
            (ny,) = numeros(1)
            y = y + ny if rel else ny
            atual.append((x, y))
        elif c == "C":
            v = numeros(6)
            if rel:
                v = [v[k] + (x if k % 2 == 0 else y) for k in range(6)]
            for passo in range(1, _PASSOS_CURVA + 1):
                t = passo / _PASSOS_CURVA
                a, b, cc, dd = (1 - t) ** 3, 3 * (1 - t) ** 2 * t, 3 * (1 - t) * t ** 2, t ** 3
                atual.append((a * x + b * v[0] + cc * v[2] + dd * v[4], a * y + b * v[1] + cc * v[3] + dd * v[5]))
            x, y = v[4], v[5]
        elif c == "A":
            rx, ry, phi, grande, horario, nx, ny = numeros(7)
            if rel:
                nx, ny = x + nx, y + ny
            atual += _arco(x, y, rx, ry, phi, bool(grande), bool(horario), nx, ny)
            x, y = nx, ny
        elif c == "Z":
            atual.append((inicio_x, inicio_y))
            x, y = inicio_x, inicio_y
        else:
            raise ValueError(f"Comando SVG não suportado: {cmd}")
    if len(atual) > 1:
        linhas.append(atual)
    return linhas


def _primitivas(nome):
    linhas = []
    for prim in ICONES[nome]:
        if prim[0] == "p":
            linhas += _caminho(prim[1])
        elif prim[0] == "c":
            _, cx, cy, r = prim
            linhas.append([(cx + r * math.cos(t * math.pi / 24), cy + r * math.sin(t * math.pi / 24)) for t in range(49)])
        else:
            _, rx_, ry_, w, h, raio = prim
            d = (f"M{rx_ + raio} {ry_}h{w - 2 * raio}a{raio} {raio} 0 0 1 {raio} {raio}v{h - 2 * raio}"
                 f"a{raio} {raio} 0 0 1 -{raio} {raio}h-{w - 2 * raio}a{raio} {raio} 0 0 1 -{raio} -{raio}"
                 f"v-{h - 2 * raio}a{raio} {raio} 0 0 1 {raio} -{raio}Z")
            linhas += _caminho(d)
    return linhas


@lru_cache(maxsize=None)
def _imagem(nome, pixels, cor, traco):
    """Desenha o ícone em 4× e reduz: bordas suaves sem depender de antialias do Tk."""
    fator = 4
    lado = pixels * fator
    escala = lado / 24
    largura = max(1, round(traco * escala))
    img = Image.new("RGBA", (lado, lado), (0, 0, 0, 0))
    desenho = ImageDraw.Draw(img)
    raio = largura / 2
    for linha in _primitivas(nome):
        pontos = [(px * escala, py * escala) for px, py in linha]
        desenho.line(pontos, fill=cor, width=largura, joint="curve")
        for px, py in pontos:  # pontas e junções redondas
            desenho.ellipse((px - raio, py - raio, px + raio, py + raio), fill=cor)
    return img.resize((pixels, pixels), Image.LANCZOS)


@lru_cache(maxsize=None)
def icone(nome, tamanho=18, cor="#ffffff", traco=1.8):
    """CTkImage do ícone `nome`, no tamanho (px lógicos) e cor pedidos.

    nome=None devolve uma imagem transparente: o CTk ignora configure(image=None),
    então é assim que se "apaga" um ícone já mostrado.
    """
    if nome is None:
        img = Image.new("RGBA", (tamanho * 2, tamanho * 2), (0, 0, 0, 0))
    else:
        img = _imagem(nome, tamanho * 2, cor, traco)  # 2× para telas de alta densidade
    return ctk.CTkImage(light_image=img, dark_image=img, size=(tamanho, tamanho))

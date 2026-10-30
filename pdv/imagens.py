"""Imagens da loja (logo) e dos produtos (fotos), tratadas com Pillow.

A imagem escolhida pelo usuário nunca é usada direto: `preparar` abre e valida
o arquivo, corrige a rotação da câmera e reduz o tamanho; `gravar` salva uma
cópia PNG nova (sem metadados) em <pasta de dados>/imagens. No banco fica só o
NOME do arquivo, para continuar valendo se a pasta de dados mudar de lugar.

Para a tela, `imagem(nome, largura, altura)` devolve um CTkImage em cache, já
com os cantos arredondados. Se o arquivo sumiu ou está corrompido, devolve
None e quem chama mostra o visual de reserva (iniciais coloridas / carrinho),
sem erro para o operador.

Uso:
    img = imagens.preparar("/home/ana/foto.jpg", imagens.LADO_FOTO, quadrada=True)
    nome = imagens.gravar(img, "produto")
    imagens.imagem(nome, 52, 52)  ->  CTkImage ou None
"""

import os
from datetime import datetime
from functools import lru_cache

import customtkinter as ctk
from PIL import Image, ImageDraw, ImageOps

from . import banco

LADO_LOGO = 256                       # px do lado maior da logo gravada
LADO_FOTO = 192                       # px do lado da foto (quadrada) do produto
TAMANHO_MAXIMO = 20 * 1024 * 1024     # recusa arquivos maiores que 20 MB
TIPOS = [("Imagens", "*.png *.jpg *.jpeg *.webp *.bmp *.gif"), ("Todos", "*.*")]


class ImagemInvalida(Exception):
    """Arquivo que não abre como imagem (ou grande demais)."""


def _pasta():
    # Lida na hora: os testes trocam banco.PASTA_DADOS depois do import.
    return os.path.join(banco.PASTA_DADOS, "imagens")


def caminho(nome):
    """Caminho completo de uma imagem gravada (basename: o banco não aponta para fora da pasta)."""
    return os.path.join(_pasta(), os.path.basename(nome))


def preparar(origem, lado, quadrada=False):
    """Abre `origem`, valida e reduz. Quadrada = corta o centro (fotos de produto).

    Devolve uma imagem RGBA em memória (nada é gravado ainda). Lança ImagemInvalida.
    """
    try:
        if os.path.getsize(origem) > TAMANHO_MAXIMO:
            raise ImagemInvalida("O arquivo passa de 20 MB.")
        with Image.open(origem) as aberta:
            img = ImageOps.exif_transpose(aberta).convert("RGBA")
    except (OSError, ValueError, Image.DecompressionBombError) as erro:
        raise ImagemInvalida("O arquivo não é uma imagem válida.") from erro
    if quadrada:
        return ImageOps.fit(img, (lado, lado), Image.LANCZOS)
    img.thumbnail((lado, lado), Image.LANCZOS)
    return img


def gravar(img, prefixo):
    """Salva a imagem preparada como PNG com nome único. Devolve o nome do arquivo."""
    os.makedirs(_pasta(), mode=0o700, exist_ok=True)
    nome = f"{prefixo}-{datetime.now():%Y%m%d%H%M%S%f}.png"
    img.save(caminho(nome), "PNG", optimize=True)
    return nome


def remover(nome):
    """Apaga a cópia gravada (a imagem original do usuário nunca é tocada)."""
    if nome:
        try:
            os.remove(caminho(nome))
        except OSError:
            pass


def _arredondar(img, raio):
    mascara = Image.new("L", img.size, 0)
    ImageDraw.Draw(mascara).rounded_rectangle((0, 0, img.width - 1, img.height - 1), raio, fill=255)
    img.putalpha(Image.composite(img.getchannel("A"), mascara, mascara))
    return img


def para_tela(img, largura, altura, raio=10, cobrir=True, fundo=None, margem=0):
    """CTkImage de uma imagem em memória. cobrir=True corta para preencher; False encaixa inteira.

    fundo/margem (só com cobrir=False): placa arredondada da cor `fundo` atrás da imagem, que fica
    afastada `margem` px da borda — é o "selo" da logo, desenhado aqui porque o CTkLabel com
    corner_radius alarga a área da imagem.
    """
    fator = 2  # 2× para telas de alta densidade
    caixa = (largura * fator, altura * fator)
    if cobrir:
        img = _arredondar(ImageOps.fit(img, caixa, Image.LANCZOS).convert("RGBA"), raio * fator) if raio else \
            ImageOps.fit(img, caixa, Image.LANCZOS)
    else:
        dentro = (caixa[0] - 2 * margem * fator, caixa[1] - 2 * margem * fator)
        encaixada = ImageOps.contain(img, dentro, Image.LANCZOS)
        placa = Image.new("RGBA", caixa, (0, 0, 0, 0))
        if fundo:
            ImageDraw.Draw(placa).rounded_rectangle((0, 0, caixa[0] - 1, caixa[1] - 1), raio * fator, fill=fundo)
        placa.alpha_composite(encaixada, ((caixa[0] - encaixada.width) // 2, (caixa[1] - encaixada.height) // 2))
        img = placa
    return ctk.CTkImage(light_image=img, dark_image=img, size=(largura, altura))


@lru_cache(maxsize=512)
def imagem(nome, largura, altura, raio=10, cobrir=True, fundo=None, margem=0):
    """CTkImage em cache de uma imagem gravada; None se não há nome ou o arquivo não abre."""
    if not nome:
        return None
    try:
        with Image.open(caminho(nome)) as aberta:
            img = aberta.convert("RGBA")
    except (OSError, ValueError, Image.DecompressionBombError):
        return None
    return para_tela(img, largura, altura, raio, cobrir, fundo, margem)

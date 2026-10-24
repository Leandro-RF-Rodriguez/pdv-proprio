import sqlite3

def criar_banco():
    conexao = sqlite3.connect("pdv.db")
    with open("schema.sql", "r", encoding="utf-8") as arquivo:
        conexao.executescript(arquivo.read())
    conexao.close()
    print("Banco pdv.db criado com sucesso.")

if __name__ == "__main__":
    criar_banco()

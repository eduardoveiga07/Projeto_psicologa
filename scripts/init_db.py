import os
import sys

# Garante o default de desenvolvimento para não bloquear boot localmente
os.environ.setdefault("AMBIENTE", "desenvolvimento")

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.db.session import criar_tabelas
from app.auth.init_users import inicializar_usuarios

if __name__ == "__main__":
    print("Iniciando banco de dados (Alembic)...")
    criar_tabelas()
    print("Inicializando usuários padrão...")
    inicializar_usuarios()
    print("Banco de dados pronto para uso.")

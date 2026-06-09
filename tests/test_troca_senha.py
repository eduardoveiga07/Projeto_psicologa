from types import SimpleNamespace
import unittest

from app.auth.login import gerar_hash, verificar_senha
from app.auth.senha_service import trocar_senha_usuario


class QueryFake:
    def __init__(self, usuario):
        self.usuario = usuario

    def filter(self, *args):
        return self

    def first(self):
        return self.usuario


class DbFake:
    def __init__(self, usuario):
        self.usuario = usuario
        self.commits = 0

    def query(self, model):
        return QueryFake(self.usuario)

    def commit(self):
        self.commits += 1


class TrocaSenhaTest(unittest.TestCase):
    def test_troca_senha_com_sucesso(self):
        usuario = SimpleNamespace(
            username="dona",
            ativo=True,
            senha_hash=gerar_hash("SenhaAtual@1"),
        )
        db = DbFake(usuario)

        ok, msg = trocar_senha_usuario(
            db, "dona", "SenhaAtual@1", "NovaSenha@1", "NovaSenha@1")

        self.assertTrue(ok)
        self.assertEqual(msg, "Senha alterada com sucesso.")
        self.assertEqual(db.commits, 1)
        self.assertTrue(verificar_senha("NovaSenha@1", usuario.senha_hash))

    def test_rejeita_senha_atual_invalida(self):
        usuario = SimpleNamespace(
            username="dona",
            ativo=True,
            senha_hash=gerar_hash("SenhaAtual@1"),
        )
        db = DbFake(usuario)

        ok, msg = trocar_senha_usuario(
            db, "dona", "Errada@1", "NovaSenha@1", "NovaSenha@1")

        self.assertFalse(ok)
        self.assertEqual(msg, "Senha atual invalida.")
        self.assertEqual(db.commits, 0)

    def test_rejeita_confirmacao_diferente(self):
        usuario = SimpleNamespace(
            username="dona",
            ativo=True,
            senha_hash=gerar_hash("SenhaAtual@1"),
        )
        db = DbFake(usuario)

        ok, msg = trocar_senha_usuario(
            db, "dona", "SenhaAtual@1", "NovaSenha@1", "OutraSenha@1")

        self.assertFalse(ok)
        self.assertEqual(msg, "As senhas nao conferem.")
        self.assertEqual(db.commits, 0)


if __name__ == "__main__":
    unittest.main()

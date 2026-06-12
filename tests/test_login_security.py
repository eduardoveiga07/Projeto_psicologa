import unittest
from datetime import datetime, timedelta
from app.auth.login import autenticar, gerar_hash
from app.db.models import Usuario

class QueryFake:
    def __init__(self, usuario):
        self.usuario = usuario

    def filter(self, *args):
        # Simula a busca pelo username correspondente
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

class LoginSecurityTest(unittest.TestCase):
    def setUp(self):
        # Cria um usuário padrão para testes
        self.user = Usuario(
            username="dona",
            nome="Dona Admin",
            ativo=True,
            senha_hash=gerar_hash("SenhaValida123!"),
            tentativas_login=0,
            bloqueado_ate=None,
            trocar_senha_proximo_login=False
        )
        self.db = DbFake(self.user)

    def test_login_sucesso(self):
        # Login com credenciais válidas deve retornar o usuário e status 'ok'
        u, status = autenticar(self.db, "dona", "SenhaValida123!")
        self.assertIsNotNone(u)
        self.assertEqual(status, "ok")
        self.assertEqual(u.tentativas_login, 0)
        self.assertIsNone(u.bloqueado_ate)

    def test_login_senha_incorreta_incrementa_tentativas(self):
        # Errar a senha deve retornar erro e incrementar as tentativas
        u, msg = autenticar(self.db, "dona", "SenhaIncorreta!")
        self.assertIsNone(u)
        self.assertIn("Você tem mais 4 tentativas", msg)
        self.assertEqual(self.user.tentativas_login, 1)
        self.assertEqual(self.db.commits, 1)

    def test_login_bloqueio_apos_5_tentativas(self):
        # 5 tentativas erradas devem bloquear o usuário por 15 minutos
        for i in range(4):
            u, msg = autenticar(self.db, "dona", "SenhaIncorreta!")
            self.assertIsNone(u)
            self.assertEqual(self.user.tentativas_login, i + 1)
            
        # 5ª tentativa
        u, msg = autenticar(self.db, "dona", "SenhaIncorreta!")
        self.assertIsNone(u)
        self.assertEqual(self.user.tentativas_login, 5)
        self.assertIn("Conta bloqueada por 15 minutos", msg)
        self.assertIsNotNone(self.user.bloqueado_ate)
        
        # Próxima tentativa (mesmo com senha correta) deve ser recusada devido ao bloqueio
        u, msg = autenticar(self.db, "dona", "SenhaValida123!")
        self.assertIsNone(u)
        self.assertIn("Conta bloqueada temporariamente", msg)

    def test_login_reset_tentativas_apos_sucesso(self):
        # Se errar 3 vezes e depois acertar, o contador deve zerar
        for _ in range(3):
            autenticar(self.db, "dona", "SenhaIncorreta!")
        self.assertEqual(self.user.tentativas_login, 3)
        
        # Login de sucesso
        u, status = autenticar(self.db, "dona", "SenhaValida123!")
        self.assertIsNotNone(u)
        self.assertEqual(status, "ok")
        self.assertEqual(self.user.tentativas_login, 0)

    def test_login_troca_senha_obrigatoria(self):
        # Quando trocar_senha_proximo_login for True, status deve ser 'trocar_senha'
        self.user.trocar_senha_proximo_login = True
        u, status = autenticar(self.db, "dona", "SenhaValida123!")
        self.assertIsNotNone(u)
        self.assertEqual(status, "trocar_senha")

if __name__ == "__main__":
    unittest.main()

import unittest
import sys
sys.path.append('c:/Users/eduar/Downloads/projeto_consultorio')

from app.db.models import Perfil
from app.auth.usuario_validacao import obter_telas_permitidas


class AuditoriaViewTest(unittest.TestCase):
    def test_dona_tem_acesso_auditoria(self):
        telas = obter_telas_permitidas(Perfil.DONA.value)
        self.assertIn("Auditoria", telas)
        self.assertIn("Usuários", telas)
        self.assertIn("Financeiro", telas)

    def test_programador_tem_acesso_auditoria(self):
        telas = obter_telas_permitidas(Perfil.PROGRAMADOR.value)
        self.assertIn("Auditoria", telas)
        self.assertIn("Usuários", telas)
        self.assertIn("Financeiro", telas)

    def test_secretaria_nao_tem_acesso_auditoria(self):
        telas = obter_telas_permitidas(Perfil.SECRETARIA.value)
        self.assertNotIn("Auditoria", telas)
        self.assertNotIn("Usuários", telas)
        self.assertNotIn("Financeiro", telas)
        self.assertIn("Cadastro", telas)
        self.assertIn("Agenda", telas)

    def test_financeiro_nao_tem_acesso_auditoria(self):
        telas = obter_telas_permitidas(Perfil.FINANCEIRO.value)
        self.assertNotIn("Auditoria", telas)
        self.assertNotIn("Usuários", telas)
        self.assertIn("Financeiro", telas)
        self.assertIn("Pagamentos", telas)
        self.assertNotIn("Cadastro", telas)


if __name__ == "__main__":
    unittest.main()

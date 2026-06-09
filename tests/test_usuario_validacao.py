import unittest

from app.auth.usuario_validacao import (
    normalizar_username,
    validar_email_opcional,
    validar_nome,
    validar_username,
)


class UsuarioValidacaoTest(unittest.TestCase):
    def test_normaliza_username(self):
        self.assertEqual(normalizar_username(" Dona.Admin "), "dona.admin")

    def test_valida_username_restrito(self):
        self.assertEqual(validar_username("adm_01")[0], True)
        self.assertEqual(validar_username("ab")[0], False)
        self.assertEqual(validar_username("admin com espaco")[0], False)

    def test_valida_nome_obrigatorio(self):
        self.assertEqual(validar_nome("Dona do Consultorio")[0], True)
        self.assertEqual(validar_nome("  ")[0], False)

    def test_valida_email_opcional(self):
        self.assertEqual(validar_email_opcional("")[0], True)
        self.assertEqual(validar_email_opcional("dona@example.com")[0], True)
        self.assertEqual(validar_email_opcional("email-invalido")[0], False)


if __name__ == "__main__":
    unittest.main()

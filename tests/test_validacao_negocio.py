import unittest
from datetime import date, timedelta
from decimal import Decimal
import sys
sys.path.append('c:/Users/eduar/Downloads/projeto_consultorio')

from app.services.validacao_negocio import (
    validar_telefone,
    validar_email_paciente,
    validar_data_nascimento,
    validar_valor_sessao,
    validar_valor_despesa,
    validar_datas_bloqueio
)


class ValidacaoNegocioTest(unittest.TestCase):

    def test_validar_telefone_valido(self):
        # Diversos formatos válidos comuns
        self.assertEqual(validar_telefone("+55 (11) 99999-9999"), (True, "5511999999999"))
        self.assertEqual(validar_telefone("11999999999"), (True, "11999999999"))
        self.assertEqual(validar_telefone("9999-9999"), (True, "99999999"))
        self.assertEqual(validar_telefone("+1 555-555-5555"), (True, "15555555555"))

    def test_validar_telefone_invalido(self):
        # Contendo letras
        self.assertFalse(validar_telefone("1199999aaaa")[0])
        # Muito curto (menos de 8 dígitos numéricos)
        self.assertFalse(validar_telefone("1234567")[0])
        # Muito longo (mais de 15 dígitos numéricos)
        self.assertFalse(validar_telefone("1234567890123456")[0])
        # Vazio
        self.assertFalse(validar_telefone("")[0])
        self.assertFalse(validar_telefone(None)[0])

    def test_validar_email_opcional(self):
        # Vazio ou None é válido (opcional)
        self.assertEqual(validar_email_paciente(""), (True, ""))
        self.assertEqual(validar_email_paciente(None), (True, ""))
        # Formatos válidos
        self.assertEqual(validar_email_paciente("paciente@example.com"), (True, "paciente@example.com"))
        self.assertEqual(validar_email_paciente("  user.name@domain.co.uk  "), (True, "user.name@domain.co.uk"))
        # Formatos inválidos
        self.assertFalse(validar_email_paciente("invalido")[0])
        self.assertFalse(validar_email_paciente("usuario@")[0])
        self.assertFalse(validar_email_paciente("@dominio.com")[0])

    def test_validar_data_nascimento(self):
        hoje = date.today()
        passado = hoje - timedelta(days=365 * 30)
        futuro = hoje + timedelta(days=1)
        
        # Passado é válido
        self.assertTrue(validar_data_nascimento(passado)[0])
        # Hoje ou Futuro são inválidos
        self.assertFalse(validar_data_nascimento(hoje)[0])
        self.assertFalse(validar_data_nascimento(futuro)[0])
        self.assertFalse(validar_data_nascimento(None)[0])

    def test_validar_valor_sessao(self):
        # Paciente recorrente (em_avaliacao=False)
        self.assertTrue(validar_valor_sessao(Decimal("150.00"), em_avaliacao=False)[0])
        self.assertFalse(validar_valor_sessao(Decimal("0.00"), em_avaliacao=False)[0])
        self.assertFalse(validar_valor_sessao(Decimal("-10.00"), em_avaliacao=False)[0])
        self.assertFalse(validar_valor_sessao(None, em_avaliacao=False)[0])

        # Avaliação (em_avaliacao=True)
        self.assertTrue(validar_valor_sessao(Decimal("150.00"), em_avaliacao=True)[0])
        self.assertTrue(validar_valor_sessao(Decimal("0.00"), em_avaliacao=True)[0]) # Gratuita
        self.assertFalse(validar_valor_sessao(Decimal("-10.00"), em_avaliacao=True)[0])

    def test_validar_valor_despesa(self):
        # Positivo maior que zero
        self.assertTrue(validar_valor_despesa(Decimal("500.00"))[0])
        # Zero ou negativo
        self.assertFalse(validar_valor_despesa(Decimal("0.00"))[0])
        self.assertFalse(validar_valor_despesa(Decimal("-50.00"))[0])
        self.assertFalse(validar_valor_despesa(None)[0])

    def test_validar_datas_bloqueio(self):
        hoje = date.today()
        futuro = hoje + timedelta(days=5)
        
        # Intervalo correto
        self.assertTrue(validar_datas_bloqueio(hoje, futuro)[0])
        self.assertTrue(validar_datas_bloqueio(hoje, hoje)[0])
        # Intervalo invertido
        self.assertFalse(validar_datas_bloqueio(futuro, hoje)[0])
        self.assertFalse(validar_datas_bloqueio(None, hoje)[0])


if __name__ == "__main__":
    unittest.main()

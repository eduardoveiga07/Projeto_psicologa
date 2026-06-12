import unittest
import sys
sys.path.append('c:/Users/eduar/Downloads/projeto_consultorio')

from app.services.pdf_export import gerar_pdf


class PdfExportTest(unittest.TestCase):
    def test_gerar_pdf_simples_retorna_bytes_pdf(self):
        linhas = [
            {"Nome": "Fulano", "Idade": "30", "Cidade": "São Paulo"},
            {"Nome": "Beltrano", "Idade": "25", "Cidade": "Rio de Janeiro"}
        ]
        
        pdf_bytes = gerar_pdf("Relatório Simples", linhas)
        
        self.assertIsInstance(pdf_bytes, bytes)
        # Cabeçalho padrão de assinatura de arquivo PDF
        self.assertTrue(pdf_bytes.startswith(b"%PDF-"))

    def test_gerar_pdf_com_filtros_e_totais(self):
        linhas = [
            {"Paciente": "Paciente A", "Faturamento Realizado": "R$ 150,00"},
            {"Paciente": "Paciente B", "Faturamento Realizado": "R$ 200,00"}
        ]
        filtros = {
            "Mês": "06/2026",
            "Usuário": "Dona"
        }
        totais = {
            "Faturamento Realizado": "R$ 350,00"
        }
        
        pdf_bytes = gerar_pdf("Financeiro", linhas, filtros=filtros, totais=totais)
        
        self.assertIsInstance(pdf_bytes, bytes)
        self.assertTrue(pdf_bytes.startswith(b"%PDF-"))

    def test_gerar_pdf_lista_vazia(self):
        pdf_bytes = gerar_pdf("Sem Dados", [])
        
        self.assertIsInstance(pdf_bytes, bytes)
        self.assertTrue(pdf_bytes.startswith(b"%PDF-"))


if __name__ == "__main__":
    unittest.main()

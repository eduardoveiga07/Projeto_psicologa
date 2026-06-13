"""Testes do serviço de comprovantes: validação de tipo, tamanho e sanitização."""
import unittest
import sys
import os
import tempfile
from io import BytesIO
from datetime import datetime

sys.path.append('c:/Users/eduar/Downloads/projeto_consultorio')

from app.services.comprovantes import (
    validar_upload, salvar_comprovante, deletar_comprovante,
    obter_comprovante_caminho, aplicar_metadados_comprovante,
    limpar_metadados_comprovante, _sanitizar_nome,
    ComprovantesError, TAMANHO_MAXIMO_BYTES
)


class _MockFile:
    """Simula o objeto retornado por st.file_uploader."""
    def __init__(self, name: str, data: bytes):
        self.name = name
        self._data = data

    def getbuffer(self):
        return self._data


class SanitizarNomeTest(unittest.TestCase):
    def test_remove_acentos(self):
        resultado = _sanitizar_nome("comprovante-março.pdf")
        self.assertIn(".pdf", resultado)
        self.assertNotIn("ç", resultado)
        self.assertNotIn("ã", resultado)

    def test_remove_espacos(self):
        resultado = _sanitizar_nome("meu comprovante 2024.jpg")
        self.assertNotIn(" ", resultado)

    def test_preserva_extensao_minuscula(self):
        resultado = _sanitizar_nome("Recibo.PDF")
        self.assertTrue(resultado.endswith(".pdf"))

    def test_nome_vazio_recebe_fallback(self):
        # Arquivo com apenas extensão — a função não deve retornar string vazia
        resultado = _sanitizar_nome(".pdf")
        self.assertTrue(len(resultado) > 0)


class ValidarUploadTest(unittest.TestCase):
    def test_tipo_invalido_lanca_erro(self):
        arq = _MockFile("malware.exe", b"conteudo")
        with self.assertRaises(ComprovantesError) as ctx:
            validar_upload(arq)
        self.assertIn("não permitido", str(ctx.exception))

    def test_arquivo_vazio_lanca_erro(self):
        arq = _MockFile("recibo.pdf", b"")
        with self.assertRaises(ComprovantesError) as ctx:
            validar_upload(arq)
        self.assertIn("vazio", str(ctx.exception))

    def test_arquivo_acima_limite_lanca_erro(self):
        # 11 MB > 10 MB de limite
        dados_grandes = b"x" * (11 * 1024 * 1024)
        arq = _MockFile("grande.pdf", dados_grandes)
        with self.assertRaises(ComprovantesError) as ctx:
            validar_upload(arq)
        self.assertIn("grande", str(ctx.exception).lower())

    def test_pdf_valido_nao_lanca_erro(self):
        arq = _MockFile("recibo.pdf", b"%PDF valido")
        validar_upload(arq)  # não deve lançar

    def test_png_valido_nao_lanca_erro(self):
        arq = _MockFile("foto.png", b"\x89PNG\r\n valido")
        validar_upload(arq)  # não deve lançar

    def test_jpg_valido_nao_lanca_erro(self):
        arq = _MockFile("foto.jpg", b"\xff\xd8\xff valido")
        validar_upload(arq)  # não deve lançar

    def test_jpeg_maiusculo_aceito(self):
        arq = _MockFile("foto.JPEG", b"\xff\xd8\xff valido")
        validar_upload(arq)  # não deve lançar (extensão normalizada)

    def test_none_nao_lanca_erro(self):
        validar_upload(None)  # None é aceito (campo opcional)


class SalvarComprovanteDiscoTest(unittest.TestCase):
    """Testa o ciclo completo de salvar → verificar → deletar no filesystem."""

    def test_ciclo_salvar_e_deletar(self):
        # Sobrescreve UPLOAD_DIR para usar diretório temporário
        import app.services.comprovantes as svc
        tmpdir = tempfile.mkdtemp()
        svc.UPLOAD_DIR = tmpdir

        arq = _MockFile("nota_fiscal.pdf", b"%PDF-1.4 conteudo real")
        meta = salvar_comprovante(arq, "despesa", 42)

        # Verifica retorno de metadados
        self.assertIsNotNone(meta)
        self.assertIn("nome", meta)
        self.assertIn("nome_original", meta)
        self.assertIn("mime", meta)
        self.assertIn("tamanho", meta)
        self.assertIn("enviado_em", meta)

        # Verifica que arquivo existe no disco
        caminho = obter_comprovante_caminho(meta["nome"])
        self.assertTrue(os.path.exists(caminho))

        # Verifica MIME correto para PDF
        self.assertEqual(meta["mime"], "application/pdf")

        # Verifica nome original preservado
        self.assertEqual(meta["nome_original"], "nota_fiscal.pdf")

        # Deleta e verifica remoção
        removido = deletar_comprovante(meta["nome"])
        self.assertTrue(removido)
        self.assertFalse(os.path.exists(caminho))


class MetadadosORMTest(unittest.TestCase):
    """Testa helpers de aplicar/limpar metadados em objetos ORM mock."""

    def _mock_registro(self):
        class Registro:
            comprovante_nome = None
            comprovante_nome_original = None
            comprovante_mime = None
            comprovante_tamanho = None
            comprovante_enviado_em = None
        return Registro()

    def test_aplicar_metadados(self):
        reg = self._mock_registro()
        meta = {
            "nome": "despesa_42_1234.pdf",
            "nome_original": "nota_fiscal.pdf",
            "mime": "application/pdf",
            "tamanho": 5120,
            "enviado_em": datetime(2026, 6, 13, 10, 30),
        }
        aplicar_metadados_comprovante(reg, meta)
        self.assertEqual(reg.comprovante_nome, "despesa_42_1234.pdf")
        self.assertEqual(reg.comprovante_nome_original, "nota_fiscal.pdf")
        self.assertEqual(reg.comprovante_mime, "application/pdf")
        self.assertEqual(reg.comprovante_tamanho, 5120)
        self.assertEqual(reg.comprovante_enviado_em, datetime(2026, 6, 13, 10, 30))

    def test_limpar_metadados(self):
        reg = self._mock_registro()
        reg.comprovante_nome = "despesa_42_1234.pdf"
        reg.comprovante_nome_original = "nota.pdf"
        reg.comprovante_mime = "application/pdf"
        reg.comprovante_tamanho = 1024
        reg.comprovante_enviado_em = datetime(2026, 6, 13, 10, 30)

        limpar_metadados_comprovante(reg)

        self.assertIsNone(reg.comprovante_nome)
        self.assertIsNone(reg.comprovante_nome_original)
        self.assertIsNone(reg.comprovante_mime)
        self.assertIsNone(reg.comprovante_tamanho)
        self.assertIsNone(reg.comprovante_enviado_em)

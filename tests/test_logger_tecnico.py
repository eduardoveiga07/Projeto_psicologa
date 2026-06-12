import unittest
import os
import sys

sys.path.append('c:/Users/eduar/Downloads/projeto_consultorio')

from app.services.logger import get_logger, logger as raiz_logger


class LoggerTecnicoTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.log_dir = "logs"
        cls.log_file = os.path.join(cls.log_dir, "tecnico.log")

    def test_get_logger_retorna_logger_filho(self):
        filho = get_logger("modulo_teste")
        self.assertEqual(filho.name, "consultorio_tecnico.modulo_teste")

    def test_logger_grava_mensagem_em_arquivo(self):
        # Envia uma mensagem de teste única
        test_msg = "Mensagem de teste unitario do logger tecnico"
        filho = get_logger("teste_unitario")
        filho.info(test_msg)

        # Força o esvaziamento (flush) dos handlers do logger para garantir a gravação física
        for handler in raiz_logger.handlers:
            handler.flush()

        # Verifica se o arquivo de logs foi criado
        self.assertTrue(os.path.exists(self.log_file), "O arquivo tecnico.log nao foi criado.")

        # Verifica se a mensagem de teste foi escrita no arquivo
        with open(self.log_file, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("INFO", content)
        self.assertIn("teste_unitario", content)
        self.assertIn(test_msg, content)


if __name__ == "__main__":
    unittest.main()

import unittest
import os
import sys

sys.path.append('c:/Users/eduar/Downloads/projeto_consultorio')


class NginxConfigTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config_path = "c:/Users/eduar/Downloads/projeto_consultorio/nginx/conf.d/app.conf"

    def test_arquivo_config_existe(self):
        self.assertTrue(os.path.exists(self.config_path), "O arquivo de configuração do Nginx não existe.")

    def test_configuracao_segura_nginx(self):
        with open(self.config_path, "r", encoding="utf-8") as f:
            content = f.read()

        # 1. Garante que escuta nas portas HTTP e HTTPS corretas
        self.assertIn("listen 80;", content)
        self.assertIn("listen 443 ssl;", content)

        # 2. Garante que oculta a versão do Nginx por segurança
        self.assertIn("server_tokens off;", content)

        # 3. Garante que ativa apenas protocolos de transporte seguros
        self.assertIn("ssl_protocols TLSv1.2 TLSv1.3;", content)

        # 4. Garante que aponta para o container app na porta interna 8501
        self.assertIn("proxy_pass http://app:8501;", content)

        # 5. Garante que contém cabeçalhos de segurança contra clickjacking, MIME-sniffing e XSS
        self.assertIn('add_header X-Frame-Options "SAMEORIGIN" always;', content)
        self.assertIn('add_header X-Content-Type-Options "nosniff" always;', content)
        self.assertIn('add_header X-XSS-Protection "1; mode=block" always;', content)

        # 6. Garante que configura cabeçalhos obrigatórios para WebSockets do Streamlit
        self.assertIn("proxy_set_header Upgrade $http_upgrade;", content)
        self.assertIn('proxy_set_header Connection "upgrade";', content)


if __name__ == "__main__":
    unittest.main()

import unittest
import time
import os
from unittest.mock import patch
from app.db.models import Perfil
from app.auth.sessao import (
    criar_token_sessao,
    validar_token,
    renovar_token,
    _obter_timeout_seconds
)


class SessaoTest(unittest.TestCase):
    def test_token_valido_recem_criado_e_aceito(self):
        # 1. Cria token válido
        token = criar_token_sessao(
            usuario_id="abc-123",
            username="test_user",
            perfil=Perfil.DONA
        )
        self.assertIsNotNone(token)
        self.assertIsInstance(token, str)

        # 2. Valida token
        payload = validar_token(token)
        self.assertIsNotNone(payload)
        self.assertEqual(payload["usuario_id"], "abc-123")
        self.assertEqual(payload["username"], "test_user")
        self.assertEqual(payload["perfil"], Perfil.DONA) # Deve retornar como Enum
        self.assertGreater(payload["expira_em"], time.time())

    def test_token_expirado_e_rejeitado(self):
        # Cria token com expiração no passado forçando o timeout para -1 minuto
        with patch.dict(os.environ, {"SESSION_TIMEOUT_MINUTES": "-1"}):
            token = criar_token_sessao(
                usuario_id="abc-123",
                username="test_user",
                perfil=Perfil.DONA
            )
            payload = validar_token(token)
            self.assertIsNone(payload)

    def test_token_adulterado_e_rejeitado(self):
        # 1. Cria token válido
        token = criar_token_sessao(
            usuario_id="abc-123",
            username="test_user",
            perfil=Perfil.DONA
        )
        
        # 2. Adulterar o token (ex: adicionando ou trocando caracteres)
        adulterated_token = token[:-4] + "AAAA"
        
        # 3. Validar token adulterado deve falhar silenciosamente (retornar None)
        payload = validar_token(adulterated_token)
        self.assertIsNone(payload)

    def test_token_vazio_ou_ausente_retorna_none_sem_excecao(self):
        self.assertIsNone(validar_token(None))
        self.assertIsNone(validar_token(""))

    def test_renovar_token_estende_expiracao(self):
        token = criar_token_sessao(
            usuario_id="abc-123",
            username="test_user",
            perfil=Perfil.DONA
        )
        payload = validar_token(token)
        self.assertIsNotNone(payload)
        
        # Espera um instante pequeno e renova
        token_renovado = renovar_token(payload)
        self.assertIsNotNone(token_renovado)
        self.assertNotEqual(token, token_renovado)
        
        payload_renovado = validar_token(token_renovado)
        self.assertIsNotNone(payload_renovado)
        self.assertEqual(payload_renovado["usuario_id"], "abc-123")
        self.assertEqual(payload_renovado["perfil"], Perfil.DONA)
        self.assertGreater(payload_renovado["expira_em"], payload["expira_em"])

    def test_obter_timeout_seconds_override(self):
        # Valor padrão
        with patch.dict(os.environ, {}):
            if "SESSION_TIMEOUT_MINUTES" in os.environ:
                del os.environ["SESSION_TIMEOUT_MINUTES"]
            self.assertEqual(_obter_timeout_seconds(), 30 * 60)

        # Com override
        with patch.dict(os.environ, {"SESSION_TIMEOUT_MINUTES": "45"}):
            self.assertEqual(_obter_timeout_seconds(), 45 * 60)

        # Com valor inválido (cai no padrão)
        with patch.dict(os.environ, {"SESSION_TIMEOUT_MINUTES": "invalido"}):
            self.assertEqual(_obter_timeout_seconds(), 30 * 60)


if __name__ == "__main__":
    unittest.main()

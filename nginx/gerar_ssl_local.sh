#!/bin/bash
# Cria o diretório de certificados se não existir
mkdir -p nginx/certs

echo "Gerando certificados SSL autoassinados locais usando Docker..."

# Executa o OpenSSL em um container temporário para gerar os certificados direto na pasta montada
docker run --rm -v "$(pwd)/nginx/certs:/certs" alpine/openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout /certs/privkey.pem \
  -out /certs/fullchain.pem \
  -subj "/C=BR/ST=SP/L=Sao Paulo/O=Consultorio/OU=Desenvolvimento/CN=localhost"

# Ajusta as permissões se for Linux/Mac
chmod 644 nginx/certs/privkey.pem nginx/certs/fullchain.pem 2>/dev/null

echo "Certificados locais (fullchain.pem e privkey.pem) gerados em nginx/certs/!"

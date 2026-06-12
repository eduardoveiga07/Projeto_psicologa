# Garante o diretório de certificados
if (-not (Test-Path -Path "nginx/certs")) {
    New-Item -ItemType Directory -Path "nginx/certs" | Out-Null
}

Write-Host "Gerando certificados SSL autoassinados locais usando Docker..." -ForegroundColor Cyan

# Executa o OpenSSL em um container temporário para gerar os certificados na pasta montada
$pwdPath = (Get-Location).Path
docker run --rm -v "${pwdPath}/nginx/certs:/certs" alpine/openssl req -x509 -nodes -days 365 -newkey rsa:2048 `
  -keyout /certs/privkey.pem `
  -out /certs/fullchain.pem `
  -subj "/C=BR/ST=SP/L=Sao Paulo/O=Consultorio/OU=Desenvolvimento/CN=localhost"

Write-Host "Certificados locais (fullchain.pem e privkey.pem) gerados com sucesso em nginx/certs/!" -ForegroundColor Green

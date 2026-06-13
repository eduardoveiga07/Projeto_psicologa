# Manual de Produção Operacional — Sistema de Consultório

Este documento serve como o guia técnico oficial para deploy, atualização, rotina de backups, conformidade de segurança/LGPD e planos de contingência do sistema de gestão do consultório de psicologia em ambiente de produção (VPS).

---

## 1. Requisitos do Sistema

Para rodar a aplicação em produção, a máquina servidora (VPS) deve possuir:
- **Sistema Operacional**: Linux (Ubuntu 20.04 LTS ou superior recomendado)
- **Docker**: v20.10+ instalado e ativo
- **Docker Compose**: v2.0+ instalado
- **Git**: Para controle de versão e deploy automático

---

## 2. Deploy Inicial (Passo a Passo)

Siga estas instruções para configurar a aplicação do zero na VPS:

### Passo 1: Clonar o Repositório
Clone o repositório oficial na pasta `/var/www/projeto_consultorio`:
```bash
sudo mkdir -p /var/www/projeto_consultorio
sudo chown -R $USER:$USER /var/www/projeto_consultorio
git clone https://github.com/seu-usuario/projeto_consultorio.git /var/www/projeto_consultorio
cd /var/www/projeto_consultorio
```

### Passo 2: Configurar Variáveis de Ambiente (`.env`)
Copie o template de produção para o arquivo oficial `.env`:
```bash
cp .env.prod .env
```
Edite o arquivo `.env` gerado utilizando um editor de texto (ex: `nano .env`) e preencha as variáveis de ambiente com credenciais seguras:
- **DATABASE_URL**: Link de conexão segura com o PostgreSQL interno.
- **SECRET_KEY**: Chave secreta de sessão (gere uma com `openssl rand -hex 32`).
- **BACKUP_ENCRYPTION_KEY**: Chave Fernet de 32 bytes codificada em base64. **Gere esta chave rodando**:
  ```bash
  python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
  ```
  > [!IMPORTANT]
  > Mantenha a chave `BACKUP_ENCRYPTION_KEY` salva em local seguro e externo (como um cofre de senhas). Sem ela, será impossível descriptografar e restaurar qualquer backup de banco de dados caso o servidor sofra sinistro.

### Passo 3: Subir os Contêineres Docker
Inicie os serviços do banco de dados, aplicação Streamlit e servidor Nginx (reverso com HTTPS):
```bash
docker compose up -d --build
```

### Passo 4: Aplicar as Migrações do Banco de Dados
Com os contêineres ativos, aplique o esquema mais recente do banco de dados utilizando as migrações do Alembic:
```bash
docker compose exec -T app alembic upgrade head
```

### Passo 5: Configurar Certificado SSL Real (Let's Encrypt)
Em produção, você deve substituir os certificados autoassinados locais por certificados reais e válidos do Let's Encrypt:

1. **Obtenha os certificados reais rodando o Certbot em um contêiner temporário**:
   Substitua `seu-dominio.com` e `seu-email@dominio.com` com as informações corretas da sua VPS:
   ```bash
   docker run --rm -it \
     -v "/var/www/projeto_consultorio/nginx/html:/usr/share/nginx/html" \
     -v "projeto_consultorio_certbot-etc:/etc/letsencrypt" \
     -v "projeto_consultorio_certbot-var:/var/lib/letsencrypt" \
     certbot/certbot certonly --webroot -w /usr/share/nginx/html \
     -d seu-dominio.com -d www.seu-dominio.com \
     --email seu-email@exemplo.com --agree-tos --no-eff-email
   ```

2. **Crie links simbólicos para que o Nginx utilize os certificados reais gerados**:
   ```bash
   # Remova os certificados locais de teste
   rm -f nginx/certs/fullchain.pem nginx/certs/privkey.pem

   # Crie links simbólicos apontando para os certificados Let's Encrypt no volume mapeado
   ln -sf /etc/letsencrypt/live/seu-dominio.com/fullchain.pem nginx/certs/fullchain.pem
   ln -sf /etc/letsencrypt/live/seu-dominio.com/privkey.pem nginx/certs/privkey.pem
   ```

3. **Reinicie o Nginx para aplicar os novos certificados**:
   ```bash
   docker compose restart nginx
   ```

---

## 3. Fluxo de Atualização (Deploy Seguro)

### Opção A: Deploy Automático (GitHub Actions)
A pipeline de CI/CD está configurada no arquivo [.github/workflows/ci.yml](file:///.github/workflows/ci.yml). Toda vez que houver um `push` na branch `main`, se os testes passarem, o workflow executará SSH na VPS utilizando chaves criptográficas seguras.

Para habilitar essa automação, cadastre os seguintes segredos no painel do seu repositório no GitHub (em **Settings -> Secrets and variables -> Actions -> New repository secret**):
- `VPS_HOST`: O endereço IP público ou domínio da sua VPS.
- `VPS_USERNAME`: O usuário administrativo SSH do servidor (ex: `root` ou `ubuntu`).
- `VPS_SSH_KEY`: O conteúdo da chave privada SSH gerada exclusivamente para o deploy. Certifique-se de que a respectiva chave pública esteja adicionada ao arquivo `~/.ssh/authorized_keys` do usuário na VPS.

### Opção B: Deploy Manual na VPS
Caso necessite rodar a atualização manualmente direto no servidor, execute a rotina na raiz do projeto:
```bash
# 1. Puxar código atualizado
git pull origin main

# 2. Reconstruir a imagem da aplicação e reiniciar contêineres de forma limpa
docker compose down
docker compose up -d --build

# 3. Aplicar as migrações mais recentes do Alembic
docker compose exec -T app alembic upgrade head
```

---

## 4. Gestão de Backups e Restauração Criptografados

O sistema conta com rotinas automatizadas para resguardar a integridade dos dados dos pacientes sob criptografia militar (AES-128 GCM/Fernet).

### 4.1 Execução de Backup Manual
Gera um arquivo de dump do PostgreSQL, criptografa com a chave definida no `.env` e salva no diretório `backups/`:
```bash
python scripts/backup_db.py
```
O arquivo gerado terá a nomenclatura semelhante a: `backups/backup_YYYYMMDD_HHMMSS.pgdump.enc`.

### 4.2 Restauração de um Backup
Para restaurar um backup criptografado (por exemplo, após um crash ou na migração de servidor):
```bash
python scripts/restaurar_db.py backups/backup_YYYYMMDD_HHMMSS.pgdump.enc
```
> [!WARNING]
> O processo de restauração utiliza a flag `--clean` no `pg_restore`, o que significa que todas as tabelas e dados atuais do banco de dados ativo serão excluídos e substituídos pelo conteúdo do backup.

### 4.3 Teste Automático de Restauração
Para validar se o seu arquivo de backup está realmente íntegro e legível, execute o script de validação:
```bash
python scripts/testar_restauracao.py backups/backup_YYYYMMDD_HHMMSS.pgdump.enc
```
Este script descriptografa o dump, cria um banco de dados temporário isolado e testa a estrutura básica para garantir que o arquivo não está corrompido, tudo de forma segura sem afetar o banco de produção.

### 4.4 Automatizando o Backup Diário (Cron Job)
Para configurar um backup diário automático às 02:00 da manhã e enviar os arquivos para fora do servidor (ex: pasta sincronizada ou AWS S3):
1. Abra as tarefas cron do servidor:
   ```bash
   crontab -e
   ```
2. Adicione a seguinte linha na parte inferior (ajuste o caminho do python e da pasta conforme necessário):
   ```cron
   0 2 * * * cd /var/www/projeto_consultorio && python scripts/backup_db.py >> /var/log/backup_consultorio.log 2>&1
   ```
3. Recomenda-se configurar uma ferramenta de sincronização externa (como `rclone` ou `aws-cli`) para enviar os arquivos da pasta `/var/www/projeto_consultorio/backups` para um armazenamento na nuvem.

---

## 5. Auditoria de Segurança e LGPD

### 5.1 Conformidade com a LGPD
- **Exclusão de Pacientes**: Pacientes excluídos por solicitação explícita (direito ao esquecimento) são removidos do banco de dados, excluindo em cascata seu prontuário e histórico financeiro associados.
- **Retenção Automática**: O script em `app/services/retencao_lgpd.py` implementa uma rotina para apagar automaticamente dados de pacientes que estão inativos há mais de 2 anos (730 dias).
- **Dados Sensíveis nos Logs**: Os logs operacionais da aplicação não gravam nomes de pacientes, números de telefone ou emails. Apenas IDs (UUIDs) e ações genéricas são registradas na auditoria técnica.

### 5.2 Segurança de Login (Brute-Force Protection)
- Após **5 tentativas falhas consecutivas de login**, o endereço IP/usuário é bloqueado temporariamente por **15 minutos**.
- Todas as tentativas são registradas no arquivo de logs técnicos para auditoria em `logs/seguranca.log`.

---

## 6. Roteiro de Emergência (Troubleshooting)

### Sintoma A: O site do Streamlit está fora do ar (erro 502 Bad Gateway no navegador)
Isso geralmente indica que o Nginx está funcionando, mas o container `app` (Streamlit) está desligado ou travado.
**Solução**:
1. Verifique o status dos contêineres:
   ```bash
   docker compose ps
   ```
2. Visualize os logs do aplicativo para identificar erros de inicialização:
   ```bash
   docker compose logs app --tail=100
   ```
3. Reinicie o contêiner do aplicativo:
   ```bash
   docker compose restart app
   ```

### Sintoma B: Erro "Database Connection Refused" nos logs da aplicação
O aplicativo não consegue falar com o banco de dados PostgreSQL.
**Solução**:
1. Verifique se o container `db` está saudável:
   ```bash
   docker compose ps
   ```
2. Verifique os logs do banco de dados:
   ```bash
   docker compose logs db --tail=100
   ```
3. Se o banco falhar por espaço em disco, limpe dados inúteis do docker:
   ```bash
   docker system prune -a --volumes
   ```

### Sintoma C: Certificado SSL/HTTPS Expirado ou Inválido
O Nginx utiliza certificados Let's Encrypt para proteger os dados em trânsito.
**Solução**:
1. Verifique o status do certbot e renovação:
   ```bash
   docker compose run --entrypoint certbot nginx renew
   ```
2. Reinicie o Nginx para recarregar o certificado:
   ```bash
   docker compose restart nginx
   ```

# Documentacao do Projeto - Gestao Consultorio Psicologia

## Visao geral

Este projeto e uma aplicacao Streamlit para gestao de um consultorio de psicologia. O sistema centraliza cadastro de pacientes, agenda, calendario de ocupacao, controle de pagamentos, financeiro previsto vs realizado, despesas, feriados, indisponibilidades e usuarios.

A aplicacao usa PostgreSQL como banco de dados, SQLAlchemy como ORM e Docker para execucao local conteinerizada.

## Stack tecnica

- Python 3.12
- Streamlit
- SQLAlchemy
- PostgreSQL 16
- psycopg2-binary
- bcrypt
- ReportLab
- Plotly
- Docker e Docker Compose

## Como executar

### Com Docker

1. Configure o arquivo `.env` com base em `.env.example`.
2. Execute:

```bash
docker compose up --build
```

3. Acesse:

```text
http://localhost:8501
```

O banco roda apenas na rede interna do Docker Compose, pois o servico `db` nao expoe portas para a maquina host.

### Sem Docker

1. Instale as dependencias:

```bash
pip install -r requirements.txt
```

2. Suba um PostgreSQL local.
3. Configure a variavel `DATABASE_URL`.
4. Execute:

```bash
streamlit run app/main.py
```

Exemplo de `DATABASE_URL`:

```text
postgresql+psycopg2://psico:psico@localhost:5432/consultorio
```

## Estrutura de arquivos

```text
.
+-- app/
|   +-- main.py
|   +-- db/
|   |   +-- models.py
|   |   +-- session.py
|   +-- auth/
|   |   +-- init_users.py
|   |   +-- login.py
|   |   +-- senha_policy.py
|   +-- services/
|       +-- auditoria.py
|       +-- calendario.py
|       +-- contrato.py
|       +-- email_srv.py
|       +-- feriados.py
|       +-- financeiro.py
|       +-- indisponibilidade.py
|       +-- ocupacao.py
|       +-- pdf_export.py
+-- docker-compose.yml
+-- Dockerfile
+-- requirements.txt
+-- .env.example
+-- README.md
```

Observacao: os modelos ativos ficam em `app/db/models.py` e o motor financeiro ativo fica em `app/services/financeiro.py`.

## Fluxo principal da aplicacao

O arquivo `app/main.py` e o ponto de entrada da interface Streamlit.

Na inicializacao, a aplicacao:

1. Configura pagina e estilos basicos.
2. Cria tabelas no banco via `criar_tabelas()`.
3. Inicializa o primeiro administrador via ambiente, se configurado.
4. Garante historico inicial de contrato para pacientes existentes.
5. Remove automaticamente pacientes inativos ha mais de 2 anos.
6. Exibe a tela de login ou, apos autenticacao, o menu lateral conforme o perfil do usuario.

## Modulos da interface

### Login

Tela responsavel por:

- autenticar usuario e senha;
- registrar login bem-sucedido e falhas na auditoria;
- solicitar redefinicao de senha por email;
- aplicar codigo de redefinicao de senha.

A sessao expira apos 15 minutos de inatividade.

### Cadastro

Permite cadastrar:

- pacientes recorrentes;
- pacientes em avaliacao inicial, com sessao unica ou pontual.

No cadastro recorrente, o usuario informa frequencia, dias da semana, horarios, valor por sessao, tipo de contrato e data de inicio da recorrencia.

Frequencias suportadas:

- semanal;
- quinzenal;
- mensal;
- 2x por semana;
- 3x por semana;
- personalizado.

O sistema detecta conflitos de horario antes de salvar, considerando os proximos 3 meses.

### Agenda

Mostra a agenda de sessoes e permite gerenciar sessoes pontuais. A ocupacao e calculada combinando:

- pacientes recorrentes ativos;
- sessoes pontuais agendadas;
- cancelamentos usados como excecao;
- feriados;
- indisponibilidades;
- excecoes recorrentes ou pontuais de horario.

### Calendario

Agrupa recursos relacionados ao calendario do consultorio, incluindo:

- visualizacao de feriados;
- bloqueios de indisponibilidade;
- ferias;
- imprevistos;
- compromissos fixos semanais.

Os feriados sao calculados automaticamente, incluindo datas moveis como Carnaval, Pascoa e Corpus Christi.

### Pagamentos

Permite acompanhar sessoes e status de pagamento. Os status principais sao:

- Pendente;
- Pago;
- Atrasado;
- Isento.

Tambem ha exportacao de relatorios em PDF.

### Financeiro

Calcula previsto vs realizado e DRE simplificado.

O previsto considera:

- pacientes ativos;
- frequencia contratada;
- dias reais do mes;
- feriados;
- indisponibilidades de dia todo;
- sessoes pontuais agendadas;
- historico de contrato vigente em cada data.

O realizado considera sessoes com status:

- Realizada;
- Cancelou -24h (cobra).

O lucro liquido e calculado como:

```text
faturamento_realizado - total_despesas
```

O modulo tambem suporta despesas recorrentes, com geracao automatica por mes.

### Usuarios

Disponivel para perfis com permissao administrativa. Permite criar e excluir usuarios.

Ao criar usuario, a senha deve obedecer a politica:

- pelo menos 6 letras;
- pelo menos 1 numero;
- pelo menos 1 caractere especial.

### Minha conta

Disponivel para todos os perfis. Permite ao usuario logado alterar a propria
senha informando senha atual, nova senha e confirmacao. A nova senha segue a
mesma politica minima de seguranca e a sessao e encerrada apos a alteracao.

## Perfis e permissoes

Os perfis definidos em `app/db/models.py` sao:

- `Dona`: acesso a Cadastro, Agenda, Calendario, Pagamentos, Financeiro e Usuarios.
- `Secretaria`: acesso a Cadastro, Agenda, Calendario e Pagamentos.
- `Financeiro`: acesso a Pagamentos e Financeiro.
- `Programador`: acesso a todos os modulos.

## Primeiro acesso

Nao ha senhas padrao fixas no codigo.

Quando o banco ainda nao tem usuarios, a tela de login mostra o formulario
"Primeiro acesso (criar usuario)". Esse formulario cria o primeiro usuario
com perfil `Dona`, que depois pode criar os demais usuarios pela tela
`Usuarios`.

O login e normalizado para minusculas e aceita apenas letras, numeros, ponto,
hifen e underline, com 3 a 50 caracteres. Nome e obrigatorio e email, quando
informado, precisa ter formato valido.

Opcionalmente, o arquivo `app/auth/init_users.py` tambem pode criar o primeiro
administrador automaticamente se `BOOTSTRAP_ADMIN_PASSWORD` estiver configurada
no ambiente. Se ja existir qualquer usuario, esse bootstrap nao altera nada.

## Modelo de dados

Os modelos principais ficam em `app/db/models.py`.

### Paciente

Representa o cadastro de um paciente.

Campos relevantes:

- nome, telefone, email e data de nascimento;
- tipo de contrato;
- valor por sessao;
- frequencia;
- dias da semana;
- horario de atendimento;
- status ativo/inativo;
- data de ativacao;
- flags de avaliacao inicial;
- data de desativacao para controle LGPD.

### AgendaSessao

Representa uma sessao agendada ou registrada.

Campos relevantes:

- paciente;
- data/hora de inicio e fim;
- status de presenca;
- status de pagamento;
- indicacao de confirmacao enviada;
- dados de remarcacao.

Existe uma restricao unica em `data_hora_inicio`, impedindo dois registros com o mesmo horario inicial.

### ContratoHistorico

Mantem snapshots de contrato por periodo de vigencia. E usado para preservar calculos financeiros corretos quando um paciente muda frequencia, valor, dias ou regra de atendimento no meio do tempo.

### ExcecaoHorario

Representa excecoes de horario:

- recorrentes, por semana do mes;
- pontuais, por data especifica.

### Despesa

Representa despesas do consultorio, incluindo despesas recorrentes.

### Usuario

Representa usuarios do sistema. Senhas sao armazenadas com hash bcrypt.

### Auditoria

Registra eventos criticos sem dados sensiveis.

### Indisponibilidade

Registra datas ou horarios em que a profissional nao atende.

## Regras de negocio importantes

### Feriados

O arquivo `app/services/feriados.py` calcula feriados nacionais, estaduais de SP e municipais de Sao Paulo. As datas moveis sao calculadas a partir da Pascoa.

### Indisponibilidades

O arquivo `app/services/indisponibilidade.py` permite agrupar bloqueios por:

- intervalo continuo;
- recorrencia semanal;
- recorrencia semanal com multiplos dias.

Esses bloqueios impactam agenda e financeiro.

### Ocupacao e conflitos

O arquivo `app/services/ocupacao.py` calcula datas reais de atendimento por paciente e monta o mapa mensal de ocupacao.

Ele tambem detecta conflitos usando sobreposicao de faixas de horario, nao apenas igualdade exata.

### Historico de contrato

O arquivo `app/services/contrato.py` fecha o periodo vigente e abre um novo quando campos financeiros do contrato mudam.

Campos monitorados:

- frequencia;
- valor da sessao;
- dias da semana;
- semana do mes;
- paridade quinzenal;
- sessoes customizadas por mes.

### Financeiro

O arquivo `app/services/financeiro.py` calcula:

- faturamento previsto por paciente;
- faturamento realizado por paciente;
- consolidado mensal;
- consolidado por periodo;
- expansao de despesas recorrentes.

Mudancas de contrato sao tratadas por data, usando o snapshot vigente no dia da sessao ou da previsao.

## Banco de dados e migracoes

O projeto possui configuracao Alembic em `alembic.ini` e migrações em
`migrations/`.

Comandos principais:

```bash
alembic upgrade head
alembic revision --autogenerate -m "descreva a mudanca"
```

O Alembic usa `DATABASE_URL` quando a variavel estiver definida. Caso contrario,
usa a URL fallback configurada em `alembic.ini`.

A primeira migracao versionada e `20260609_0001_schema_inicial`, que representa
o schema atual dos modelos SQLAlchemy.

Para bancos ja criados pela versao antiga do app, faca backup e confira se o
schema esta equivalente antes de marcar a versao atual:

```bash
alembic stamp head
```

O arquivo `app/db/session.py` ainda:

- cria o engine SQLAlchemy;
- cria tabelas;
- adiciona colunas faltantes em tabelas existentes;
- amplia tamanho de colunas `VARCHAR` quando necessario;
- remove constraint antiga de duracao fixa de 1 hora em `agenda_sessoes`.

Essa compatibilidade foi mantida para nao quebrar bancos existentes, mas novas
mudancas de schema devem ser registradas por migrações Alembic.

## Codificacao e finais de linha

O projeto usa UTF-8 como padrao de codificacao. Os arquivos `.editorconfig` e
`.gitattributes` ajudam a manter charset, finais de linha e tratamento de
arquivos binarios consistentes entre Windows, Linux e Docker.

## Testes automatizados

Os testes ficam em `tests/` e podem ser executados com:

```bash
python -m unittest discover -s tests
```

A suite inicial cobre regras puras de calendario, ocupacao de horarios e
previsao financeira sem depender de PostgreSQL.

## Backup e restauracao

Os scripts operacionais em Python ficam em `scripts/` e fornecem criptografia simétrica forte via AES-256 (Fernet):

* **Geração de backup criptografado**:
  ```bash
  python scripts/backup_db.py
  ```
* **Restauração de backup criptografado**:
  ```bash
  python scripts/restaurar_db.py backups/NOME_DO_ARQUIVO.pgdump.enc
  ```
* **Teste de restaurabilidade (integridade)**:
  ```bash
  python scripts/testar_restauracao.py
  ```

Os arquivos criptografados gerados possuem extensão `.pgdump.enc` e a pasta `backups/` é ignorada no Git.

## Variaveis de ambiente

Baseadas em `.env.example`, `.env.dev` e `.env.prod`:

| Variavel | Uso |
| --- | --- |
| `POSTGRES_USER` | Usuario do PostgreSQL no Docker |
| `POSTGRES_PASSWORD` | Senha do PostgreSQL |
| `POSTGRES_DB` | Nome do banco |
| `DATABASE_URL` | String de conexao usada pelo SQLAlchemy |
| `BACKUP_ENCRYPTION_KEY` | Chave de criptografia AES Fernet (32 bytes em base64) para backups |
| `BACKUP_DIR` | Diretorio destino dos arquivos de backup |
| `BACKUP_RETENTION_COUNT` | Quantidade de arquivos mantidos na rotacao de backup |
| `AMBIENTE` | Ambiente de execucao (`desenvolvimento` ou `producao`) |
| `BOOTSTRAP_ADMIN_USERNAME` | Login do primeiro administrador automatico, padrao `dona` |
| `BOOTSTRAP_ADMIN_NAME` | Nome do primeiro administrador automatico |
| `BOOTSTRAP_ADMIN_EMAIL` | Email do primeiro administrador automatico |
| `BOOTSTRAP_ADMIN_PASSWORD` | Senha forte para criar o primeiro administrador automatico |
| `SMTP_HOST` | Servidor SMTP para reset de senha |
| `SMTP_PORT` | Porta SMTP, padrao 465 |
| `SMTP_USER` | Usuario SMTP |
| `SMTP_PASS` | Senha SMTP |
| `SMTP_FROM` | Remetente dos emails |
| `RETENCAO_PACIENTES_DIAS` | Dias de inatividade de pacientes antes da exclusao automatica LGPD |
| `RETENCAO_AUDITORIA_DIAS` | Dias de armazenamento de logs de auditoria antes da limpeza automatica LGPD |

Se o SMTP nao estiver configurado, o codigo de redefinicao de senha aparece nos logs tecnicos mascarados da aplicacao.

## Seguranca e LGPD

Pontos implementados:

- senhas com hash bcrypt;
- ausencia de senhas padrao fixas no codigo;
- criacao do primeiro usuario pela tela ou por variavel de ambiente;
- politica minima de senha;
- timeout de sessao apos 15 minutos;
- perfis com permissoes por modulo;
- bloqueio temporario de conta por 15 minutos apos 5 tentativas malsucedidas de login seguidas;
- redefinicao obrigatoria de senha inicial no primeiro acesso do usuario;
- mascara automatica de chaves, tokens e senhas no logger tecnico de diagnostico;
- auditoria de eventos criticos sem gravar dados sensiveis (ex: marcando UUID em vez de nome do paciente);
- remocao automatica de pacientes inativos e logs de auditoria antigos respeitando a politica de retencao LGPD parametrizavel;
- exclusao manual segura de pacientes exigindo confirmacao digitando 'EXCLUIR' em caixa de dialogo modal;
- exportacao/portabilidade de dados do paciente em formato JSON estruturado por meio do botao `📥` nas listagens;
- banco Docker nao exposto diretamente por porta em producao (porta fechada por padrao);
- documentacao da politica operacional em [POLITICA_PRIVACIDADE.md](file:///c:/Users/eduar/Downloads/projeto_consultorio/POLITICA_PRIVACIDADE.md).

Pontos recomendados para producao:

- configurar SMTP real;
- usar senha forte no PostgreSQL;
- usar senha forte em `BOOTSTRAP_ADMIN_PASSWORD`, caso o bootstrap automatico seja usado;
- Nginx implantado como reverse proxy e porta do Streamlit (8501) isolada do acesso publico direto;
- revisar `.env` para garantir que nao seja versionado;
- executar e armazenar backups regulares fora da maquina local;
- aplicar Alembic no processo de deploy antes de subir a aplicacao;

## Infraestrutura de Producao, Nginx e HTTPS

A aplicacao possui uma infraestrutura conteinerizada preparada para producao:

1. **Proxy Reverso (Nginx)**: O container `nginx` escuta nas portas publicas `80` e `443` e encapsula as conexoes direcionando-as internamente ao container `app` (porta `8501`).
2. **Seguranca HTTPS**: Suporta TLSv1.2 e TLSv1.3 e cifras fortes, com desativacao de protocolos antigos e cabeçalhos HTTP de protecao (`X-Frame-Options`, `X-Content-Type-Options`, `X-XSS-Protection`, e CSP rigorosa com WebSockets).
3. **Ambiente Local (Certificados Autoassinados)**: Disponibilizados os scripts `nginx/gerar_ssl_local.ps1` (PowerShell) e `nginx/gerar_ssl_local.sh` (Bash) que utilizam o docker com `alpine/openssl` para gerar credenciais locais autoassinadas para testes em desenvolvimento.
4. **Deploy Controlado em Producao**:
   - Para obter certificados reais do Let's Encrypt usando o Certbot, suba temporariamente uma regra HTTP simples no Nginx para o desafio ACME ou execute o certbot com a pasta `nginx/html` mapeada.
   - O fluxo padrao recomendado para atualizacoes em producao eh:
     1. Backup do banco (`scripts/backup_db.ps1`).
     2. Puxar as mudancas do git (`git pull`).
     3. Rodar as migrações do banco com `alembic upgrade head`.
     4. Recriar e reiniciar contêineres (`docker compose up --build -d`).

## Exportacao de PDF

O modulo [pdf_export.py](file:///c:/Users/eduar/Downloads/projeto_consultorio/app/services/pdf_export.py) gera relatorios PDF no formato paisagem (A4) usando ReportLab. 

Pontos implementados:
- **NumberedCanvas**: Paginação dinamica de duas passagens no formato `"Página X de Y"` e nota de confidencialidade LGPD.
- **Cabeçalho de Filtros**: Renderiza um painel com os filtros aplicados no topo se informados no parametro `filtros`.
- **Linha de Totais**: Adiciona uma linha destacada ao final da tabela com totais em negrito e fundo cinza se informada no parametro `totais`.

## Suite de Testes

A suite de testes foi expandida para cobrir:
- Validação de regras e seguranca de perfil na tela de auditoria.
- Lógica de faturamento e inadimplência usando banco de dados SQLite em memoria (`tests/test_financeiro_db.py`).
- Geração fisica e integridade binaria de PDFs (`tests/test_pdf_export.py`).
- Validação completa do serviço de comprovantes: tipo, tamanho, sanitização, ciclo disco e helpers ORM (`tests/test_comprovantes.py`).
- Notificações e busca global com limites de resultados (`tests/test_notificacoes.py`, `tests/test_busca_global.py`).

Execute os testes com:
```bash
python -m unittest discover -s tests
```

---

## Comprovantes — Arquitetura de Storage

### Visão Geral

O sistema permite anexar comprovantes de pagamento (PDF, PNG, JPG/JPEG, máximo 10 MB) tanto em sessões quanto em despesas. A arquitetura foi projetada para isolar completamente a camada de storage, de modo que a troca futura para S3/Supabase não exija alterar nenhuma tela.

### Camada isolada: `app/services/comprovantes.py`

Toda manipulação de arquivo passa por este módulo. As telas (`financeiro.py`, `pagamentos.py`, `cadastro.py`) **nunca** lidam com caminhos absolutos ou storage diretamente.

**Contratos estáveis — não mudam ao trocar o storage:**

| Função | Descrição |
|---|---|
| `salvar_comprovante(file, tipo, id)` | Valida, salva e retorna `dict` com 5 campos de metadados |
| `obter_comprovante_caminho(nome)` | Retorna caminho interno para leitura — nunca exposto na UI |
| `deletar_comprovante(nome)` | Remove arquivo do storage |
| `aplicar_metadados_comprovante(registro, meta)` | Aplica os 5 campos no ORM |
| `limpar_metadados_comprovante(registro)` | Zera todos os campos de metadados no ORM |

**Dicionário de metadados retornado por `salvar_comprovante`:**
```python
{
    "nome":          "sessao_42_1718290000_recibo.pdf",  # nome interno único
    "nome_original": "Recibo Janeiro 2026.pdf",          # nome original do usuário
    "mime":          "application/pdf",                   # MIME correto para download
    "tamanho":       45312,                              # bytes
    "enviado_em":    datetime(2026, 1, 13, 10, 30),      # data/hora do upload
}
```

### Metadados no Banco de Dados

Os 5 campos são persistidos em `agenda_sessoes` e `despesas`:

| Coluna | Tipo | Descrição |
|---|---|---|
| `comprovante_nome` | `VARCHAR(200)` | Nome interno gerado — nunca um caminho absoluto |
| `comprovante_nome_original` | `VARCHAR(300)` | Nome original enviado pelo usuário |
| `comprovante_mime` | `VARCHAR(100)` | Tipo MIME para download correto |
| `comprovante_tamanho` | `INTEGER` | Tamanho em bytes |
| `comprovante_enviado_em` | `DATETIME` | Data/hora do upload |

Os metadados ficam **permanentemente no banco PostgreSQL**, mesmo que o arquivo físico desapareça.

### Validação de Upload

Toda submissão passa por `validar_upload()` antes de qualquer escrita em disco:

- **Extensões aceitas:** `.pdf`, `.png`, `.jpg`, `.jpeg`
- **Tamanho máximo:** 10 MB (configurável via `TAMANHO_MAXIMO_BYTES`)
- **Arquivo vazio:** rejeitado
- **Nome sanitizado:** ASCII seguro, colapsado, com timestamp para unicidade

### Auditoria e LGPD

Toda operação com comprovante gera registro em `auditoria`:

- `COMPROVANTE_ANEXADO` — `despesa_id`/`sessao_id`, nome do arquivo, MIME e bytes
- `COMPROVANTE_REMOVIDO` — arquivo anterior, motivo (ex: `motivo=status_nao_pago`)

Regras LGPD observadas:
- `uploads/` está no `.gitignore` — arquivos de pacientes nunca são versionados
- Caminhos absolutos nunca aparecem na interface do usuário
- Download sempre controlado por usuário autenticado e ativo
- Comprovante removido automaticamente quando sessão deixa de ser "Paga"

### Limitação atual — Streamlit Cloud

> ⚠️ **O filesystem do Streamlit Cloud é efêmero.** A plataforma pode reiniciar o contêiner a qualquer momento, apagando o conteúdo de `uploads/`. Os metadados permanecem no banco PostgreSQL, mas o arquivo físico pode desaparecer entre reinicializações.

A interface trata este caso com fallback gracioso: exibe `⚠️ Arquivo ausente` sem quebrar o sistema ou gerar erro para o usuário.

---

### TODO TÉCNICO — Migração para Storage Externo

> Quando o sistema for para produção definitiva ou quando a limitação do filesystem do Streamlit Cloud se tornar um problema, substituir **somente** a função `salvar_comprovante` em `app/services/comprovantes.py`. Nenhuma tela precisa ser alterada.

**Opções recomendadas:**

#### 1. Supabase Storage *(recomendado — já fornece PostgreSQL)*
```bash
pip install supabase
```
```python
# Implementação de salvar_comprovante com Supabase:
from supabase import create_client
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
supabase.storage.from_("comprovantes").upload(nome_arquivo, dados)
url = supabase.storage.from_("comprovantes").create_signed_url(nome_arquivo, 900)
```

#### 2. Amazon S3 / Cloudflare R2
```bash
pip install boto3
```
```python
# Implementação com S3 — URL assinada com expiração de 15 min:
s3 = boto3.client("s3", ...)
s3.put_object(Bucket=BUCKET, Key=nome_arquivo, Body=dados)
url = s3.generate_presigned_url("get_object", Params={...}, ExpiresIn=900)
```

#### 3. Google Drive API
```bash
pip install google-api-python-client google-auth
```
```python
# Implementação com Drive — pasta privada da profissional:
service.files().create(body={"name": nome_arquivo, "parents": [FOLDER_ID]},
                       media_body=dados).execute()
```

**Regras invariantes — válidas para qualquer storage escolhido:**

- ✔ Metadados (`nome`, `mime`, `tamanho`, `enviado_em`) permanecem no banco PostgreSQL
- ✔ Caminho ou URL absoluta nunca é exposta diretamente na interface
- ✔ Download sempre controlado por usuário autenticado
- ✔ Fallback gracioso quando arquivo não existe (`⚠️ Arquivo ausente`)
- ✔ Auditoria registrada ao anexar e ao remover (`COMPROVANTE_ANEXADO` / `COMPROVANTE_REMOVIDO`)
- ✔ Arquivos dos pacientes são dados pessoais/financeiros — conformidade LGPD obrigatória
- ✔ `uploads/` permanece no `.gitignore` — nunca versionar arquivos de pacientes

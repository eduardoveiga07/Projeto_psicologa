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

Observacao: existem tambem `app/models.py` e `app/financeiro.py`, que parecem versoes antigas/legadas. A aplicacao atual importa os modelos de `app/db/models.py` e o motor financeiro de `app/services/financeiro.py`.

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

## Banco de dados e migracao simples

O arquivo `app/db/session.py`:

- cria o engine SQLAlchemy;
- cria tabelas;
- adiciona colunas faltantes em tabelas existentes;
- amplia tamanho de colunas `VARCHAR` quando necessario;
- remove constraint antiga de duracao fixa de 1 hora em `agenda_sessoes`.

Essa migracao e simples e nao substitui uma ferramenta formal como Alembic, mas ajuda a evoluir o prototipo sem recriar o banco.

## Variaveis de ambiente

Baseadas em `.env.example`:

| Variavel | Uso |
| --- | --- |
| `POSTGRES_USER` | Usuario do PostgreSQL no Docker |
| `POSTGRES_PASSWORD` | Senha do PostgreSQL |
| `POSTGRES_DB` | Nome do banco |
| `DATABASE_URL` | String de conexao usada pelo SQLAlchemy |
| `BOOTSTRAP_ADMIN_USERNAME` | Login do primeiro administrador automatico, padrao `dona` |
| `BOOTSTRAP_ADMIN_NAME` | Nome do primeiro administrador automatico |
| `BOOTSTRAP_ADMIN_EMAIL` | Email do primeiro administrador automatico |
| `BOOTSTRAP_ADMIN_PASSWORD` | Senha forte para criar o primeiro administrador automatico |
| `SMTP_HOST` | Servidor SMTP para reset de senha |
| `SMTP_PORT` | Porta SMTP, padrao 465 |
| `SMTP_USER` | Usuario SMTP |
| `SMTP_PASS` | Senha SMTP |
| `SMTP_FROM` | Remetente dos emails |

Se o SMTP nao estiver configurado, o codigo de redefinicao de senha aparece na tela em modo de desenvolvimento.

## Seguranca e LGPD

Pontos implementados:

- senhas com hash bcrypt;
- ausencia de senhas padrao fixas no codigo;
- criacao do primeiro usuario pela tela ou por variavel de ambiente;
- politica minima de senha;
- timeout de sessao apos 15 minutos;
- perfis com permissoes por modulo;
- auditoria de eventos criticos;
- recomendacao explicita para nao registrar dados sensiveis em auditoria;
- remocao automatica de pacientes inativos ha mais de 2 anos;
- banco Docker nao exposto diretamente por porta.

Pontos recomendados para producao:

- configurar SMTP real;
- usar senha forte no PostgreSQL;
- usar senha forte em `BOOTSTRAP_ADMIN_PASSWORD`, caso o bootstrap automatico seja usado;
- proteger o acesso ao Streamlit com HTTPS/reverse proxy;
- revisar `.env` para garantir que nao seja versionado;
- adicionar backups regulares do volume PostgreSQL;
- substituir migracao manual por Alembic se o sistema crescer.

## Exportacao de PDF

O arquivo `app/services/pdf_export.py` gera PDFs simples com ReportLab a partir de listas de dicionarios.

E usado para relatorios como feriados, pagamentos e dados financeiros exibidos na interface.

## Pontos de atencao encontrados

1. Existem arquivos aparentemente legados: `app/models.py` e `app/financeiro.py`.
2. O README atual e resumido; este documento detalha melhor a arquitetura e regras.
3. Alguns textos no codigo aparecem com caracteres quebrados, indicando possivel problema de encoding em arquivos salvos anteriormente.
4. Nao ha suite de testes automatizados no projeto.
5. Nao ha ferramenta formal de migracao de banco, como Alembic.

## Sugestoes de proximos passos

1. Remover ou arquivar arquivos legados apos confirmar que nao sao usados.
2. Corrigir encoding dos arquivos para UTF-8.
3. Criar testes unitarios para calendario, ocupacao, contrato e financeiro.
4. Adicionar um guia operacional para backup/restauracao do PostgreSQL.
5. Criar uma documentacao de uso para a profissional e outra tecnica para manutencao.

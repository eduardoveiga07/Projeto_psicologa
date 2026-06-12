# Manual de Uso do Sistema - Gestão de Consultório de Psicologia

Bem-vindo(a) ao manual de instruções da sua ferramenta de gestão de consultório. Este documento foi elaborado para ajudar você, sua secretária ou seu braço financeiro a operarem o sistema de forma correta no dia a dia.

---

## Sumário
1. [Primeiro Acesso e Login](#1-primeiro-acesso-e-login)
2. [Gestão de Pacientes (Cadastro)](#2-gestao-de-pacientes-cadastro)
3. [Agenda de Sessões](#3-agenda-de-sessoes)
4. [Calendário e Indisponibilidades (Férias/Bloqueios)](#4-calendario-e-indisponibilidades-feriasbloqueios)
5. [Controle de Pagamentos](#5-controle-de-pagamentos)
6. [Painel Financeiro (Previsto vs Realizado)](#6-painel-financeiro-previsto-vs-realizado)
7. [Gestão de Usuários (Apenas Administrador)](#7-gestao-de-usuarios-apenas-administrador)
8. [Exportação de Relatórios PDF e LGPD](#8-exportacao-de-relatorios-pdf-e-lgpd)
9. [Rotina de Backup e Restauração (Técnico/Segurança)](#9-rotina-de-backup-e-restauracao-tecnicoseguranca)
10. [Configuração de Produção e HTTPS (Infraestrutura/Segurança)](#10-configuracao-de-producao-e-https-infraestruturaseguranca)

---

## 1. Primeiro Acesso e Login

### A. Primeiro Acesso
Quando o banco de dados estiver completamente vazio, a tela inicial exibirá o formulário **"Primeiro acesso (criar usuário)"**.
1. Preencha o seu login (username), nome completo, email e uma senha forte.
2. A senha deve ter no mínimo:
   - **6 caracteres**;
   - **1 número**;
   - **1 caractere especial** (ex: `@`, `#`, `!`, `*`).
3. O primeiro usuário criado terá automaticamente o perfil de administrador (**"Dona"**).

### B. Login Diário
- Insira seu login e senha na tela inicial.
- **Segurança importante**: A sessão expira automaticamente após **15 minutos de inatividade** para evitar acessos indesejados caso o computador seja deixado desbloqueado na recepção ou consultório.

---

## 2. Gestão de Pacientes (Cadastro)

A tela de **Cadastro** possui três seções principais ocultas sob caixas retráteis (expanders). Clique sobre o título para expandi-las:

### A. Cadastrar Novo Paciente (Formulário)
1. **Nome completo**, **telefone** (com código do país e DDD, ex: `5511999998888`), **email** (opcional, útil para portabilidade e faturamento) e **data de nascimento**.
2. **Tipo de Cadastro**:
   - **Recorrente**: Paciente fixo que faz tratamento contínuo. Exige configuração de frequência, dias da semana, horários e valor da sessão.
   - **Avaliação Inicial**: Paciente novo passando por sessões pontuais de avaliação diagnóstica inicial. Exige definir se a avaliação é cobrada ou gratuita e seu valor.
3. Clique em **"Cadastrar Paciente"**.

### B. Pacientes em Avaliação Inicial
- Exibe pacientes novos que ainda não iniciaram um tratamento contínuo.
- **Ações disponíveis**:
  - `Editar`: Altera nome, telefone, email, se a avaliação é paga e o valor dela.
  - `Recorrente`: Caso o paciente decida iniciar o tratamento fixo, clique em "Recorrente" para convertê-lo e preencher a frequência contratada.
  - `Excluir`: Exclui permanentemente o cadastro e as sessões associadas a esta avaliação (exige confirmação de segurança digitando "EXCLUIR").
  - `📥` (Exportar): Baixa um arquivo JSON com todas as informações deste paciente (direito de acesso/portabilidade LGPD).

### C. Pacientes Ativos Recorrentes
- Lista todos os pacientes em atendimento fixo contínuo com os detalhes do contrato deles (frequência, valor por sessão, etc.).
- **Ações disponíveis**:
  - `✉️` (Copiar email): Copia rapidamente o email do paciente para a área de transferência.
  - `Editar`: Permite renegociar o valor da sessão, alterar dias da semana, horários ou frequência.
    - *Nota*: Ao alterar o contrato do paciente, o sistema fecha a vigência do contrato antigo e abre uma nova, mantendo o histórico financeiro passado intacto.
  - `Desativar`: Define o paciente como inativo (suspensão do tratamento). Ele vai para a lista de inativos.
  - `📥` (Exportar): Baixa um arquivo JSON contendo todos os dados do paciente.

### D. Pacientes Inativos (Sem Retorno)
- Lista pacientes que interromperam o tratamento.
- **Ações disponíveis**:
  - `Reativar`: Retorna o paciente para a lista de ativos recorrentes.
  - `Excluir`: Exclui permanentemente o paciente do sistema (exige confirmação de segurança digitando "EXCLUIR").
- **Exclusão Automática (LGPD)**: Pacientes inativos há **mais de 2 anos (730 dias)** são removidos de forma definitiva e automática pelo sistema para cumprir o tempo limite de retenção de dados pessoais.

---

## 3. Agenda de Sessões

A tela **Agenda** calcula automaticamente os horários de atendimento da semana e do mês com base na frequência contratada de cada paciente.

### A. Calendário Mensal e Ocupação
- Informe o **Mês** e o **Ano** para visualizar a listagem das sessões programadas.
- O sistema mostra as sessões dia a dia com os nomes dos pacientes e os respectivos horários.

### B. Remarcar Sessões em Conflito
- Caso uma data de sessão coincida com um feriado nacional ou um período de indisponibilidade cadastrado por você (ex: folga ou férias):
  1. A sessão será exibida no painel **"⚠️ Sessões a remarcar/avisar pacientes"**.
  2. Clique em **"Remarcar"**.
  3. Preencha a **Nova data** e o **Novo horário** sugeridos e clique em **"Confirmar"**.
  4. O sistema registrará na auditoria a alteração de data sem expor informações pessoais, e a sessão será remarcada na agenda daquele paciente.

### C. Cadastrar Sessão Pontual / Avulsa
No formulário de agendamento na tela de agenda:
1. Selecione o paciente.
2. Defina o dia e o horário da sessão avulsa.
3. Clique em **"Agendar"**.
- *Nota*: O sistema impedirá o agendamento caso o horário já esteja reservado para outro paciente ativo ou coincida com uma indisponibilidade.

---

## 4. Calendário e Indisponibilidades (Férias/Bloqueios)

Neste módulo você gerencia feriados e bloqueios na sua agenda profissional.

### A. Feriados
- O sistema já calcula e exibe automaticamente todos os feriados nacionais móveis (Carnaval, Sexta-feira Santa, Páscoa, Corpus Christi) e fixos.
- Sessões recorrentes que caírem em feriados são marcadas como perdidas automaticamente na agenda para que você possa remarcá-las.

### B. Cadastrar Novo Bloqueio de Agenda (Indisponibilidade)
1. **Período**: Escolha a data de início e fim.
2. **Abrangência**:
   - **Dia todo**: A agenda ficará bloqueada de manhã até a noite.
   - **Horário específico**: Bloqueia apenas uma faixa horária (ex: das 14:00 às 16:00) para ir a uma consulta médica ou compromisso.
3. **Motivo**: Selecione entre "Férias", "Prolongou feriado", "Imprevisto/Emergência" ou "Outro".
4. **Observação**: Insira anotações adicionais.
5. Clique em **"Registrar Bloqueio"**.

### C. Remover ou Editar Bloqueios
- Na seção "Bloqueios cadastrados", visualize a lista de bloqueios ativos.
- Use `Editar` para alterar datas ou motivos, ou `Remover` para liberar a agenda e permitir novos agendamentos nessas datas.

---

## 5. Controle de Pagamentos

A tela **Pagamentos** gerencia o fluxo de caixa individualizado das sessões realizadas.

### A. Listagem e Alteração de Status
O sistema lista as sessões recentes ordenadas por data. Cada sessão possui:
- O nome do paciente, a data/horário e as seguintes ações:
  - **Presença**: Altere o status conforme o comparecimento:
    - *Agendada* (padrão inicial);
    - *Confirmada*;
    - *Realizada* (confirma a execução);
    - *Falta* (paciente faltou sem avisar);
    - *Cancelou +24h (isento)*;
    - *Cancelou -24h (cobra)* (a cobrança da sessão é mantida no financeiro);
    - *Imprevisto/Emergência (isento)*.
  - **Pagamento**:
    - *Pendente* (sessão realizada, mas não paga);
    - *Pago* (paciente quitou o valor);
    - *Atrasado*;
    - *Isento*.

### B. Cobranças Pendentes
- Utilize o painel de **Cobranças Pendentes** para visualizar todos os pacientes que possuem sessões com pagamento pendente ou em atraso.
- Permite ter uma visão rápida de quem está inadimplente para realizar a cobrança periódica de forma assertiva.

---

## 6. Painel Financeiro (Previsto vs Realizado)

A tela **Financeiro** calcula automaticamente o desempenho financeiro do consultório com base na agenda e nas despesas.

### A. Faturamento Previsto
O sistema projeta o quanto você deve faturar no mês de referência selecionado. O cálculo considera:
- A frequência do paciente e o valor do contrato vigente;
- O número de dias úteis reais que aquele dia da semana ocorre no mês;
- A exclusão automática de feriados e indisponibilidades que bloqueiam o atendimento;
- A soma de sessões pontuais/avulsas agendadas.

### B. Faturamento Realizado
O total efetivamente gerado a partir de sessões cujo status de presença é **"Realizada"** ou **"Cancelou -24h (cobra)"**.

### C. Lançar e Gerenciar Despesas
Você pode lançar contas de consumo (água, luz, aluguel), impostos, taxas, etc.
1. Preencha a **Descrição**, o **Valor** e a **Data de Vencimento**.
2. **Despesa Recorrente**: Se ativada, a despesa será replicada automaticamente para os meses seguintes no dia de vencimento configurado.
3. Preencha se a despesa está **Paga** ou **Pendente** e a data do pagamento.
4. Clique em **"Salvar Despesa"**.

### D. Lucro Líquido e DRE Simplificado
- Exibe o consolidado mensal: `Faturamento Realizado - Total de Despesas Pagas`.
- Mostra gráficos interativos e demonstrativos financeiros que auxiliam na tomada de decisões e planejamento de gastos do consultório.

---

## 7. Gestão de Usuários (Apenas Administrador)

Disponível apenas para usuários com perfis administrativos ("Dona" ou "Programador") para gerenciar quem acessa a ferramenta:

### A. Criar Novo Usuário
1. Preencha o login (username), nome completo, email, selecione o perfil e defina a senha inicial (obedecendo a política de força).
2. **Perfis Disponíveis**:
   - **Dona**: Acesso completo (Configurações, Cadastro, Agenda, Pagamentos, Financeiro e Usuários).
   - **Secretária**: Acesso para controle de cadastros, agendamentos de sessões e status de pagamentos. Não visualiza o módulo Financeiro.
   - **Financeiro**: Acesso voltado para registrar pagamentos, despesas e visualizar o módulo Financeiro (faturamento previsto vs realizado). Não edita cadastros de pacientes ou agendas.
   - **Programador**: Acesso irrestrito a todos os módulos e visualização de trilha de auditoria.

### B. Excluir Usuário
- Exclui o acesso de um funcionário ou parceiro de negócios do sistema.
- *Nota*: Você não pode excluir a si mesmo para evitar que o consultório fique sem um usuário administrador.

### C. Alterar Minha Senha (Todos os Perfis)
Na aba **"Minha conta"** (no menu lateral), qualquer usuário logado pode alterar a sua própria senha:
1. Digite a senha atual para validação.
2. Insira a nova senha e confirme.
3. Clique em **"Salvar nova senha"**.
4. O sistema encerrará a sessão atual por segurança, exigindo que você realize o login com a nova senha criada.

---

## 8. Exportação de Relatórios PDF e LGPD

### A. Relatórios em PDF
Em diversos módulos do sistema (Cadastro de Pacientes, Calendário de Feriados, Tabela de Pagamentos e Demonstrativo Financeiro), existe o botão **"Baixar PDF"** ou **"Exportar PDF"**:
- O sistema gera um documento formatado com cabeçalho, rodapé e as listagens filtradas na tela para que você possa imprimir, enviar por email ou guardar para contabilidade.

### B. Exportação LGPD (Portabilidade)
Se um paciente solicitar cópia de todos os seus dados guardados:
1. Acesse a tela de **Cadastro**.
2. Localize o paciente nas listas de ativos, inativos ou em avaliação.
3. Clique no botão de download (`📥`).
4. Na janela que se abrir, clique em **"Baixar Arquivo JSON"**.
5. Um arquivo de texto estruturado contendo a portabilidade completa de dados será baixado para o seu computador.

---

## 9. Rotina de Backup e Restauração (Técnico/Segurança)

Os dados clínicos e financeiros do consultório são preciosos. Realize backups regulares para evitar perdas em caso de problemas de hardware no computador local.

> [!IMPORTANT]
> Os comandos a seguir devem ser executados por meio do terminal do sistema operacional (PowerShell) na pasta raiz do projeto.

### A. Gerar Backup (Cópia de Segurança)
Para gerar uma cópia de segurança completa do banco de dados atual:
1. Abra o terminal (PowerShell) no computador onde o sistema está instalado.
2. Execute o comando:
   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts/backup_db.ps1
   ```
3. O script se conectará ao banco de dados no contêiner Docker, extrairá todas as tabelas e salvará um arquivo com formato `.dump` (contendo a data e hora da geração) dentro da pasta `backups/`.
4. **Recomendação de segurança**: Copie o arquivo `.dump` gerado para um local externo seguro (como um HD externo ou pasta em nuvem segura protegida por criptografia de ponta a ponta).

### B. Restaurar Backup (Recuperação de Dados)
Se você precisar reinstalar o sistema ou recuperar os dados de uma data anterior:
1. Identifique o nome do arquivo que deseja restaurar dentro da pasta `backups/` (exemplo: `backup_20260612_150000.dump`).
2. Abra o terminal (PowerShell) na pasta raiz do projeto.
3. Execute o comando passando o nome exato do arquivo desejado:
   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts/restore_db.ps1 -BackupFile backups/NOME_DO_ARQUIVO.dump
   ```
4. O script exibirá um aviso alertando que todos os dados atuais serão substituídos e exigirá que você digite a palavra **`RESTAURAR`** (tudo em maiúsculas) para confirmar a operação.
5. Digite e pressione Enter. O banco de dados será limpo e restaurado para o estado exato daquele backup.

---

## 10. Configuração de Produção e HTTPS (Infraestrutura/Segurança)

Para garantir a total segurança dos dados confidenciais de saúde de seus pacientes (conforme exigido pela LGPD), a aplicação em produção deve rodar sob criptografia SSL/HTTPS.

### A. Funcionamento da Segurança
* **Porta Protegida**: O aplicativo Streamlit (porta `8501`) é totalmente isolado e fica inacessível diretamente pela internet.
* **Nginx**: Atua como o único intermediário nas portas públicas padrão da internet: `80` (HTTP) e `443` (HTTPS).
* **HTTPS**: Criptografa a conexão de ponta a ponta (ativando o símbolo de cadeado de segurança no navegador da psicóloga).

### B. Inicialização Local (Modo Desenvolvimento com SSL Autoassinado)
Para testar a segurança HTTPS no seu computador local:
1. Abra o terminal (PowerShell) na pasta raiz do projeto.
2. Execute o script para gerar os certificados locais temporários:
   ```powershell
   powershell -ExecutionPolicy Bypass -File nginx/gerar_ssl_local.ps1
   ```
3. Suba a aplicação Docker normalmente:
   ```bash
   docker compose up --build -d
   ```
4. Acesse a aplicação em: `https://localhost` (o navegador mostrará um aviso de certificado autoassinado/não confiável porque é local, mas a conexão estará criptografada para teste).

### C. Publicação em Produção (Let's Encrypt - Gratuito e Oficial)
Quando for implantar o sistema em um servidor na nuvem (ex: AWS, DigitalOcean, Azure) com um domínio real (ex: `sistema.consultorio.com.br`):
1. **Apontamento**: Aponte o seu domínio (registro DNS do tipo `A`) para o IP público do seu servidor.
2. **Obtenção do Certificado**: Execute o Certbot Let's Encrypt no servidor para obter os arquivos oficiais de chave e certificado:
   ```bash
   sudo certbot certonly --standalone -d seu-dominio.com -d www.seu-dominio.com
   ```
3. **Mapeamento**: Copie ou aponte os certificados oficiais gerados pelo Certbot (`fullchain.pem` e `privkey.pem`) para a pasta do projeto `nginx/certs/`.
4. **Reinicie a Infraestrutura**:
   ```bash
   docker compose down
   docker compose up --build -d
   ```
A partir de agora, a psicóloga poderá acessar o endereço `https://seu-dominio.com` de qualquer computador com segurança de nível bancário e conformidade LGPD.


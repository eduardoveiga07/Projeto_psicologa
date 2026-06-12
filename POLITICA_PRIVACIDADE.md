# Política Operacional de Privacidade e Proteção de Dados (LGPD)
*Gestão Consultório de Psicologia*

Este documento descreve as diretrizes operacionais de proteção de dados pessoais implementadas neste sistema, em total conformidade com a **Lei Geral de Proteção de Dados Pessoais (LGPD) — Lei nº 13.709/2018**.

---

## 1. Dados Coletados e Finalidade
O sistema armazena informações estritamente necessárias para a gestão administrativa, financeira e de agenda do consultório:
- **Dados Cadastrais do Paciente**: Nome completo, telefone (WhatsApp para comunicação), email (para fins de faturamento/comunicação) e data de nascimento (necessária para identificação de faixa etária e anamnese).
- **Dados do Contrato**: Frequência acordada, valor da sessão, dias da semana e horário fixo de atendimento.
- **Histórico de Contratos**: Snapshots de vigência para garantir que os cálculos do faturamento retroativo previsto e realizado não sejam alterados caso o paciente mude as condições de contrato.
- **Histórico de Sessões**: Registro de presença (Agendada, Confirmada, Realizada, Falta, Cancelamentos com/sem ônus) e status de pagamento de cada sessão.
- **Dados Clínicos**: O sistema **não** armazena prontuários de atendimento, evolução clínica ou notas de sessões de psicoterapia. O uso é restrito à gestão de horários e faturamento.

---

## 2. Direitos do Titular (Paciente)
O sistema foi desenhado para viabilizar o exercício dos direitos dos titulares de dados de forma simples e direta pelo(a) psicólogo(a) responsável:

### A. Direito de Acesso e Portabilidade
Através do botão de exportação (`📥`) presente em cada listagem de pacientes (ativos, inativos e em avaliação inicial), o sistema gera um arquivo **JSON** estruturado e de fácil leitura por máquinas, contendo todos os dados coletados do titular:
- Informações cadastrais atuais;
- Histórico de vigência de contratos anteriores;
- Exceções de horários registradas;
- Histórico de todas as sessões agendadas ou registradas no banco de dados.

### B. Direito de Eliminação (Esquecimento)
O sistema implementa dois fluxos de exclusão física dos dados:
1. **Exclusão Manual Segura**: Em conformidade com a LGPD, o usuário (com privilégio administrativo) pode excluir fisicamente um paciente (seja em avaliação inicial ou após ser movido para inativo). A exclusão exige confirmação explícita digitando a palavra `'EXCLUIR'` e remove fisicamente, via propagação em cascata (`CASCADE`), todos os registros cadastrais, contratos, sessões e exceções de horários associados.
2. **Retenção Limitada e Descarte Automático**: Pacientes que foram marcados como *Inativos* e estão sem retorno ou sessões registradas há **mais de 2 anos (730 dias)** são removidos de forma automática e permanente do banco de dados na inicialização do sistema, evitando a guarda por tempo indeterminado de dados pessoais sem finalidade operacional.

---

## 3. Segurança da Informação

### A. Controle de Acesso e Perfis
O acesso ao sistema é pessoal, intransferível e controlado por senhas hash criptografadas usando o algoritmo **bcrypt**. As permissões são distribuídas com base no princípio do menor privilégio, através de quatro perfis:
- **Dona**: Acesso pleno à gestão do consultório e criação/exclusão de usuários.
- **Secretária**: Acesso restrito a agendamentos, calendários e pagamentos (sem visualização do módulo financeiro).
- **Financeiro**: Acesso restrito ao módulo financeiro e pagamentos (sem visualização de agendas detalhadas ou cadastro de pacientes).
- **Programador**: Acesso global voltado à manutenção do sistema.

### B. Sessão Segura
O sistema implementa um **timeout automático de inatividade de 15 minutos**. Caso o usuário deixe a tela aberta no consultório sem interação, a sessão é limpa e exige uma nova autenticação para evitar acessos não autorizados por terceiros no ambiente de trabalho.

### C. Auditoria Minimizada
Eventos críticos como criação de novos usuários, exclusão de pacientes, alterações cadastrais ou remarcações de sessões são registrados em uma tabela de **Auditoria**. Para mitigar o vazamento de informações cadastrais em caso de acesso ao banco de logs:
- **Dados Pessoais são Omitidos**: Logs de auditoria nunca armazenam nomes, telefones ou emails de pacientes.
- **Identificação Indireta**: Eventos críticos de pacientes utilizam apenas o identificador único interno do sistema (UUID), inviabilizando a identificação direta do titular a partir de uma inspeção isolada da tabela de logs.

---

## 4. Recomendações de Infraestrutura
Para manter o ambiente local seguro:
1. **Ambiente Isolado**: O banco de dados PostgreSQL roda em rede interna do Docker e não expõe portas diretamente para a máquina host.
2. **Tráfego Seguro**: Recomenda-se utilizar HTTPS/Proxy Reverso (como Nginx ou Caddy) caso o sistema seja implantado em rede ou acessado externamente.
3. **Backup Criptografado**: Realizar a rotina de backups utilizando os scripts fornecidos e armazenar os arquivos `.dump` gerados em local externo seguro e protegido por criptografia de ponta a ponta.

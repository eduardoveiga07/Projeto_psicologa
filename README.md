# Gestao Consultorio Psicologia - Modelo Teste

Este sistema web em Streamlit gerencia o consultório de psicologia, integrando controle de pacientes, agenda, faturamento (previsto vs realizado), despesas, feriados, indisponibilidades, usuários e auditoria.

## 📖 Documentação de Uso e Políticas
- Para aprender a operar o sistema no dia a dia (agendamentos, pagamentos, despesas e relatórios), consulte o **[Manual de Uso da Profissional](file:///c:/Users/eduar/Downloads/projeto_consultorio/MANUAL_USO.md)**.
- Para entender as práticas de segurança da informação e conformidade com a LGPD implementadas, consulte a **[Política Operacional de Privacidade](file:///c:/Users/eduar/Downloads/projeto_consultorio/POLITICA_PRIVACIDADE.md)**.
- Para detalhes técnicos da arquitetura e infraestrutura, consulte a **[Documentação Técnica](file:///c:/Users/eduar/Downloads/projeto_consultorio/DOCUMENTACAO.md)**.

## Subir o sistema (Docker)
```
docker compose up --build
```
Acesse: http://localhost:8501

Primeiro acesso: se ainda nao existir usuario no banco, expanda
"Primeiro acesso (criar usuario)" na tela de login e crie o usuario Dona.

Opcionalmente, defina `BOOTSTRAP_ADMIN_PASSWORD` no `.env` para criar o
primeiro administrador automaticamente na subida inicial. Nao ha senhas padrao
fixas no codigo.

## Rodar local sem Docker
```
pip install -r requirements.txt
# subir um PostgreSQL e exportar:
export DATABASE_URL="postgresql+psycopg2://psico:psico@localhost:5432/consultorio"
streamlit run app/main.py
```

## Rodar testes
```
python -m unittest discover -s tests
```

## Migracoes de banco
```
alembic upgrade head
alembic revision --autogenerate -m "descreva a mudanca"
```

O Alembic usa `DATABASE_URL` quando configurado.

Para banco ja existente criado pela versao antiga do app, faca backup e use
`alembic stamp head` apenas depois de conferir que o schema esta equivalente.

## Backup e restauracao
Com Docker Compose rodando:
```
powershell -ExecutionPolicy Bypass -File scripts/backup_db.ps1
powershell -ExecutionPolicy Bypass -File scripts/restore_db.ps1 -BackupFile backups/NOME_DO_ARQUIVO.dump
```

Os backups locais ficam em `backups/`, que nao e versionado pelo Git.

## Comprovantes de pagamento

O sistema permite anexar comprovantes (PDF, PNG, JPG — máximo 10 MB) em sessões e despesas.

> ⚠️ **Limitação no Streamlit Cloud:** o filesystem é efêmero — arquivos em `uploads/` podem ser perdidos em reinicializações. Os **metadados** (nome original, MIME, tamanho, data de envio) permanecem **permanentemente no banco PostgreSQL**. A interface exibe `⚠️ Arquivo ausente` quando o arquivo físico não é encontrado, sem quebrar o sistema.

**TODO técnico:** substituir `salvar_comprovante()` em `app/services/comprovantes.py` por Supabase Storage, S3 ou Google Drive para storage persistente em produção. Nenhuma tela precisa ser alterada — ver [DOCUMENTACAO.md § Comprovantes — Arquitetura de Storage](DOCUMENTACAO.md) para guia completo com código de exemplo.

## Estrutura
- app/db        modelos e conexao
- app/services  motor financeiro (previsto vs realizado, DRE) + storage de comprovantes
- app/auth      login bcrypt
- app/main.py   interface (Cadastro / Agenda / Financeiro / Saúde do Sistema)

## Pendente (apos validacao da profissional)
- Modulo 3: automacao WhatsApp (Meta Cloud API - exige conta paga)
- **TODO:** trocar storage local de comprovantes por S3/Supabase Storage em producao

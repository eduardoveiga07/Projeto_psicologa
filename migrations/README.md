# Migrações de banco

Este diretório contém migrações Alembic.

Comandos úteis:

```bash
alembic upgrade head
alembic revision --autogenerate -m "descreva a mudanca"
```

O Alembic usa `DATABASE_URL` quando a variável estiver definida. Caso contrário,
usa a URL fallback configurada em `alembic.ini`.

Para bancos que ja foram criados pela versao antiga do app, faca backup e
confira se o schema esta equivalente antes de marcar a versao atual:

```bash
alembic stamp head
```

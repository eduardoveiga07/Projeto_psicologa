# Gestao Consultorio Psicologia - Modelo Teste

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

## Estrutura
- app/db        modelos e conexao
- app/services  motor financeiro (previsto vs realizado, DRE)
- app/auth      login bcrypt
- app/main.py   interface (Cadastro / Agenda / Financeiro)

## Pendente (apos validacao da profissional)
- Modulo 3: automacao WhatsApp (Meta Cloud API - exige conta paga)

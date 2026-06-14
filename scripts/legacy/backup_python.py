# DEPRECATED: Este arquivo foi desativado em favor do Neon PITR nativo em produção.
# Mantido apenas para referência histórica.

import json
import uuid
from datetime import datetime, date
from decimal import Decimal
from sqlalchemy import text
from app.db.models import (
    Usuario, Paciente, ContratoHistorico, AgendaSessao,
    Despesa, Auditoria, Indisponibilidade, SistemaStatus, FechamentoMensal
)

def serialize_value(v):
    if isinstance(v, datetime):
        return {"__type__": "datetime", "value": v.isoformat()}
    elif isinstance(v, date):
        return {"__type__": "date", "value": v.isoformat()}
    elif isinstance(v, Decimal):
        return {"__type__": "decimal", "value": str(v)}
    elif isinstance(v, uuid.UUID):
        return {"__type__": "uuid", "value": str(v)}
    return v

def deserialize_value(v):
    if isinstance(v, dict) and "__type__" in v:
        t = v["__type__"]
        val = v["value"]
        if t == "datetime":
            return datetime.fromisoformat(val)
        elif t == "date":
            return date.fromisoformat(val)
        elif t == "decimal":
            return Decimal(val)
        elif t == "uuid":
            return uuid.UUID(val)
    return v

def dump_database_to_json(db) -> str:
    """Exporta todas as linhas de todas as tabelas do banco de dados para uma string JSON."""
    modelos = [
        Usuario,
        Paciente,
        ContratoHistorico,
        AgendaSessao,
        Despesa,
        Auditoria,
        Indisponibilidade,
        SistemaStatus,
        FechamentoMensal
    ]
    
    backup_data = {}
    for model in modelos:
        table_name = model.__tablename__
        rows = db.query(model).all()
        serialized_rows = []
        for row in rows:
            row_dict = {}
            for col in model.__table__.columns:
                val = getattr(row, col.name)
                row_dict[col.name] = serialize_value(val)
            serialized_rows.append(row_dict)
        backup_data[table_name] = serialized_rows
        
    return json.dumps(backup_data, indent=2)

def restore_database_from_json(db, json_str: str) -> None:
    """Limpa e restaura todos os dados de tabelas a partir de uma string JSON."""
    backup_data = json.loads(json_str)
    
    modelos_delete_order = [
        AgendaSessao,
        ContratoHistorico,
        Paciente,
        Usuario,
        Despesa,
        Auditoria,
        Indisponibilidade,
        SistemaStatus,
        FechamentoMensal
    ]
    
    # 1. Limpa dados existentes na ordem reversa de chaves estrangeiras
    for model in modelos_delete_order:
        db.query(model).delete()
    db.flush()
    
    modelos_insert_order = [
        Usuario,
        Paciente,
        ContratoHistorico,
        AgendaSessao,
        Despesa,
        Auditoria,
        Indisponibilidade,
        SistemaStatus,
        FechamentoMensal
    ]
    
    # 2. Insere dados novos na ordem correta de chaves estrangeiras
    for model in modelos_insert_order:
        table_name = model.__tablename__
        if table_name not in backup_data:
            continue
        for row_dict in backup_data[table_name]:
            obj_kwargs = {}
            for k, v in row_dict.items():
                obj_kwargs[k] = deserialize_value(v)
            db.add(model(**obj_kwargs))
    db.flush()
    
    # 3. Reseta sequências de PKs numéricas no PostgreSQL
    for model in modelos_insert_order:
        pk_cols = [c for c in model.__table__.columns if c.primary_key and c.type.python_type == int]
        if pk_cols:
            table_name = model.__tablename__
            col_name = pk_cols[0].name
            try:
                db.execute(text(
                    f"SELECT setval(pg_get_serial_sequence('{table_name}', '{col_name}'), "
                    f"coalesce(max({col_name}), 1), true) FROM {table_name}"
                ))
            except Exception:
                pass
    db.commit()

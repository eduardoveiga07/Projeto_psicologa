import io
import zipfile
from datetime import datetime, timedelta
from openpyxl import Workbook
from sqlalchemy import inspect
from app.db.models import Paciente, AgendaSessao, Despesa, ContratoHistorico, Usuario, Auditoria, Base


def _criar_planilha_excel(model, query_obj, columns_to_exclude=None, extra_joins=None):
    """
    Função auxiliar genérica que transforma uma query do SQLAlchemy em planilha Excel (.xlsx) em memória.
    """
    wb = Workbook()
    ws = wb.active
    ws.title = "Dados"

    # Inspeciona as colunas do modelo SQLAlchemy
    mapper = inspect(model)
    cols = [c.key for c in mapper.column_attrs]
    if columns_to_exclude:
        cols = [c for c in cols if c not in columns_to_exclude]

    # Cabeçalho da tabela
    headers = cols.copy()
    if extra_joins:
        headers.extend(extra_joins.keys())
    ws.append(headers)

    # Adiciona as linhas
    for row in query_obj.all():
        row_data = []
        if isinstance(row, tuple):
            instance = row[0]
        else:
            instance = row

        for c in cols:
            val = getattr(instance, c, None)
            # Converte timezone-aware datetime ou outros formatos se necessário (openpyxl trata a maioria nativamente)
            row_data.append(val)

        if extra_joins and isinstance(row, tuple):
            # Adiciona os campos extras do JOIN (começa a partir do índice 1 da tupla do row)
            for idx in range(1, len(row)):
                row_data.append(row[idx])

        ws.append(row_data)

    # Escreve em bytes
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def gerar_exportacao_zip(db) -> bytes:
    """
    Gera um arquivo ZIP em memória contendo todas as tabelas em formato Excel (.xlsx).
    """
    # 1. Obter os dados em formato Excel
    # Pacientes
    query_pacientes = db.query(Paciente)
    pacientes_xlsx = _criar_planilha_excel(
        Paciente, query_pacientes, columns_to_exclude=['id_paciente']
    )

    # Sessões (com JOIN para obter nome do paciente)
    query_sessoes = db.query(AgendaSessao, Paciente.nome).join(
        Paciente, AgendaSessao.id_paciente == Paciente.id_paciente
    )
    sessoes_xlsx = _criar_planilha_excel(
        AgendaSessao, query_sessoes,
        columns_to_exclude=['id_paciente'],
        extra_joins={'nome_paciente': Paciente.nome}
    )

    # Despesas
    query_despesas = db.query(Despesa)
    despesas_xlsx = _criar_planilha_excel(Despesa, query_despesas)

    # Contratos Histórico
    query_contratos = db.query(ContratoHistorico, Paciente.nome).join(
        Paciente, ContratoHistorico.id_paciente == Paciente.id_paciente
    )
    contratos_xlsx = _criar_planilha_excel(
        ContratoHistorico, query_contratos,
        columns_to_exclude=['id_paciente'],
        extra_joins={'nome_paciente': Paciente.nome}
    )

    # Usuários (sem senha_hash)
    query_usuarios = db.query(Usuario)
    usuarios_xlsx = _criar_planilha_excel(
        Usuario, query_usuarios, columns_to_exclude=['senha_hash']
    )

    # Auditoria (últimos 12 meses)
    limite_data = datetime.now() - timedelta(days=365)
    query_auditoria = db.query(Auditoria).filter(
        Auditoria.quando >= limite_data
    ).order_by(Auditoria.quando.desc())
    auditoria_xlsx = _criar_planilha_excel(Auditoria, query_auditoria)

    # 2. Criar README.txt
    readme_content = f"""Relatório de Exportação de Dados do Consultório
Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}

Este arquivo compactado ZIP contém todos os dados estruturados do consultório em formato Excel (.xlsx).
Abaixo estão os arquivos inclusos e suas descrições:

1. pacientes.xlsx: Lista completa de pacientes (ativos e inativos). A coluna interna id_paciente foi omitida por privacidade.
2. sessoes.xlsx: Registro histórico de agendamentos e sessões de terapia, exibindo o nome do paciente em vez de IDs técnicos.
3. despesas.xlsx: Controle histórico de despesas operacionais do consultório.
4. contratos_historico.xlsx: Histórico de vigências contratuais de atendimento associados a cada paciente.
5. usuarios.xlsx: Lista de usuários autorizados do sistema (senhas criptografadas omitidas).
6. auditoria.xlsx: Trilha de auditoria técnica e operacional do sistema. Contém apenas os registros dos últimos 12 meses para otimização de processamento.

INSTRUÇÕES DE SEGURANÇA:
* Este arquivo contém dados pessoais e financeiros sensíveis (sujeitos à LGPD).
* Guarde esta exportação em local seguro offline (HD externo, pendrive, cofre digital pessoal).
* Não compartilhe estes arquivos de forma desprotegida.
* Em caso de necessidade de restauração de dados por desastre técnico, contate o desenvolvedor do sistema com este arquivo em mãos.
"""

    # 3. Compactar no ZIP em memória
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        zip_file.writestr("pacientes.xlsx", pacientes_xlsx)
        zip_file.writestr("sessoes.xlsx", sessoes_xlsx)
        zip_file.writestr("despesas.xlsx", despesas_xlsx)
        zip_file.writestr("contratos_historico.xlsx", contratos_xlsx)
        zip_file.writestr("usuarios.xlsx", usuarios_xlsx)
        zip_file.writestr("auditoria.xlsx", auditoria_xlsx)
        zip_file.writestr("README.txt", readme_content)

    return zip_buffer.getvalue()

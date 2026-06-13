"""Historico de contrato do paciente.
Toda mudanca de freq/dias/valor/semana/paridade fecha o periodo vigente e
abre novo. O financeiro consulta o snapshot vigente no mes para calcular
o previsto historicamente correto."""
from datetime import date, timedelta
from decimal import Decimal
from app.db.models import Paciente, ContratoHistorico, Frequencia


# Campos do contrato que importam para o previsto financeiro.
CAMPOS_CONTRATO = ("frequencia", "valor_sessao", "dias_semana",
                   "semana_do_mes", "paridade_quinzenal",
                   "sessoes_mes_custom")


def snapshot_vigente(db, id_paciente, ref: date) -> ContratoHistorico | None:
    """Retorna o contrato vigente na data 'ref' (ou None se nao havia)."""
    q = db.query(ContratoHistorico).filter(
        ContratoHistorico.id_paciente == id_paciente,
        ContratoHistorico.vigente_de <= ref,
    ).filter(
        (ContratoHistorico.vigente_ate.is_(None))
        | (ContratoHistorico.vigente_ate >= ref)
    ).order_by(ContratoHistorico.vigente_de.desc())
    return q.first()


def snapshot_vigente_em_memoria(historico: list, ref: date) -> ContratoHistorico | None:
    """Retorna o contrato vigente na data 'ref' a partir da lista 'historico' em memoria.
    A lista 'historico' deve estar ordenada por vigente_de desc (mais recente primeiro)."""
    for snap in historico:
        if snap.vigente_de <= ref:
            if snap.vigente_ate is None or snap.vigente_ate >= ref:
                return snap
    return None


def abrir_periodo(db, p: Paciente, inicio: date, commit: bool = True
                  ) -> ContratoHistorico:
    """Fecha o periodo vigente (se houver) e abre um novo a partir de 'inicio'
    com os valores atuais do paciente. Idempotente: se ja existe periodo
    vigente identico ao do paciente comecando em 'inicio', nao duplica."""
    vig = db.query(ContratoHistorico).filter(
        ContratoHistorico.id_paciente == p.id_paciente,
        ContratoHistorico.vigente_ate.is_(None),
    ).order_by(ContratoHistorico.vigente_de.desc()).first()

    novo_snap = dict(
        frequencia=p.frequencia,
        valor_sessao=p.valor_sessao,
        dias_semana=p.dias_semana,
        semana_do_mes=p.semana_do_mes,
        paridade_quinzenal=p.paridade_quinzenal,
        sessoes_mes_custom=p.sessoes_mes_custom,
    )

    if vig:
        # Se o snapshot vigente ja eh identico, nao faz nada
        if all(getattr(vig, k) == novo_snap[k] for k in novo_snap):
            return vig
        # Fecha o vigente no dia anterior ao novo inicio
        vig.vigente_ate = inicio - timedelta(days=1)
        if vig.vigente_ate < vig.vigente_de:
            # Edicao no mesmo dia que abriu -> sobrescreve em vez de duplicar
            for k, v in novo_snap.items():
                setattr(vig, k, v)
            vig.vigente_ate = None
            if commit:
                db.commit()
            return vig

    novo = ContratoHistorico(
        id_paciente=p.id_paciente,
        vigente_de=inicio,
        vigente_ate=None,
        **novo_snap,
    )
    db.add(novo)
    if commit:
        db.commit()
    return novo


def garantir_historico_inicial(db):
    """Migracao: para cada paciente sem nenhum registro de historico,
    cria 1 registro a partir do ativo_desde (ou data atual)."""
    pacientes = db.query(Paciente).all()
    ids_com_hist = {c.id_paciente for c in db.query(
        ContratoHistorico.id_paciente).distinct()}
    criados = 0
    for p in pacientes:
        if p.id_paciente in ids_com_hist:
            continue
        inicio = p.ativo_desde or date.today()
        db.add(ContratoHistorico(
            id_paciente=p.id_paciente,
            vigente_de=inicio,
            vigente_ate=None,
            frequencia=p.frequencia,
            valor_sessao=p.valor_sessao,
            dias_semana=p.dias_semana,
            semana_do_mes=p.semana_do_mes,
            paridade_quinzenal=p.paridade_quinzenal,
            sessoes_mes_custom=p.sessoes_mes_custom,
        ))
        criados += 1
    if criados:
        db.commit()
    return criados

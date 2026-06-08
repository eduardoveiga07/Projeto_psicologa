"""Datas/horarios indisponiveis (ferias, imprevistos)."""
from datetime import date, timedelta
from app.db.models import Indisponibilidade


def datas_dia_todo(db, ano: int, mes: int) -> set:
    """Set de datas (date) que estao bloqueadas o dia todo no ano/mes."""
    rs = db.query(Indisponibilidade).filter(
        Indisponibilidade.dia_todo == True).all()  # noqa: E712
    return {r.data for r in rs
            if r.data.year == ano and r.data.month == mes}


def horarios_bloqueados(db, d: date) -> set:
    """Set de strings de horario bloqueadas numa data especifica."""
    rs = db.query(Indisponibilidade).filter(
        Indisponibilidade.data == d,
        Indisponibilidade.dia_todo == False).all()  # noqa: E712
    return {r.horario for r in rs if r.horario}


def agrupar_em_ranges(regs: list) -> list:
    """Agrupa Indisponibilidades em grupos quando compartilham
    motivo/dia_todo/horario/observacao. Detecta dois padroes:
    - Range continuo (datas consecutivas): "01 ate 15/10/2026"
    - Recorrencia semanal (mesmo dia da semana, intervalo 7 dias): "toda
      Quinta de 04/06 ate 30/07/2026"
    Retorna lista de dicts: {ini, fim, motivo, dia_todo, horario, obs, ids,
                              padrao: 'continuo'|'semanal',
                              dia_semana (so se semanal)}."""
    if not regs:
        return []
    DIAS_PT = ["Segunda-feira", "Terça-feira", "Quarta-feira",
               "Quinta-feira", "Sexta-feira", "Sábado", "Domingo"]

    def chave(r):
        return (r.motivo.value, r.dia_todo, r.horario or "", r.observacao or "")

    # Agrupa todos com a mesma chave
    buckets = {}
    for r in regs:
        buckets.setdefault(chave(r), []).append(r)

    grupos = []
    for k, lista in buckets.items():
        lista.sort(key=lambda r: r.data)
        # Detecta padrao
        i = 0
        while i < len(lista):
            # Tenta consumir um range CONTINUO ou um padrao SEMANAL
            j = i + 1
            padrao_continuo_ok = True
            padrao_semanal_ok = True
            while j < len(lista):
                delta = (lista[j].data - lista[j - 1].data).days
                if delta != 1:
                    padrao_continuo_ok = False
                if delta != 7:
                    padrao_semanal_ok = False
                # Tambem semanal exige mesmo weekday
                if lista[j].data.weekday() != lista[i].data.weekday():
                    padrao_semanal_ok = False
                if not padrao_continuo_ok and not padrao_semanal_ok:
                    break
                j += 1
            # j eh o primeiro que NAO faz parte do padrao
            sub = lista[i:j]
            if len(sub) >= 3 and padrao_semanal_ok and not padrao_continuo_ok:
                padrao = "semanal"
                dia_sem = DIAS_PT[sub[0].data.weekday()]
            elif len(sub) >= 2 and padrao_continuo_ok:
                padrao = "continuo"
                dia_sem = None
            else:
                # Solto: pega so um por vez
                padrao = "continuo"
                dia_sem = None
                sub = [lista[i]]
                j = i + 1
            g = {"ini": sub[0].data, "fim": sub[-1].data,
                 "motivo": sub[0].motivo.value, "dia_todo": sub[0].dia_todo,
                 "horario": sub[0].horario, "obs": sub[0].observacao,
                 "ids": [r.id_indisp for r in sub], "padrao": padrao,
                 "dia_semana": dia_sem}
            grupos.append(g)
            i = j

    grupos.sort(key=lambda g: g["ini"], reverse=True)

    # 2o passe: junta grupos semanais que sao parte do mesmo
    # "compromisso multi-dia" (mesma obs+motivo+dia_todo+intervalo proximo)
    semanais = [g for g in grupos if g.get("padrao") == "semanal"]
    outros = [g for g in grupos if g.get("padrao") != "semanal"]
    # Chave de fusao: motivo+dia_todo+obs (sem horario)
    def chave_fusao(g):
        return (g["motivo"], g["dia_todo"], g.get("obs") or "")
    buckets2 = {}
    for g in semanais:
        buckets2.setdefault(chave_fusao(g), []).append(g)
    fundidos = []
    for k, lst in buckets2.items():
        if len(lst) == 1:
            fundidos.append(lst[0])
            continue
        # Une todos: 1 supergrupo
        lst.sort(key=lambda g: g["ini"])
        ini = min(g["ini"] for g in lst)
        fim = max(g["fim"] for g in lst)
        ids = [i for g in lst for i in g["ids"]]
        # Lista de (weekday_idx, dia_semana, horario)
        DIAS_PT_IDX = {n: i for i, n in enumerate(DIAS_PT)}
        slots = sorted([
            {"dia_semana": g["dia_semana"],
             "weekday": DIAS_PT_IDX.get(g["dia_semana"], 0),
             "horario": g["horario"]}
            for g in lst], key=lambda s: s["weekday"])
        super_g = {
            "ini": ini, "fim": fim,
            "motivo": lst[0]["motivo"],
            "dia_todo": lst[0]["dia_todo"],
            "horario": None,  # vazio: ver slots
            "obs": lst[0].get("obs"),
            "ids": ids,
            "padrao": "semanal_multi",
            "slots": slots,
        }
        fundidos.append(super_g)
    grupos = sorted(outros + fundidos, key=lambda g: g["ini"], reverse=True)
    return grupos


def formatar_grupo(g: dict) -> str:
    """Texto pronto pra exibir um grupo. Se motivo='Outro' e ha observacao,
    o motivo exibido eh a propria observacao (ex: 'Médico'), nao 'Outro'.
    Exemplos:
      'toda Quinta de 04/06 até 30/07/2026 — Médico — 13:00-14:00 (8 dias)'
      '01/10/2026 até 15/10/2026 — Férias — dia todo (15 dias)'
      '20/10/2026 — Imprevisto/Emergência — dia todo'."""
    if g["dia_todo"]:
        quando = "dia todo"
    else:
        quando = g["horario"]
    # Se motivo Outro + obs, troca o nome do motivo pela obs
    motivo_label = g["motivo"]
    obs_extra = g.get("obs") or ""
    if motivo_label == "Outro" and obs_extra:
        motivo_label = obs_extra
        obs_extra = ""  # ja foi usada como motivo
    if g["ini"] == g["fim"]:
        cabeca = g["ini"].strftime("%d/%m/%Y")
        contagem = ""
    elif g.get("padrao") == "semanal_multi":
        # Multi-dia: "toda Terça (10:00-14:00) e Quinta (16:00-18:00) de 04/06 até 30/07/2026"
        slots = g.get("slots") or []
        partes = []
        for s in slots:
            nome = s["dia_semana"].replace("-feira", "")
            if g["dia_todo"]:
                partes.append(nome)
            else:
                partes.append(f"{nome} ({s['horario']})")
        if len(partes) == 2:
            dias_txt = " e ".join(partes)
        else:
            dias_txt = ", ".join(partes[:-1]) + " e " + partes[-1]
        cabeca = (f"toda {dias_txt} de "
                  f"{g['ini'].strftime('%d/%m')} até "
                  f"{g['fim'].strftime('%d/%m/%Y')}")
        contagem = f" ({len(g['ids'])} ocorrências)"
        obs_txt = (f" — _{g.get('obs')}_"
                   if (g.get('obs') and motivo_label == g['motivo']) else "")
        # Para multi nao precisa "— quando" pq ja vai em cada slot
        return f"{cabeca} — {motivo_label}{contagem}{obs_txt}"
    elif g.get("padrao") == "semanal":
        cabeca = (f"toda {g['dia_semana']} de "
                  f"{g['ini'].strftime('%d/%m')} até "
                  f"{g['fim'].strftime('%d/%m/%Y')}")
        contagem = f" ({len(g['ids'])} ocorrências)"
    else:
        cabeca = (f"{g['ini'].strftime('%d/%m/%Y')} até "
                  f"{g['fim'].strftime('%d/%m/%Y')}")
        contagem = f" ({len(g['ids'])} dias)"
    obs_txt = f" — _{obs_extra}_" if obs_extra else ""
    return f"{cabeca} — {motivo_label} — {quando}{contagem}{obs_txt}"

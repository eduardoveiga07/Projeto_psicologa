import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from datetime import datetime, date, time, timedelta
from app.db.session import get_session
from app.db.models import Paciente, AgendaSessao, ContratoHistorico, Indisponibilidade, StatusPaciente, StatusPresenca, StatusPagamento
from app.services.agenda_geracao import AgendaGeracaoService

def migrar():
    db = get_session()
    try:
        print("Iniciando migração de dados para sessões reais...")
        
        # 1. Atualizar todas as sessões existentes no banco com valor_sessao
        sessoes_existentes = db.query(AgendaSessao).all()
        print(f"Atualizando {len(sessoes_existentes)} sessões existentes no banco com valores e flags...")
        
        # Mapeamos os contratos de todos os pacientes para evitar N+1
        contratos_db = db.query(ContratoHistorico).order_by(ContratoHistorico.vigente_de.desc()).all()
        contratos_dict = {}
        for c in contratos_db:
            contratos_dict.setdefault(c.id_paciente, []).append(c)
            
        pacientes_db = db.query(Paciente).all()
        pacientes_dict = {p.id_paciente: p for p in pacientes_db}
        
        from app.services.contrato import snapshot_vigente_em_memoria
        
        atualizadas = 0
        for s in sessoes_existentes:
            p = pacientes_dict.get(s.id_paciente)
            if not p:
                continue
            hist_p = contratos_dict.get(s.id_paciente, [])
            dt = s.data_hora_inicio.date()
            snap = snapshot_vigente_em_memoria(hist_p, dt)
            
            s.valor_sessao = snap.valor_sessao if snap else p.valor_sessao
            s.recorrente = True
            atualizadas += 1
            
        db.commit()
        print(f"{atualizadas} sessões existentes atualizadas com sucesso!")
        
        # 2. Gerar sessões futuras a partir de hoje
        hoje = datetime.now().date()
        pacientes_ativos = db.query(Paciente).filter(Paciente.status == StatusPaciente.ATIVO).all()
        print(f"Gerando sessões futuras para {len(pacientes_ativos)} pacientes ativos...")
        
        geradas = 0
        for p in pacientes_ativos:
            inicio_gen = hoje
            if p.ativo_desde and p.ativo_desde > hoje:
                inicio_gen = p.ativo_desde
                
            total_antes = db.query(AgendaSessao).filter(AgendaSessao.id_paciente == p.id_paciente).count()
            AgendaGeracaoService.gerar_sessoes_futuras(db, p, inicio_gen, limite_meses=12)
            db.commit()
            total_depois = db.query(AgendaSessao).filter(AgendaSessao.id_paciente == p.id_paciente).count()
            geradas += (total_depois - total_antes)
            
        print(f"Migração concluída com sucesso! {geradas} novas sessões geradas no futuro.")
    except Exception as e:
        db.rollback()
        print(f"Erro durante a migração: {e}")
        sys.exit(1)
    finally:
        db.close()

if __name__ == "__main__":
    migrar()

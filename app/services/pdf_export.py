"""Gera PDF simples a partir de uma lista de dicionarios (tabela)."""
from io import BytesIO
from datetime import datetime
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfgen import canvas
from reportlab.pdfbase.pdfmetrics import stringWidth


class NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_elements(num_pages)
            super().showPage()
        super().save()

    def draw_page_elements(self, page_count):
        self.saveState()
        
        # --- RODAPÉ ---
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#7f8c8d"))
        
        # Texto confidencial à esquerda
        self.drawString(1.5 * cm, 0.8 * cm, "Documento Restrito — Gestão Clínica (Conformidade LGPD)")
        
        # Paginação à direita
        page_text = f"Página {self._pageNumber} de {page_count}"
        self.drawRightString(self._pagesize[0] - 1.5 * cm, 0.8 * cm, page_text)
        
        # Linha decorativa rodapé
        self.setStrokeColor(colors.HexColor("#ccd6d3"))
        self.setLineWidth(0.5)
        self.line(1.5 * cm, 1.2 * cm, self._pagesize[0] - 1.5 * cm, 1.2 * cm)
        
        # --- CABEÇALHO COMPACTO (PÁGINA 2+) ---
        if self._pageNumber > 1:
            self.setFont("Helvetica-Bold", 8)
            self.setFillColor(colors.HexColor("#165a4c"))
            self.drawString(1.5 * cm, self._pagesize[1] - 1.0 * cm, "Consultório de Psicologia — Gestão Clínica")
            self.setFont("Helvetica", 8)
            self.setFillColor(colors.HexColor("#7f8c8d"))
            self.drawRightString(self._pagesize[0] - 1.5 * cm, self._pagesize[1] - 1.0 * cm, "Relatório Operacional")
            self.setStrokeColor(colors.HexColor("#ccd6d3"))
            self.setLineWidth(0.5)
            self.line(1.5 * cm, self._pagesize[1] - 1.1 * cm, self._pagesize[0] - 1.5 * cm, self._pagesize[1] - 1.1 * cm)
            
        self.restoreState()


def gerar_pdf(titulo: str, linhas: list, filtros: dict = None, totais: dict = None) -> bytes:
    """Gera um relatório PDF elegante a partir de uma lista de dicionários.
    Aceita filtros: dict (filtros aplicados) e totais: dict (totais acumulados)."""
    buf = BytesIO()
    
    # Definindo margens do documento
    doc = SimpleDocTemplate(
        buf, 
        pagesize=landscape(A4),
        leftMargin=1.5 * cm,
        rightMargin=1.5 * cm,
        topMargin=1.5 * cm,
        bottomMargin=2.0 * cm
    )
    
    estilos = getSampleStyleSheet()
    
    # Criar estilos customizados para o título
    titulo_estilo = ParagraphStyle(
        "CustomTitle",
        parent=estilos["Title"],
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=22,
        textColor=colors.HexColor("#0f3d3e"),
        alignment=0,  # Alinhado à esquerda
        spaceAfter=10
    )
    
    # Estilos de parágrafo para a tabela (garantir auto-wrap de texto)
    estilo_celula = ParagraphStyle(
        "TableCell",
        parent=estilos["Normal"],
        fontName="Helvetica",
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#2e3340")
    )
    
    estilo_cabecalho = ParagraphStyle(
        "TableHeader",
        parent=estilos["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=10,
        textColor=colors.white
    )
    
    estilo_total = ParagraphStyle(
        "TableTotal",
        parent=estilos["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#0f3d3e")
    )
    
    elementos = []
    
    # 1. Cabeçalho decorativo (Flowables)
    # Título do Relatório
    elementos.append(Paragraph(titulo, titulo_estilo))
    
    # Data de Geração e Identificação do Consultório
    meta_estilo = ParagraphStyle(
        "MetaStyle",
        parent=estilos["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#7f8c8d")
    )
    data_geracao = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    elementos.append(Paragraph("<b>Consultório de Psicologia</b> — Sistema de Gestão", meta_estilo))
    elementos.append(Paragraph(f"Gerado em: {data_geracao}", meta_estilo))
    elementos.append(Spacer(1, 0.3 * cm))
    
    # Linha decorativa verde petróleo abaixo do cabeçalho
    linha_decorativa = Table([[""]], colWidths=[doc.width], rowHeights=[2.5])
    linha_decorativa.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#0f3d3e")),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    elementos.append(linha_decorativa)
    elementos.append(Spacer(1, 0.4 * cm))
    
    # 2. Seção de Filtros (se fornecidos)
    if filtros:
        filtros_estilo = ParagraphStyle(
            "FiltrosStyle",
            parent=estilos["Normal"],
            fontName="Helvetica",
            fontSize=8,
            leading=11,
            textColor=colors.HexColor("#1b4d3e")
        )
        filtros_itens = []
        for k, v in filtros.items():
            filtros_itens.append(f"<b>{k}:</b> {v}")
        filtros_str = " | ".join(filtros_itens)
        
        # Box de filtros com fundo cinza claro e borda suave
        t_filtros = Table([[Paragraph(f"🔍 <b>Filtros aplicados:</b> {filtros_str}", filtros_estilo)]], colWidths=[doc.width])
        t_filtros.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f4f7f6")),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#ccd6d3")),
            ("PADDING", (0, 0), (-1, -1), 6),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))
        elementos.append(t_filtros)
        elementos.append(Spacer(1, 0.5 * cm))
        
    # 3. Tabela de Dados
    if not linhas:
        elementos.append(Paragraph("Sem registros encontrados.", estilos["Normal"]))
    else:
        cols = list(linhas[0].keys())
        
        # Envolve os cabeçalhos em Paragraph para quebra de linha se necessário
        cabecalhos_p = [Paragraph(col, estilo_cabecalho) for col in cols]
        
        # Envolve os dados em Paragraph
        linhas_p = []
        for l in linhas:
            linha_p = []
            for col in cols:
                val = str(l.get(col, ""))
                linha_p.append(Paragraph(val, estilo_celula))
            linhas_p.append(linha_p)
            
        dados = [cabecalhos_p] + linhas_p
        
        # Se totais for fornecido, adicionamos a linha de total formatada
        if totais:
            linha_total = []
            for i, col in enumerate(cols):
                if i == 0:
                    linha_total.append(Paragraph("TOTAL", estilo_total))
                elif col in totais:
                    linha_total.append(Paragraph(str(totais[col]), estilo_total))
                else:
                    linha_total.append(Paragraph("", estilo_total))
            dados.append(linha_total)
            
        # --- Cálculo Inteligente e Proporcional de Larguras de Colunas ---
        largura_disponivel = doc.width  # Largura útil da página
        larguras_desejadas = []
        
        for col in cols:
            # Largura com base no cabeçalho
            max_w = stringWidth(str(col), "Helvetica-Bold", 8)
            # Largura com base nos registros
            for l in linhas:
                val = str(l.get(col, ""))
                # Se for um valor longo, limitamos a estimativa no cálculo para evitar inflar demais
                val_truncado = val[:40]
                val_w = stringWidth(val_truncado, "Helvetica", 8)
                if val_w > max_w:
                    max_w = val_w
            
            # Adiciona 12 pontos para padding das células (6 pontos esquerda + 6 pontos direita)
            larguras_desejadas.append(max_w + 12)
            
        # Distribui proporcionalmente
        soma_desejada = sum(larguras_desejadas)
        if soma_desejada > 0:
            largura_minima = 45.0  # pontos
            # Primeira aproximação proporcional
            col_widths = [max(largura_minima, w * (largura_disponivel / soma_desejada)) for w in larguras_desejadas]
            
            # Normalização final para garantir que feche exatamente na largura disponível
            soma_ajustada = sum(col_widths)
            if abs(soma_ajustada - largura_disponivel) > 1.0:
                col_widths = [w * (largura_disponivel / soma_ajustada) for w in col_widths]
        else:
            col_widths = [largura_disponivel / len(cols)] * len(cols)
            
        t = Table(dados, colWidths=col_widths, repeatRows=1)
        
        # Configurar estilos de tabela
        estilo_tabela = [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#165a4c")),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#ccd6d3")),
            ("ROWBACKGROUNDS", (0, 1), (-1, (-2 if totais else -1)),
             [colors.white, colors.HexColor("#f4f7f6")]),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),  # Alinha no topo para parágrafos com quebra
            ("PADDING", (0, 0), (-1, -1), 6),
        ]
        
        if totais:
            # Estilo especial para a linha de totais (última linha)
            estilo_tabela.extend([
                ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#e1e9e6")),
                ("LINEABOVE", (0, -1), (-1, -1), 1.2, colors.HexColor("#165a4c")),
                ("PADDING", (0, -1), (-1, -1), 7),
                ("VALIGN", (0, -1), (-1, -1), "MIDDLE"),
            ])
            
        t.setStyle(TableStyle(estilo_tabela))
        elementos.append(t)
        
    # Construção do documento passando o NumberedCanvas customizado
    doc.build(elementos, canvasmaker=NumberedCanvas)
    return buf.getvalue()


def gerar_pdf_portabilidade(p, contratos: list, sessoes: list) -> bytes:
    """Gera um PDF estruturado contendo todos os dados do paciente para conformidade LGPD."""
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,  # Retrato para documento cadastral
        leftMargin=1.5 * cm,
        rightMargin=1.5 * cm,
        topMargin=1.5 * cm,
        bottomMargin=2.0 * cm
    )
    
    estilos = getSampleStyleSheet()
    
    titulo_estilo = ParagraphStyle(
        "LgpdTitle",
        parent=estilos["Title"],
        fontName="Helvetica-Bold",
        fontSize=16,
        leading=20,
        textColor=colors.HexColor("#0f3d3e"),
        alignment=0,
        spaceAfter=15
    )
    
    h1_estilo = ParagraphStyle(
        "LgpdH1",
        parent=estilos["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=16,
        textColor=colors.HexColor("#165a4c"),
        spaceBefore=12,
        spaceAfter=6
    )
    
    texto_estilo = ParagraphStyle(
        "LgpdText",
        parent=estilos["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#2e3340")
    )
    
    texto_bold_estilo = ParagraphStyle(
        "LgpdTextBold",
        parent=texto_estilo,
        fontName="Helvetica-Bold"
    )
    
    estilo_celula = ParagraphStyle(
        "LgpdCell",
        parent=estilos["Normal"],
        fontName="Helvetica",
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#2e3340")
    )
    
    estilo_cabecalho = ParagraphStyle(
        "LgpdHeader",
        parent=estilos["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=10,
        textColor=colors.white
    )

    elementos = []
    
    # Título e Meta
    elementos.append(Paragraph("Relatório de Portabilidade de Dados (LGPD)", titulo_estilo))
    data_geracao = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    elementos.append(Paragraph(f"<b>Data de Exportação:</b> {data_geracao}", texto_estilo))
    elementos.append(Paragraph("Este documento contém todas as informações pessoais e financeiras coletadas na plataforma em conformidade com o Art. 18 da Lei Geral de Proteção de Dados (LGPD).", texto_estilo))
    elementos.append(Spacer(1, 0.4 * cm))
    
    # Linha decorativa
    linha_decorativa = Table([[""]], colWidths=[doc.width], rowHeights=[2])
    linha_decorativa.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#0f3d3e")),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    elementos.append(linha_decorativa)
    elementos.append(Spacer(1, 0.4 * cm))
    
    # 1. DADOS CADASTRAIS DO PACIENTE
    elementos.append(Paragraph("1. Dados Cadastrais", h1_estilo))
    
    nasc = p.data_nascimento.strftime("%d/%m/%Y") if p.data_nascimento else "Não informada"
    ad = p.ativo_desde.strftime("%d/%m/%Y") if p.ativo_desde else "Não informada"
    
    dados_cadastrais = [
        [Paragraph("<b>Nome Completo:</b>", texto_estilo), Paragraph(p.nome, texto_estilo)],
        [Paragraph("<b>Telefone:</b>", texto_estilo), Paragraph(p.telefone, texto_estilo)],
        [Paragraph("<b>E-mail:</b>", texto_estilo), Paragraph(p.email or "—", texto_estilo)],
        [Paragraph("<b>Data Nascimento:</b>", texto_estilo), Paragraph(nasc, texto_estilo)],
        [Paragraph("<b>Tipo de Contrato:</b>", texto_estilo), Paragraph(p.tipo_contrato.value if p.tipo_contrato else "—", texto_estilo)],
        [Paragraph("<b>Frequência Padrão:</b>", texto_estilo), Paragraph(p.frequencia.value if p.frequencia else "—", texto_estilo)],
        [Paragraph("<b>Horário Atendimento:</b>", texto_estilo), Paragraph(p.horario_atendimento or "—", texto_estilo)],
        [Paragraph("<b>Ativo Desde:</b>", texto_estilo), Paragraph(ad, texto_estilo)],
        [Paragraph("<b>Status:</b>", texto_estilo), Paragraph(p.status.value, texto_bold_estilo)],
    ]
    
    t_cad = Table(dados_cadastrais, colWidths=[4 * cm, doc.width - 4 * cm])
    t_cad.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#ccd6d3")),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f4f7f6")),
        ("PADDING", (0, 0), (-1, -1), 5),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    elementos.append(t_cad)
    elementos.append(Spacer(1, 0.5 * cm))
    
    # 2. HISTÓRICO DE CONTRATOS
    elementos.append(Paragraph("2. Histórico de Vigência de Contratos", h1_estilo))
    if not contratos:
        elementos.append(Paragraph("Nenhum histórico de vigência de contrato registrado para este paciente.", texto_estilo))
    else:
        dados_contratos = [[
            Paragraph("Vigência De", estilo_cabecalho),
            Paragraph("Vigência Até", estilo_cabecalho),
            Paragraph("Frequência", estilo_cabecalho),
            Paragraph("Valor Sessão", estilo_cabecalho),
            Paragraph("Dias de Atendimento", estilo_cabecalho)
        ]]
        
        for c in contratos:
            ate_str = c.vigente_ate.strftime("%d/%m/%Y") if c.vigente_ate else "Vigente (Atual)"
            valor_br = f"R$ {float(c.valor_sessao):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            dados_contratos.append([
                Paragraph(c.vigente_de.strftime("%d/%m/%Y"), estilo_celula),
                Paragraph(ate_str, estilo_celula),
                Paragraph(c.frequencia.value, estilo_celula),
                Paragraph(valor_br, estilo_celula),
                Paragraph(c.dias_semana or "—", estilo_celula)
            ])
            
        t_cont = Table(dados_contratos, colWidths=[3 * cm, 3 * cm, 3 * cm, 3 * cm, doc.width - 12 * cm])
        t_cont.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#165a4c")),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#ccd6d3")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f4f7f6")]),
            ("PADDING", (0, 0), (-1, -1), 5),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))
        elementos.append(t_cont)
        
    elementos.append(Spacer(1, 0.5 * cm))
    
    # 3. HISTÓRICO DE SESSÕES
    elementos.append(Paragraph("3. Histórico de Agendamentos e Sessões", h1_estilo))
    if not sessoes:
        elementos.append(Paragraph("Nenhuma sessão registrada para este paciente.", texto_estilo))
    else:
        dados_sessoes = [[
            Paragraph("Data/Hora Início", estilo_cabecalho),
            Paragraph("Duração / Fim", estilo_cabecalho),
            Paragraph("Situação (Presença)", estilo_cabecalho),
            Paragraph("Pagamento", estilo_cabecalho),
            Paragraph("Valor Cobrado", estilo_cabecalho)
        ]]
        
        for s in sessoes:
            quando_ini = s.data_hora_inicio.strftime("%d/%m/%Y %H:%M")
            quando_fim = s.data_hora_fim.strftime("%H:%M")
            valor_br = f"R$ {float(s.valor_sessao):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") if s.valor_sessao is not None else "—"
            
            dados_sessoes.append([
                Paragraph(quando_ini, estilo_celula),
                Paragraph(f"Até {quando_fim}", estilo_celula),
                Paragraph(s.status_presenca.value, estilo_celula),
                Paragraph(s.status_pagamento.value, estilo_celula),
                Paragraph(valor_br, estilo_celula)
            ])
            
        t_sess = Table(dados_sessoes, colWidths=[4.5 * cm, 3.5 * cm, 4 * cm, 3.5 * cm, doc.width - 15.5 * cm])
        t_sess.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#165a4c")),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#ccd6d3")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f4f7f6")]),
            ("PADDING", (0, 0), (-1, -1), 4),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))
        elementos.append(t_sess)
        
    doc.build(elementos, canvasmaker=NumberedCanvas)
    return buf.getvalue()

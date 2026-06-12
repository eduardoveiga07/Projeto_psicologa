"""Gera PDF simples a partir de uma lista de dicionarios (tabela)."""
from io import BytesIO
from datetime import datetime
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfgen import canvas


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
        self.setStrokeColor(colors.HexColor("#dcdde1"))
        self.setLineWidth(0.5)
        self.line(1.5 * cm, 1.2 * cm, self._pagesize[0] - 1.5 * cm, 1.2 * cm)
        
        # --- CABEÇALHO COMPACTO (PÁGINA 2+) ---
        if self._pageNumber > 1:
            self.setFont("Helvetica-Bold", 8)
            self.setFillColor(colors.HexColor("#2e3340"))
            self.drawString(1.5 * cm, self._pagesize[1] - 1.0 * cm, "Consultório de Psicologia — Gestão Clínica")
            self.setFont("Helvetica", 8)
            self.setFillColor(colors.HexColor("#7f8c8d"))
            self.drawRightString(self._pagesize[0] - 1.5 * cm, self._pagesize[1] - 1.0 * cm, "Relatório Operacional")
            self.setStrokeColor(colors.HexColor("#dcdde1"))
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
    
    # Criar um estilo customizado para o título
    titulo_estilo = ParagraphStyle(
        "CustomTitle",
        parent=estilos["Title"],
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=22,
        textColor=colors.HexColor("#2e3340"),
        alignment=0,  # Alinhado à esquerda
        spaceAfter=15
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
    elementos.append(Spacer(1, 0.4 * cm))
    
    # 2. Seção de Filtros (se fornecidos)
    if filtros:
        filtros_estilo = ParagraphStyle(
            "FiltrosStyle",
            parent=estilos["Normal"],
            fontName="Helvetica",
            fontSize=8,
            leading=11,
            textColor=colors.HexColor("#2c3e50")
        )
        filtros_itens = []
        for k, v in filtros.items():
            filtros_itens.append(f"<b>{k}:</b> {v}")
        filtros_str = " | ".join(filtros_itens)
        
        # Box de filtros com fundo cinza claro
        t_filtros = Table([[Paragraph(f"🔍 <b>Filtros aplicados:</b> {filtros_str}", filtros_estilo)]], colWidths=[doc.width])
        t_filtros.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8f9fa")),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
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
        dados = [cols] + [[str(l.get(c, "")) for c in cols] for l in linhas]
        
        # Se totais for fornecido, adicionamos a linha de total
        if totais:
            linha_total = []
            for i, col in enumerate(cols):
                if i == 0:
                    linha_total.append("TOTAL")
                elif col in totais:
                    linha_total.append(str(totais[col]))
                else:
                    linha_total.append("")
            dados.append(linha_total)
            
        t = Table(dados, repeatRows=1)
        
        # Configurar estilos de tabela
        estilo_tabela = [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2e3340")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#dcdde1")),
            ("ROWBACKGROUNDS", (0, 1), (-1, (-2 if totais else -1)),
             [colors.white, colors.HexColor("#f8f9fa")]),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("PADDING", (0, 0), (-1, -1), 6),
        ]
        
        if totais:
            # Estilo especial para a linha de totais (última linha)
            estilo_tabela.extend([
                ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#eaeded")),
                ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                ("LINEABOVE", (0, -1), (-1, -1), 1, colors.HexColor("#2e3340")),
                ("PADDING", (0, -1), (-1, -1), 7),
            ])
            
        t.setStyle(TableStyle(estilo_tabela))
        elementos.append(t)
        
    # Construção do documento passando o NumberedCanvas customizado
    doc.build(elementos, canvasmaker=NumberedCanvas)
    return buf.getvalue()

"""Gera PDF simples a partir de uma lista de dicionarios (tabela)."""
from io import BytesIO
from datetime import datetime
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
from reportlab.lib.styles import getSampleStyleSheet


def gerar_pdf(titulo: str, linhas: list) -> bytes:
    """linhas: lista de dicts. Retorna bytes do PDF."""
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4),
                            topMargin=1.5 * cm, bottomMargin=1.5 * cm)
    estilos = getSampleStyleSheet()
    elementos = [Paragraph(titulo, estilos["Title"]),
                 Paragraph("Gerado em " +
                           datetime.now().strftime("%d/%m/%Y %H:%M"),
                           estilos["Normal"])]

    if not linhas:
        elementos.append(Paragraph("Sem registros.", estilos["Normal"]))
    else:
        cols = list(linhas[0].keys())
        dados = [cols] + [[str(l.get(c, "")) for c in cols] for l in linhas]
        t = Table(dados, repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2e3340")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1),
             [colors.white, colors.HexColor("#f0f0f0")]),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))
        elementos.append(t)

    doc.build(elementos)
    return buf.getvalue()

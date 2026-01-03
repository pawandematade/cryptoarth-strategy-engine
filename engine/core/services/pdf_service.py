"""
PDF Generation Service
Generates PDF reports for paper trades.
"""
import logging
from io import BytesIO
from typing import List
from datetime import datetime
from engine.models import StrategyExecution, PaperTrade, Strategy
from typing import List

logger = logging.getLogger(__name__)

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter, A4
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False
    logger.warning("reportlab not available - PDF generation will use placeholder")


def generate_paper_trade_pdf(execution: StrategyExecution, paper_trades: List[PaperTrade]) -> bytes:
    """
    Generate PDF report for paper trades.
    
    PDF includes:
    - Strategy name
    - Execution mode
    - Trade table
    - Total PnL
    - Date range
    
    Args:
        execution: Strategy execution record
        paper_trades: List of paper trades
    
    Returns:
        bytes: PDF file content
    """
    if not REPORTLAB_AVAILABLE:
        # Return placeholder PDF
        logger.warning("reportlab not available - returning placeholder PDF")
        return b"%PDF-1.4\n%PDF placeholder - install reportlab for full PDF generation"
    
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    story = []
    styles = getSampleStyleSheet()
    
    # Title
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=18,
        textColor=colors.HexColor('#1a1a1a'),
        spaceAfter=30
    )
    story.append(Paragraph("Paper Trade Report", title_style))
    story.append(Spacer(1, 0.2*inch))
    
    # Strategy Info
    execution_mode_str = execution.execution_mode.value if hasattr(execution.execution_mode, 'value') else str(execution.execution_mode)
    info_data = [
        ['Strategy Name:', execution.strategy_name or 'N/A'],
        ['Strategy Code:', execution.strategy_code or 'N/A'],
        ['Execution Mode:', execution_mode_str.upper()],
        ['Total PnL:', f"${execution.pnl or '0.0'}"],
        ['Total Trades:', str(execution.trades or 0)],
        ['Created At:', execution.created_at.strftime('%Y-%m-%d %H:%M:%S UTC') if execution.created_at else 'N/A']
    ]
    
    info_table = Table(info_data, colWidths=[2*inch, 4*inch])
    info_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
        ('TOPPADDING', (0, 0), (-1, -1), 12),
        ('GRID', (0, 0), (-1, -1), 1, colors.grey)
    ]))
    story.append(info_table)
    story.append(Spacer(1, 0.3*inch))
    
    # Trade Table
    if paper_trades:
        story.append(Paragraph("Trade History", styles['Heading2']))
        story.append(Spacer(1, 0.1*inch))
        
        # Table headers
        trade_data = [['Date', 'Symbol', 'Side', 'Lot Size', 'Entry', 'Exit', 'PnL']]
        
        # Add trades
        for trade in paper_trades:
            trade_date = trade.created_at.strftime('%Y-%m-%d %H:%M') if trade.created_at else 'N/A'
            entry = trade.entry_price or 'N/A'
            exit_price = trade.exit_price or 'Open'
            pnl_color = colors.green if float(trade.pnl or 0) >= 0 else colors.red
            
            trade_data.append([
                trade_date,
                trade.symbol,
                trade.side,
                trade.lot_size,
                entry,
                exit_price,
                f"${trade.pnl or '0.0'}"
            ])
        
        trade_table = Table(trade_data, colWidths=[1*inch, 0.8*inch, 0.5*inch, 0.8*inch, 0.8*inch, 0.8*inch, 0.8*inch])
        trade_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('TEXTCOLOR', (6, 1), (6, -1), colors.black),  # PnL column
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('GRID', (0, 0), (-1, -1), 1, colors.grey),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.lightgrey])
        ]))
        story.append(trade_table)
    else:
        story.append(Paragraph("No trades recorded", styles['Normal']))
    
    # Build PDF
    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()


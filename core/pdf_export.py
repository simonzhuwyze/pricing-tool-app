"""
PDF Export Engine for Wyze Pricing Tool.
Generates professional pricing analysis reports using fpdf2.
Landscape A4 format for wide CPAM tables.
"""

import io
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional, List
from fpdf import FPDF


# Brand colors (RGB)
BRAND_TEAL = (13, 138, 123)
BRAND_DARK = (38, 39, 48)
HEADER_BG = (240, 242, 246)
CPAM_BG = (213, 245, 240)
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
GRAY = (102, 102, 102)
LIGHT_GRAY = (200, 200, 200)


@dataclass
class ExportConfig:
    """All data needed for PDF export."""
    # Product info
    sku: str = ""
    product_name: str = ""
    reference_sku: str = ""
    product_group: str = ""
    product_line: str = ""

    # User inputs
    msrp: float = 0.0
    fob: float = 0.0
    tariff_rate: float = 0.0
    promotion_mix: float = 0.0
    promo_percentage: float = 0.0

    # View mode
    view_mode: str = "Blended"

    # Section toggles
    include_summary: bool = True
    include_waterfall: bool = True
    include_channel_mix: bool = True
    include_sensitivity: bool = False
    include_assumptions: bool = False

    # Data: list of dicts (rows) with string-formatted values
    summary_rows: list = field(default_factory=list)
    summary_columns: list = field(default_factory=list)

    waterfall_rows: list = field(default_factory=list)
    waterfall_columns: list = field(default_factory=list)
    waterfall_levels: list = field(default_factory=list)

    channel_mix_rows: list = field(default_factory=list)

    sensitivity_msrp_rows: list = field(default_factory=list)
    sensitivity_fob_rows: list = field(default_factory=list)

    assumptions_static_rows: list = field(default_factory=list)
    assumptions_log_rows: list = field(default_factory=list)
    assumptions_log_columns: list = field(default_factory=list)

    # Metadata
    generated_by: str = "local_user"
    generated_at: Optional[datetime] = None


class PricingReportPDF(FPDF):
    """Custom FPDF with Wyze branding."""

    def __init__(self):
        super().__init__(orientation="L", unit="mm", format="A4")
        self.set_auto_page_break(auto=True, margin=15)
        self._report_title = "Wyze Pricing Analysis Report"
        self._sku_line = ""

    def header(self):
        # Teal top bar
        self.set_fill_color(*BRAND_TEAL)
        self.rect(0, 0, self.w, 6, "F")
        # Header text
        self.set_y(8)
        self.set_font("Helvetica", "I", 7)
        self.set_text_color(*GRAY)
        self.cell(0, 4, self._sku_line, align="L")
        self.cell(0, 4, self._report_title, align="R", ln=True)
        self.ln(2)

    def footer(self):
        self.set_y(-10)
        self.set_font("Helvetica", "I", 7)
        self.set_text_color(*GRAY)
        self.cell(0, 5, f"Page {self.page_no()}/{{nb}}", align="C")

    def section_title(self, title: str):
        """Render a section title."""
        self.set_font("Helvetica", "B", 13)
        self.set_text_color(*BRAND_TEAL)
        self.cell(0, 8, title, ln=True)
        self.set_draw_color(*BRAND_TEAL)
        self.line(self.get_x(), self.get_y(), self.get_x() + 50, self.get_y())
        self.ln(3)
        self.set_text_color(*BLACK)

    def info_row(self, label: str, value: str, label_w: float = 40):
        """Render a label: value row."""
        self.set_font("Helvetica", "B", 8)
        self.cell(label_w, 5, label, align="R")
        self.set_font("Helvetica", "", 8)
        self.cell(60, 5, f"  {value}", ln=True)

    def data_table(self, columns: list, rows: list, col_widths: list = None,
                   row_levels: list = None, font_size: int = 7):
        """Render a formatted table."""
        n_cols = len(columns)
        usable_w = self.w - 20  # 10mm margins each side

        if col_widths is None:
            first_w = min(55, usable_w * 0.25)
            rest_w = (usable_w - first_w) / max(n_cols - 1, 1)
            col_widths = [first_w] + [rest_w] * (n_cols - 1)

        # Clamp total width
        total_w = sum(col_widths)
        if total_w > usable_w:
            scale = usable_w / total_w
            col_widths = [w * scale for w in col_widths]

        row_h = max(4.5, font_size * 0.7)

        # Header row
        self.set_font("Helvetica", "B", font_size)
        self.set_fill_color(*BRAND_TEAL)
        self.set_text_color(*WHITE)
        self.set_draw_color(*LIGHT_GRAY)
        for i, col in enumerate(columns):
            align = "L" if i == 0 else "C"
            self.cell(col_widths[i], row_h + 1, str(col), border=1, fill=True, align=align)
        self.ln()

        # Data rows
        for row_idx, row in enumerate(rows):
            level = row_levels[row_idx] if row_levels and row_idx < len(row_levels) else "L2"

            # Check if we need a new page
            if self.get_y() + row_h > self.h - 15:
                self.add_page()
                # Re-render header
                self.set_font("Helvetica", "B", font_size)
                self.set_fill_color(*BRAND_TEAL)
                self.set_text_color(*WHITE)
                for i, col in enumerate(columns):
                    align = "L" if i == 0 else "C"
                    self.cell(col_widths[i], row_h + 1, str(col), border=1, fill=True, align=align)
                self.ln()

            # Row styling
            fill = False
            if level == "L1":
                self.set_font("Helvetica", "B", font_size)
                self.set_text_color(*BLACK)
                self.set_fill_color(*HEADER_BG)
                fill = True
            elif level == "CPAM":
                self.set_font("Helvetica", "B", font_size)
                self.set_text_color(*BRAND_TEAL)
                self.set_fill_color(*CPAM_BG)
                fill = True
            elif level == "L3":
                self.set_font("Helvetica", "", max(font_size - 1, 5))
                self.set_text_color(*GRAY)
            else:  # L2
                self.set_font("Helvetica", "", font_size)
                self.set_text_color(*BLACK)

            for i, val in enumerate(row):
                align = "L" if i == 0 else "R"
                self.cell(col_widths[i], row_h, str(val), border=1, fill=fill, align=align)
            self.ln()
            self.set_text_color(*BLACK)


def generate_pricing_report(config: ExportConfig) -> bytes:
    """Generate complete pricing PDF. Returns bytes for st.download_button."""
    pdf = PricingReportPDF()
    pdf.alias_nb_pages()
    pdf._sku_line = f"{config.sku} - {config.product_name}"

    # Cover
    _render_cover(pdf, config)

    # Selected sections
    if config.include_summary and config.summary_rows:
        _render_summary(pdf, config)

    if config.include_waterfall and config.waterfall_rows:
        _render_waterfall(pdf, config)

    if config.include_channel_mix and config.channel_mix_rows:
        _render_channel_mix(pdf, config)

    if config.include_sensitivity and (config.sensitivity_msrp_rows or config.sensitivity_fob_rows):
        _render_sensitivity(pdf, config)

    if config.include_assumptions and config.assumptions_static_rows:
        _render_assumptions(pdf, config)

    buf = io.BytesIO()
    pdf.output(buf)
    return buf.getvalue()


def _render_cover(pdf: PricingReportPDF, config: ExportConfig):
    """Render cover page with product info and inputs."""
    pdf.add_page()

    # Title
    pdf.ln(8)
    pdf.set_font("Helvetica", "B", 24)
    pdf.set_text_color(*BRAND_TEAL)
    pdf.cell(0, 12, "Wyze Pricing Analysis Report", ln=True, align="C")

    pdf.set_font("Helvetica", "", 14)
    pdf.set_text_color(*BRAND_DARK)
    pdf.cell(0, 8, f"{config.product_name} ({config.sku})", ln=True, align="C")
    pdf.ln(8)

    # Two-column info layout
    pdf.set_text_color(*BLACK)
    x_start = 60

    pdf.set_x(x_start)
    pdf.info_row("SKU:", config.sku)
    pdf.set_x(x_start)
    pdf.info_row("Product Name:", config.product_name)
    pdf.set_x(x_start)
    pdf.info_row("Reference SKU:", config.reference_sku or "N/A")
    pdf.set_x(x_start)
    pdf.info_row("Product Group:", config.product_group or "N/A")
    pdf.set_x(x_start)
    pdf.info_row("Product Line:", config.product_line or "N/A")
    pdf.ln(3)

    pdf.set_x(x_start)
    pdf.info_row("MSRP:", f"${config.msrp:.2f}")
    pdf.set_x(x_start)
    pdf.info_row("FOB:", f"${config.fob:.2f}")
    pdf.set_x(x_start)
    pdf.info_row("Tariff Rate:", f"{config.tariff_rate:.1f}%")
    pdf.set_x(x_start)
    pdf.info_row("Promo Mix:", f"{config.promotion_mix:.0f}%")
    pdf.set_x(x_start)
    pdf.info_row("Promo %:", f"{config.promo_percentage:.0f}%")
    pdf.set_x(x_start)
    pdf.info_row("View Mode:", config.view_mode)
    pdf.ln(3)

    gen_at = (config.generated_at or datetime.now()).strftime("%Y-%m-%d %H:%M")
    pdf.set_x(x_start)
    pdf.info_row("Generated:", gen_at)
    pdf.set_x(x_start)
    pdf.info_row("Generated By:", config.generated_by)

    # Sections included
    pdf.ln(8)
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(0, 5, "Sections Included:", ln=True, align="C")
    pdf.set_font("Helvetica", "", 8)
    sections = []
    if config.include_summary:
        sections.append("CPAM Summary")
    if config.include_waterfall:
        sections.append("CPAM Waterfall")
    if config.include_channel_mix:
        sections.append("Channel Mix")
    if config.include_sensitivity:
        sections.append("Sensitivity Analysis")
    if config.include_assumptions:
        sections.append("Assumptions Detail")
    pdf.cell(0, 5, " | ".join(sections), ln=True, align="C")


def _render_summary(pdf: PricingReportPDF, config: ExportConfig):
    """Render CPAM summary table."""
    pdf.add_page()
    pdf.section_title(f"CPAM Summary ({config.view_mode})")

    cols = config.summary_columns
    rows = []
    levels = []
    for row_dict in config.summary_rows:
        row_vals = [row_dict.get(c, "") for c in cols]
        rows.append(row_vals)
        # Weighted Avg row gets CPAM-level styling
        if row_dict.get(cols[0], "") == "Weighted Avg":
            levels.append("CPAM")
        else:
            levels.append("L2")

    pdf.data_table(cols, rows, row_levels=levels)


def _render_waterfall(pdf: PricingReportPDF, config: ExportConfig):
    """Render CPAM waterfall breakdown."""
    pdf.add_page()
    pdf.section_title(f"CPAM Waterfall Breakdown ({config.view_mode})")

    cols = config.waterfall_columns
    rows = []
    for row_dict in config.waterfall_rows:
        row_vals = [row_dict.get(c, "") for c in cols]
        rows.append(row_vals)

    # Determine font size based on column count
    n_cols = len(cols)
    if n_cols > 10:
        font_size = 5
    elif n_cols > 6:
        font_size = 6
    else:
        font_size = 7

    pdf.data_table(cols, rows, row_levels=config.waterfall_levels, font_size=font_size)


def _render_channel_mix(pdf: PricingReportPDF, config: ExportConfig):
    """Render channel mix table."""
    pdf.add_page()
    pdf.section_title("Channel Mix")

    cols = ["Channel", "Mix %"]
    rows = []
    total = 0.0
    for item in config.channel_mix_rows:
        ch = item.get("channel", "")
        pct = item.get("mix_pct", 0.0)
        rows.append([ch, f"{pct:.1f}%" if pct > 0 else "-"])
        total += pct

    rows.append(["Total", f"{total:.1f}%"])
    levels = ["L2"] * (len(rows) - 1) + ["L1"]

    col_widths = [80, 40]
    pdf.data_table(cols, rows, col_widths=col_widths, row_levels=levels)


def _render_sensitivity(pdf: PricingReportPDF, config: ExportConfig):
    """Render sensitivity analysis tables."""
    pdf.add_page()
    pdf.section_title("Sensitivity Analysis")

    if config.sensitivity_msrp_rows:
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(0, 7, "MSRP Sensitivity", ln=True)
        pdf.ln(1)
        cols = ["MSRP", "CPAM $"]
        rows = []
        for item in config.sensitivity_msrp_rows:
            rows.append([item.get("msrp", ""), item.get("cpam", "")])
        pdf.data_table(cols, rows, col_widths=[60, 60])
        pdf.ln(5)

    if config.sensitivity_fob_rows:
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(0, 7, "FOB Sensitivity", ln=True)
        pdf.ln(1)
        cols = ["FOB", "CPAM $"]
        rows = []
        for item in config.sensitivity_fob_rows:
            rows.append([item.get("fob", ""), item.get("cpam", "")])
        pdf.data_table(cols, rows, col_widths=[60, 60])


def _render_assumptions(pdf: PricingReportPDF, config: ExportConfig):
    """Render assumptions section."""
    pdf.add_page()
    pdf.section_title("Assumptions Detail")

    # Static assumptions
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 7, "Static Cost Assumptions", ln=True)
    pdf.ln(1)
    cols = ["Item", "Value", "Unit"]
    rows = [[d.get("item", ""), d.get("value", ""), d.get("unit", "")]
            for d in config.assumptions_static_rows]
    pdf.data_table(cols, rows, col_widths=[60, 40, 50])
    pdf.ln(5)

    # Resolution log
    if config.assumptions_log_rows:
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(0, 7, "All Resolved Assumptions", ln=True)
        pdf.ln(1)
        log_cols = config.assumptions_log_columns or ["Channel", "Field", "Value", "Source"]
        rows = []
        for item in config.assumptions_log_rows:
            rows.append([item.get(c, "") for c in log_cols])
        pdf.data_table(log_cols, rows, font_size=6)

# Databricks notebook source
# DBTITLE 1,PPTX Generator
# MAGIC %md
# MAGIC # Agent 02 — PPTX Generator (W3)
# MAGIC
# MAGIC **Purpose:** Converts business case content into a professional PowerPoint deck using python-pptx. Follows Hologic brand guidelines.
# MAGIC
# MAGIC | Field | Value |
# MAGIC |---|---|
# MAGIC | Layer | EXECUTION |
# MAGIC | Workspace | W3 (Business Champions) |
# MAGIC | Inputs | BUSINESS_CASE dict from 01_business_case_builder |
# MAGIC | Outputs | .pptx file saved to outputs folder |

# COMMAND ----------

# DBTITLE 1,Load config
# MAGIC %run ./00_bc_config

# COMMAND ----------

# DBTITLE 1,STEP 1: Build PPTX
# ======================================================================
# STEP 1 — BUILD POWERPOINT DECK
# Uses python-pptx to create a branded presentation
# ======================================================================

from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR

AGENT_NAME = "02_pptx_generator"

# Get business case data
try:
    bc = BUSINESS_CASE
except NameError:
    bc = {"name": "Sample Project", "audience": "board",
          "financials": {"base": {"npv_3yr": 250000, "roi_pct": 340, "payback_months": 5.0, "investment": 75000, "annual_benefit": 180000}},
          "content": "# Executive Summary\nSample content for testing."}

prs = Presentation()
prs.slide_width = Inches(13.333)
prs.slide_height = Inches(7.5)

def add_title_slide(prs, title, subtitle):
    """Add a branded title slide."""
    slide = prs.slides.add_slide(prs.slide_layouts[6])  # Blank
    # Background
    bg = slide.background.fill
    bg.solid()
    bg.fore_color.rgb = RGBColor(0x1B, 0x2A, 0x4A)
    # Title
    txBox = slide.shapes.add_textbox(Inches(1), Inches(2.5), Inches(11), Inches(2))
    tf = txBox.text_frame
    p = tf.paragraphs[0]
    p.text = title
    p.font.size = Pt(40)
    p.font.bold = True
    p.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
    p.alignment = PP_ALIGN.CENTER
    # Subtitle
    p2 = tf.add_paragraph()
    p2.text = subtitle
    p2.font.size = Pt(18)
    p2.font.color.rgb = RGBColor(0x16, 0xA0, 0x85)
    p2.alignment = PP_ALIGN.CENTER
    return slide

def add_content_slide(prs, title, content, kpi_boxes=None):
    """Add a content slide with optional KPI boxes."""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    # Title bar
    title_box = slide.shapes.add_textbox(Inches(0.5), Inches(0.3), Inches(12), Inches(0.8))
    tf = title_box.text_frame
    p = tf.paragraphs[0]
    p.text = title
    p.font.size = Pt(28)
    p.font.bold = True
    p.font.color.rgb = RGBColor(0x1B, 0x2A, 0x4A)
    # Content
    content_box = slide.shapes.add_textbox(Inches(0.5), Inches(1.3), Inches(12), Inches(5.5))
    tf2 = content_box.text_frame
    tf2.word_wrap = True
    for line in content.split('\n')[:20]:  # Cap at 20 lines per slide
        p = tf2.add_paragraph()
        p.text = line.strip('# ').strip('- ')
        p.font.size = Pt(14)
        p.space_after = Pt(6)
    return slide

def add_kpi_slide(prs, title, kpis):
    """Add a slide with KPI metric boxes."""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    # Title
    title_box = slide.shapes.add_textbox(Inches(0.5), Inches(0.3), Inches(12), Inches(0.8))
    tf = title_box.text_frame
    tf.paragraphs[0].text = title
    tf.paragraphs[0].font.size = Pt(28)
    tf.paragraphs[0].font.bold = True
    tf.paragraphs[0].font.color.rgb = RGBColor(0x1B, 0x2A, 0x4A)
    # KPI boxes
    box_width = Inches(3)
    box_height = Inches(2)
    start_x = Inches(0.8)
    start_y = Inches(2)
    colors = [RGBColor(0x27, 0xAE, 0x60), RGBColor(0x34, 0x98, 0xDB), RGBColor(0x8E, 0x44, 0xAD), RGBColor(0xF3, 0x9C, 0x12)]
    
    for i, (label, value) in enumerate(kpis[:4]):
        x = start_x + (i * Inches(3.1))
        shape = slide.shapes.add_shape(1, x, start_y, box_width, box_height)  # Rectangle
        shape.fill.solid()
        shape.fill.fore_color.rgb = colors[i % len(colors)]
        shape.line.fill.background()
        # Value
        tf = shape.text_frame
        tf.vertical_anchor = MSO_ANCHOR.MIDDLE
        p = tf.paragraphs[0]
        p.text = str(value)
        p.font.size = Pt(32)
        p.font.bold = True
        p.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        p.alignment = PP_ALIGN.CENTER
        # Label
        p2 = tf.add_paragraph()
        p2.text = label
        p2.font.size = Pt(12)
        p2.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        p2.alignment = PP_ALIGN.CENTER
    return slide

# Build the deck
financials = bc['financials']['base']

add_title_slide(prs, bc['name'], f"Business Case | {datetime.now().strftime('%B %Y')}")

add_kpi_slide(prs, "Financial Impact", [
    ("3-Year NPV", f"${financials['npv_3yr']:,.0f}"),
    ("ROI", f"{financials['roi_pct']:.0f}%"),
    ("Payback", f"{financials['payback_months']:.1f} mo"),
    ("Annual Benefit", f"${financials['annual_benefit']:,.0f}"),
])

# Split business case content into slides by section headers
sections = bc['content'].split('## ') if '## ' in bc['content'] else bc['content'].split('# ')
for section in sections[1:8]:  # Skip empty first, cap at 7 content slides
    lines = section.strip().split('\n')
    title = lines[0].strip()
    content = '\n'.join(lines[1:]).strip()
    add_content_slide(prs, title, content)

# Save
output_file = f"/tmp/{bc['name'].replace(' ', '_')}_Business_Case.pptx"
prs.save(output_file)

print(f"\u2705 PPTX generated: {output_file}")
print(f"   Slides: {len(prs.slides)}")
print(f"   Project: {bc['name']}")
print(f"   Audience: {bc.get('audience', 'board').upper()}")
"""
styles.py - CSS styles for Streamlit pages

Utils:
- VALIDATE_PAGE_STYLES: CSS for two-pane validation interface with 80vh scrollable containers
"""

VALIDATE_PAGE_STYLES = """
<style>
    .small-font {
        font-size: 11px;
        font-family: monospace;
        white-space: pre-wrap;
        line-height: 1.3;
    }
    .doc-container {
        height: 80vh;
        overflow-y: auto;
        padding: 10px;
        background-color: #f8f9fa;
        border-radius: 5px;
    }
    .validation-container {
        height: 80vh;
        overflow-y: auto;
        padding: 10px;
    }
    .stExpander {
        margin-bottom: 0.5rem;
        border: 1px solid #e0e0e0;
    }
    .stRadio > div {
        margin-top: 0;
        margin-bottom: 0.3rem;
    }
    .stCheckbox {
        margin-top: 0;
        margin-bottom: 0;
    }
    .stMarkdown {
        margin-bottom: 0.3rem;
    }
    h3 {
        font-size: 1.1rem;
        margin-top: 0.5rem;
        margin-bottom: 0.3rem;
    }
    .mesa-row {
        display: flex;
        gap: 8px;
        padding: 4px 2px;
        font-size: 0.86rem;
        align-items: baseline;
        border-bottom: 1px solid #eceef1;
    }
    .mesa-label {
        /* all rows now share the same [6,1] column geometry, so a percentage
           basis aligns values consistently without crushing them when nested */
        flex: 0 0 42%;
        font-weight: 600;
        color: #57606a;
        word-break: break-word;
    }
    .mesa-value {
        flex: 1;
        word-break: break-word;
    }
    .mesa-null {
        color: #999;
        font-style: italic;
    }
    .mesa-nested-label {
        font-weight: 700;
        color: #24292f;
        font-size: 0.88rem;
        margin: 8px 0 2px;
    }
    /* tighten vertical spacing between field rows inside entity cards */
    div[data-testid="stVerticalBlock"]:has(> div[data-testid="stHorizontalBlock"] .mesa-row) {
        gap: 0.1rem;
    }
    /* keep the locate button on the same baseline as its row, compact */
    div[data-testid="stHorizontalBlock"]:has(.mesa-row) {
        gap: 0.3rem;
        align-items: center;
    }
    div[data-testid="stHorizontalBlock"]:has(.mesa-row) .stButton > button {
        padding: 0 0.35rem;
        min-height: 1.6rem;
        line-height: 1.4rem;
    }
    /* grouped Validate page: ✓/✗ toggle rows (leaf fields + per-list-item rows) --
       compact icon buttons and a tight vertical rhythm between rows. */
    div[data-testid="stHorizontalBlock"]:has(.mesa-toggle-row) {
        gap: 0.3rem;
        align-items: center;
        margin-bottom: 0.05rem;
    }
    div[data-testid="stHorizontalBlock"]:has(.mesa-toggle-row) div[data-testid="column"] button {
        padding: 0 0.4rem;
        min-height: 1.6rem;
        line-height: 1.4rem;
        font-size: 0.95rem;
    }
</style>
"""

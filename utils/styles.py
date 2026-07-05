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
    .mesa-card {
        border: 1px solid #dfe3e8;
        border-radius: 6px;
        padding: 8px 12px;
        margin-bottom: 6px;
        background-color: #fbfcfd;
    }
    .mesa-row {
        display: flex;
        gap: 8px;
        padding: 2px 0;
        border-bottom: 1px solid #f0f2f4;
        font-size: 0.88rem;
    }
    .mesa-row:last-child {
        border-bottom: none;
    }
    .mesa-label {
        flex: 0 0 40%;
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
</style>
"""

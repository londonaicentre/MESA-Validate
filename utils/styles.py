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
</style>
"""

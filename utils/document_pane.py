"""
document_pane.py - Document text pane with highlight + scroll

Renders the source document inside an iframe (streamlit component) that
embeds the shared textmatch.js, so jump-to-source highlighting behaves
identically to the clinician HTML packets. Includes a "Reflow spaces" toggle
that turns runs of 3+ spaces (a data-warehouse export artefact) into line
breaks; the toggle state persists in localStorage across Streamlit reruns.
"""

import json
from pathlib import Path

import streamlit.components.v1 as components

TEXTMATCH_JS = (Path(__file__).parent / "textmatch.js").read_text(encoding="utf-8")


def render_document_pane(content, highlight_query=None, height=800):
    doc_json = json.dumps(content).replace("<", "\\u003c")
    query_json = json.dumps(highlight_query or "").replace("<", "\\u003c")
    page = f"""
<style>
  body {{ margin: 0; font-family: "Source Sans Pro", -apple-system, sans-serif; }}
  #toolbar {{ display: flex; justify-content: flex-end; margin-bottom: 6px; }}
  #toolbar label {{ font-size: 0.82rem; color: #57606a; display: flex;
                   align-items: center; gap: 4px; cursor: pointer; }}
  #doc {{ white-space: pre-wrap; word-wrap: break-word; padding: 10px;
         background: #f5f5f5; border: 1px solid #ddd; border-radius: 5px;
         font-size: 0.95rem; line-height: 1.5; }}
  mark {{ background: #ffd54d; padding: 0 1px; }}
  mark.active {{ background: #ff9800; }}
  mark.fuzzy {{ text-decoration: underline dashed #b26a00; }}
  #notfound {{ background: #fff3cd; border: 1px solid #ffe08a; padding: 6px 10px;
               border-radius: 4px; margin-bottom: 8px; font-size: 0.85rem; }}
</style>
<div id="toolbar">
  <label title="Insert a line break wherever the document has 3 or more spaces in a row">
    <input type="checkbox" id="reflow-check"> Reflow spaces
  </label>
</div>
<div id="banner"></div>
<div id="doc"></div>
<script>{TEXTMATCH_JS}</script>
<script>
  const rawText = {doc_json};
  const query = {query_json};
  const docEl = document.getElementById("doc");
  const banner = document.getElementById("banner");
  const reflowCheck = document.getElementById("reflow-check");

  let reflow = false;
  try {{ reflow = localStorage.getItem("mesa-reflow") === "1"; }} catch (e) {{}}
  reflowCheck.checked = reflow;

  function currentDocText() {{
    return reflow ? rawText.replace(/ {{3,}}/g, "\\n") : rawText;
  }}

  function render() {{
    const docText = currentDocText();
    docEl.innerHTML = "";
    banner.innerHTML = "";
    if (!query) {{
      docEl.textContent = docText;
      return;
    }}
    const m = TextMatch.findMatches(docText, query);
    if (!m.ranges.length) {{
      docEl.textContent = docText;
      banner.innerHTML = '<div id="notfound">Text not found verbatim in document</div>';
      return;
    }}
    let cursor = 0;
    m.ranges.forEach((r, i) => {{
      docEl.appendChild(document.createTextNode(docText.slice(cursor, r.start)));
      const mark = document.createElement("mark");
      if (i === 0) mark.className = "active";
      if (m.strategy === "fuzzy") {{
        mark.classList.add("fuzzy");
        mark.title = "approximate match";
      }}
      mark.textContent = docText.slice(r.start, r.end);
      docEl.appendChild(mark);
      cursor = r.end;
    }});
    docEl.appendChild(document.createTextNode(docText.slice(cursor)));
    const first = docEl.querySelector("mark");
    if (first) first.scrollIntoView({{ block: "center" }});
  }}

  reflowCheck.addEventListener("change", (e) => {{
    reflow = e.target.checked;
    try {{ localStorage.setItem("mesa-reflow", reflow ? "1" : "0"); }} catch (err) {{}}
    render();
  }});

  render();
</script>
"""
    components.html(page, height=height, scrolling=True)

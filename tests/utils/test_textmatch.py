import json
import shutil
import subprocess
from pathlib import Path

import pytest

NODE = shutil.which("node")
JS = Path("utils/textmatch.js").resolve()


def run_match(doc, query):
    script = (
        f"require({json.dumps(str(JS))});"
        "const r = globalThis.TextMatch.findMatches("
        f"{json.dumps(doc)}, {json.dumps(query)});"
        "console.log(JSON.stringify(r));"
    )
    out = subprocess.run(
        [NODE, "-e", script], capture_output=True, text=True, check=True
    )
    return json.loads(out.stdout)


@pytest.mark.skipif(NODE is None, reason="node not installed")
class TestFindMatches:
    def test_exact_match(self):
        r = run_match(
            "The post-operative recovery was slow.", "The post-operative recovery"
        )
        assert r["strategy"] == "exact"
        assert r["ranges"] == [{"start": 0, "end": 27}]

    def test_case_insensitive(self):
        assert run_match("KIT exon 11 mutation", "kit exon 11")["strategy"] == "exact"

    def test_multiple_occurrences(self):
        r = run_match("ileus. Later, another ileus.", "ileus")
        assert r["strategy"] == "exact"
        assert len(r["ranges"]) == 2

    def test_whitespace_normalized(self):
        r = run_match(
            "recovery was\n   complicated by ileus", "recovery was complicated"
        )
        assert r["strategy"] == "normalized"
        assert len(r["ranges"]) == 1

    def test_fuzzy(self):
        r = run_match(
            "The patient was discharged on post-operative day 8 after an ileus.",
            "discharged post-operative day eight ileus",
        )
        assert r["strategy"] == "fuzzy"

    def test_no_match(self):
        r = run_match(
            "Cardiology consultation note.", "pancreatic adenocarcinoma metastasis"
        )
        assert r == {"strategy": None, "ranges": []}

    def test_empty_query(self):
        assert run_match("Some document", "")["strategy"] is None

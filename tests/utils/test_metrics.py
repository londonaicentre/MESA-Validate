import pytest

from utils.metrics import aggregate_metrics
from utils.models import FieldSelection
from utils.schema_inspector import SchemaInspector


@pytest.fixture(scope="module")
def inspector():
    return SchemaInspector("oncollamaschemav3", "OncoLlamaModel")


def test_aggregate_metrics_uses_path_keys(inspector):
    selections = [
        FieldSelection(selection_type="basemodel_field",
                       class_name="PrimaryCancerFacts", field_name="topography"),
    ]
    progress = {
        "completed_files": ["doc1", "doc2"],
        "results": {
            "doc1": {"primary_cancer.primary_cancer_facts.topography": "PRESENT_CORRECT"},
            "doc2": {"primary_cancer.primary_cancer_facts.topography": "PRESENT_INCORRECT"},
        },
    }
    metrics = aggregate_metrics(progress, selections, inspector)
    key = "primary_cancer.primary_cancer_facts.topography"
    assert key in metrics
    assert metrics[key]["type"] == "binary"
    assert metrics[key]["tp"] == 1
    assert metrics[key]["fp"] == 1
    assert metrics[key]["target"].title == "PrimaryCancerFacts.topography"

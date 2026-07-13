"""
metrics.py - Metrics calculation for validation results
"""

import csv
from io import StringIO

from utils.validation_plan import build_validation_plan, flatten_targets


def calculate_binary_accuracy(results):
    """
    Calculate precision, recall, F1, and accuracy for binary validation results

    Args:
        results:
            List of "PRESENT_CORRECT" | "ABSENT_CORRECT" | "PRESENT_INCORRECT" | "ABSENT_INCORRECT" | "NOT_APPLICABLE" strings

    Returns:
        Dict with metrics results
    """
    if not results:
        return {
            "precision": 0.0,
            "recall": 0.0,
            "f1": 0.0,
            "accuracy": 0.0,
            "tp": 0,
            "tn": 0,
            "fp": 0,
            "fn": 0,
            "not_applicable": 0,
            "total": 0,
        }

    tp = sum(1 for r in results if r == "PRESENT_CORRECT")
    tn = sum(1 for r in results if r == "ABSENT_CORRECT")
    fp = sum(1 for r in results if r == "PRESENT_INCORRECT")
    fn = sum(1 for r in results if r == "ABSENT_INCORRECT")
    not_applicable = sum(1 for r in results if r == "NOT_APPLICABLE")

    if tp + fp == 0:
        precision = 0.0
    else:
        precision = tp / (tp + fp)

    if tp + fn == 0:
        recall = 0.0
    else:
        recall = tp / (tp + fn)

    if precision + recall == 0:
        f1 = 0.0
    else:
        f1 = 2 * (precision * recall) / (precision + recall)

    # exclude where not_applicable
    applicable = tp + tn + fp + fn
    if applicable == 0:
        accuracy = 0.0
    else:
        accuracy = (tp + tn) / applicable

    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "accuracy": accuracy,
        "tp": tp,
        "tn": tn,
        "fp": fp,
        "fn": fn,
        "not_applicable": not_applicable,
        "total": len(results),
    }


def calculate_list_metrics(results):
    """
    Calculate precision, recall, F1 for list validation results.

    Args:
        results:
            List of dicts with 'items' (list of null/true/false) and 'missed' (int)
            null = not evaluated, true = correct, false = incorrect

    Returns:
        Dict with metrics results
    """
    if not results:
        return {
            "precision": 0.0,
            "recall": 0.0,
            "f1": 0.0,
            "total_items": 0,
            "correct_items": 0,
            "total_missed": 0,
        }

    total_items = 0
    correct_items = 0
    total_missed = 0

    for result in results:
        if isinstance(result, dict):
            items = result.get("items", [])
            missed = result.get("missed", 0)

            # only count evaluated items (not none/null)
            evaluated_items = [item for item in items if item is not None]
            total_items += len(evaluated_items)
            correct_items += sum(1 for item in evaluated_items if item is True)
            total_missed += missed

    if total_items == 0:
        precision = 0.0
    else:
        precision = correct_items / total_items

    total_expected = correct_items + total_missed
    if total_expected == 0:
        recall = 0.0
    else:
        recall = correct_items / total_expected

    if precision + recall == 0:
        f1 = 0.0
    else:
        f1 = 2 * (precision * recall) / (precision + recall)

    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "total_items": total_items,
        "correct_items": correct_items,
        "total_missed": total_missed,
    }


def aggregate_metrics(progress_data, selections, inspector):
    """
    Aggregate metrics across all files for each validation plan target.

    Args:
        progress_data:
            results Dict
        selections:
            List of FieldSelection objects
        inspector:
            SchemaInspector for the session's schema, used to build the
            validation plan (and thus the canonical target keys) that the
            selections resolve to.

    Returns:
        Dict mapping target keys to their metrics
    """
    metrics = {}

    completed_files = set(progress_data.get("completed_files", []))
    targets = flatten_targets(build_validation_plan(selections, inspector))

    for target in targets:
        results_for_target = [
            file_results[target.key]
            for file_path, file_results in progress_data.get("results", {}).items()
            if file_path in completed_files and target.key in file_results
        ]
        if not results_for_target:
            continue

        first = results_for_target[0]
        if isinstance(first, str):
            metrics[target.key] = {
                "type": "binary",
                "target": target,
                **calculate_binary_accuracy(results_for_target),
            }
        elif isinstance(first, dict):
            metrics[target.key] = {
                "type": "list",
                "target": target,
                **calculate_list_metrics(results_for_target),
            }

    return metrics


def _build_metrics_rows(metrics):
    """
    Build CSV rows from metrics dict
    """
    rows = []
    for key, metric_data in metrics.items():
        name = metric_data["target"].title

        row = {
            "selection": name,
            "type": metric_data["type"],
            "precision": metric_data["precision"],
            "recall": metric_data["recall"],
            "f1": metric_data["f1"],
        }

        if metric_data["type"] == "binary":
            row["accuracy"] = metric_data["accuracy"]
            row["tp"] = metric_data["tp"]
            row["tn"] = metric_data["tn"]
            row["fp"] = metric_data["fp"]
            row["fn"] = metric_data["fn"]
            row["not_applicable"] = metric_data["not_applicable"]
            row["total"] = metric_data["total"]
        else:
            row["correct_items"] = metric_data["correct_items"]
            row["total_items"] = metric_data["total_items"]
            row["missed"] = metric_data["total_missed"]

        rows.append(row)
    return rows


def export_to_csv(progress_data, selections, inspector, output_path):
    """
    Export summary metrics to CSV for download
    """
    metrics = aggregate_metrics(progress_data, selections, inspector)
    if not metrics:
        return

    rows = _build_metrics_rows(metrics)

    fieldnames = []
    seen = set()
    for row in rows:
        for key in row.keys():
            if key not in seen:
                fieldnames.append(key)
                seen.add(key)

    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def export_to_csv_string(progress_data, selections, inspector):
    """Export summary metrics to CSV string for download"""
    metrics = aggregate_metrics(progress_data, selections, inspector)
    if not metrics:
        return ""

    rows = _build_metrics_rows(metrics)
    if not rows:
        return ""

    fieldnames = []
    seen = set()
    for row in rows:
        for key in row.keys():
            if key not in seen:
                fieldnames.append(key)
                seen.add(key)

    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)

    return output.getvalue()


def format_metrics_summary(metrics):
    """
    Format metrics into readable summary

    Args:
        metrics:
            Dict from aggregate_metrics()

    Returns:
        List of dicts with formatted metrics for display
    """
    summary = []

    for key, metric_data in metrics.items():
        name = metric_data["target"].title

        if metric_data["type"] == "binary":
            summary.append(
                {
                    "selection": name,
                    "type": "Binary",
                    "precision": f"{metric_data['precision']:.1%}",
                    "recall": f"{metric_data['recall']:.1%}",
                    "f1": f"{metric_data['f1']:.3f}",
                    "accuracy": f"{metric_data['accuracy']:.1%}",
                    "tp": metric_data["tp"],
                    "tn": metric_data["tn"],
                    "fp": metric_data["fp"],
                    "fn": metric_data["fn"],
                    "not_applicable": metric_data["not_applicable"],
                    "total": metric_data["total"],
                }
            )
        else:  # list
            summary.append(
                {
                    "selection": name,
                    "type": "List",
                    "precision": f"{metric_data['precision']:.1%}",
                    "recall": f"{metric_data['recall']:.1%}",
                    "f1": f"{metric_data['f1']:.3f}",
                    "correct_items": metric_data["correct_items"],
                    "total_items": metric_data["total_items"],
                    "missed": metric_data["total_missed"],
                }
            )

    return summary

import json
import os
import sys
import numpy as np

from sklearn.metrics import (
    accuracy_score,
    precision_score,
    recall_score,
    f1_score,
    roc_auc_score,
    matthews_corrcoef,
    mean_squared_error,
    confusion_matrix
)


METRICS = {
    "accuracy": accuracy_score,
    "precision": precision_score,
    "recall": recall_score,
    "f1": f1_score,
    "roc_auc": roc_auc_score,
    "mcc": matthews_corrcoef,
    "mse": mean_squared_error
}

# the channels to the outer world
PRED_LABELS_FILE = "/data/pred_labels.json"
TRUE_LABELS_FILE = "/data/true_labels.json"
RESULT_FILE = "/data/result.json"
ENVVAR_NAME = "CMD"


def compute_metric(true_labels: np.ndarray, pred_labels: np.ndarray, metric: str) -> float:
    """Computes the selected evaluation metric.

    Args:
        true_labels (np.ndarray): Ground truth labels.
        pred_labels (np.ndarray): Predicted labels.
        metric (str): The metric to compute.

    Returns:
        float: Computed metric value.
    """
    # Compute confusion matrix components
    if metric in {"tp", "fp", "tn", "fn", "specificity", "balanced_accuracy"}:
        tn, fp, fn, tp = confusion_matrix(true_labels, pred_labels).ravel()
    if metric == "tp":
        return int(tp)
    elif metric == "fp":
        return int(fp)
    elif metric == "tn":
        return int(tn)
    elif metric == "fn":
        return int(fn)
    elif metric == "specificity":
        return tn / (tn + fp) if (tn + fp) > 0 else None
    elif metric == "balanced_accuracy":
        sensitivity = tp / (tp + fn) if (tp + fn) > 0 else None
        specificity = tn / (tn + fp) if (tn + fp) > 0 else None
        return (sensitivity + specificity) / 2 if sensitivity is not None and specificity is not None else None

    # Compute standard metrics
    return METRICS[metric](true_labels, pred_labels)


def load_ndarray_from_json(file_path, mode="r"):
    if not os.path.exists(file_path):
        print(f"Error: Required file '{file_path}' does not exist.")
        sys.exit(12)
    with open(file_path, mode) as f:
        j = json.load(f)
    if j is None:
        print(f"Error: JSON file '{file_path}' could not be loaded.")
        sys.exit(12)
    ndarray = np.array(j)
    return ndarray


def main():
    try:
        envvar_value = os.environ.get(ENVVAR_NAME)
        print(f"Started to compute the metrics {envvar_value}")

        pred_label = load_ndarray_from_json(PRED_LABELS_FILE)
        true_label = load_ndarray_from_json(TRUE_LABELS_FILE)

        if envvar_value is None:
            print(f"Error: Environment variable {ENVVAR_NAME} is not set.")
            sys.exit(12)
        if len(true_label) != len(pred_label):
            print("Error: Lengths of true labels and predicted labels do not match.")
            sys.exit(12)

        metrics = envvar_value.split(",")
        result = {}
        for metric in metrics:
            result[metric] = compute_metric(true_label, pred_label, metric)
        with open(RESULT_FILE, "w") as f:
            json.dump(result, f)

        print("Finished to compute the metrics")
    except Exception as e:
        print(f"An error occurred while computing the metrics: {e}")

if __name__ == "__main__":
    main()

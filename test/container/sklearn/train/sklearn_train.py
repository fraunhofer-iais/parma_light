import argparse
import json
import pickle
import sys
from sklearn.datasets import make_classification
from sklearn.model_selection import train_test_split
from sklearn.linear_model import LogisticRegression


# the channels to the outer world
MODEL_FILE = "/data/model.pkl"
X_TEST_FILE = "/data/X_test.json"
TRUE_LABELS_FILE = "/data/true_labels.json"
SEED_PARAMETER = "--seed"


def main():
    try:
        # the seed is given as command line parameter "--seed <int>"
        parser = argparse.ArgumentParser(description="generate a model, test features and true labels")
        parser.add_argument(SEED_PARAMETER, type=int, help="seed of the random number generator")
        args = parser.parse_args()
        seed_value = args.seed
        if seed_value is None:
            print(f"Error: command line parameter {SEED_PARAMETER} is not set.")
            sys.exit(12)

        print(f"Started to generate the model with random seed {seed_value}")

        # Generate sample dataset
        X, y = make_classification(n_samples=200, n_features=5, random_state=seed_value)
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42
        )

        # Train a simple Logistic Regression model
        model = LogisticRegression()
        model.fit(X_train, y_train)

        # Save the model
        with open(MODEL_FILE, "wb") as f:
            pickle.dump(model, f)

        # Save the test features
        with open(X_TEST_FILE, "w") as f:
            json.dump(X_test.tolist(), f)

        # Save the true labels
        with open(TRUE_LABELS_FILE, "w") as f:
            json.dump(y_test.tolist(), f)

        print("Finished to generate the model. Model, test features and true labels stored")
    except Exception as e:
        print(f"An error occurred while generating the model: {e}")
        sys.exit(12)


if __name__ == "__main__":
    main()

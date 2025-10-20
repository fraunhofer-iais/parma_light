import json
import pickle
import sys


# the channels to the outer world
MODEL_FILE = "/data/model.pkl"
X_TEST_FILE = "/data/X_test.json"
PRED_LABELS_FILE = "/data/pred_labels.json"


def main():
    try:
        print("Started to predict values")

        # Load the model
        with open(MODEL_FILE, "rb") as f:
            model = pickle.load(f)

        # Load the test features
        with open(X_TEST_FILE, "r") as f:
            X_test = json.load(f)

        # Predict labels using the trained model
        y_pred = model.predict(X_test)

        # Save predictions
        with open(PRED_LABELS_FILE, "w") as f:
            json.dump(y_pred.tolist(), f)

        print("Terminated to predict values")
    except Exception as e:
        print(f"An error occurred while predicting the values: {e}")
        sys.exit(12)

if __name__ == "__main__":
    main()

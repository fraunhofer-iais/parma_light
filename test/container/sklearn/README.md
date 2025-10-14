# three docker nodes build from the sklearn library to be used in workflows

- train: builds a simple regression model,
  - input is:
    - the seed for a random number generator, needed to generate training and test data
  - output is:
    - the model
    - the test labels
    - the true labels
- predict:
  - input is:
    - the model
    - the test labels
  - output is:
    - the predicted labels
- metric:
  - input is:
    - the command (defines which metric(s) should be computed)
    - the true labels
    - the predicted labels
  - output is:
    - a JSON object with the metric values
- train_and_predict: used in tests

create all images by calling ```./admin.sh --images sklearn```

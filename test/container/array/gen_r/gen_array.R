# Load the required library for JSON handling
library(jsonlite)

# Read the parameter --count, convert it to an integer and check its validity
args <- commandArgs(trailingOnly = TRUE)
count_index <- match("--count", args)
count_arg <- if (is.na(count_index) || count_index == length(args)) "" else args[count_index + 1]
count <- suppressWarnings(as.integer(count_arg))
if (is.na(count) || count < 0) {
  warning("Invalid --count value. The used default is 10.")
  count <- 10
}

numbers <- 1:count

write_json(numbers, "/data/generated_array.json", pretty = TRUE)
cat("Numbers written to /data/generated_array.json\n")

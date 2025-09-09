# Load the required library for JSON handling
library(jsonlite)

# Read the COUNT environment variable, convert it to an integer and check its validity
count_env <- Sys.getenv("COUNT")
count <- as.integer(count_env)
if (is.na(count) || count < 0) {
  stop("Invalid COUNT value. Please set COUNT to a non-negative integer.")
}

numbers <- 0:count

write_json(numbers, "/data/generated_array.json", pretty = TRUE)
cat("Numbers written to /data/generated_array.json\n")

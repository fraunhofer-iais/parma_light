# Use the official R base image
FROM r-base:4.5.0

RUN R -e "install.packages('jsonlite', repos='http://cran.r-project.org')"
COPY gen_array.R gen_array.R

CMD ["Rscript", "gen_array.R"]

FROM ubuntu:22.04 AS build

VOLUME /opt/db /tmp/openrobertaTmp
EXPOSE 1999

RUN mkdir --parent /opt/openroberta-lab/lib
WORKDIR /opt/openroberta-lab

COPY --from=build /tmp/build/export .
COPY Docker/openroberta/conf/y-standalone-lab/start.sh .
RUN chmod ugo+rx ./*.sh

ENTRYPOINT ["./start.sh"]
CMD []

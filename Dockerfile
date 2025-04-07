FROM docker/buildx-bin:v0.12 as buildx

FROM docker:24-dind

RUN apk add bash pigz sysstat procps lsof python3 py3-pip curl libc6-compat py3-yaml

COPY etc/docker/daemon.json /etc/docker/daemon.json

COPY --from=buildx /buildx /root/.docker/cli-plugins/docker-buildx

COPY ./entrypoint ./entrypoint
RUN chmod +x ./entrypoint
COPY ./docker-entrypoint.d/* ./docker-entrypoint.d/

COPY ./proxy.py /app/proxy.py
COPY ./challenges /app/challenges

ENV DOCKER_TMPDIR=/data/docker/tmp

ENTRYPOINT ["./entrypoint"]

CMD ["dockerd", "-p", "/var/run/docker.pid"]
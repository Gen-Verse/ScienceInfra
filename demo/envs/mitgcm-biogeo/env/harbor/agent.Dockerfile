# @NAME@: defective MITgcm tree; the archive and defect record stay in prep.
FROM @DIGEST@ AS prep

ENV DEBIAN_FRONTEND=noninteractive
@APT_MIRROR@RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential python3 python3-numpy ca-certificates make gfortran \
    && rm -rf /var/lib/apt/lists/*

COPY source/@MITGCM_ARCHIVE@ /tmp/mitgcm.tar.gz
RUN echo "@MITGCM_SHA256@  /tmp/mitgcm.tar.gz" | sha256sum -c - \
 && mkdir -p /app \
 && tar -xzf /tmp/mitgcm.tar.gz -C /app \
 && mv /app/mitgcm-@MITGCM_COMMIT@ /app/MITgcm \
 && rm /tmp/mitgcm.tar.gz \
 && test ! -e /app/MITgcm/.git

COPY defect/ /opt/defect/
RUN python3 /opt/defect/apply_defect.py /opt/defect/defect.json /app/MITgcm \
 && rm -rf /app/MITgcm/.git \
 && @STRIP@

FROM @DIGEST@

ENV DEBIAN_FRONTEND=noninteractive
# tmux is a hard dependency of harbor's terminus-2 harness, not a convenience: it
# drives the container through a tmux pane. It must be baked in because the agent
# allowlist carries only model API hosts and no Debian mirror, so terminus-2's
# runtime `apt install tmux` and build-from-source fallbacks both fail and every
# trial dies with "Failed to install tmux from source" then rollout_error.
# asciinema is deliberately omitted: harbor treats recording as best-effort and
# proceeds without it, so it is not worth an image layer here.
@APT_MIRROR@RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential python3 python3-numpy ca-certificates make gfortran \
    time procps tmux \
    && rm -rf /var/lib/apt/lists/*

COPY --from=prep /app/MITgcm /app/MITgcm
COPY cases/ /app/cases/
COPY checks/ /app/checks/
COPY rowtool.py runtime_lib.py /app/
RUN mkdir -p /app/builds /logs/artifacts
WORKDIR /app

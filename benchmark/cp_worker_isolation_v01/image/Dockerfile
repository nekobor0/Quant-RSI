FROM python@sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258
RUN python -m pip uninstall -y pip && mkdir -p /worker /submit /public /boundary_canary && \
    printf '{"synthetic_only":true,"answer":17}' > /boundary_canary/oracle.json && \
    printf '{"synthetic_only":true,"rule":"external_only"}' > /boundary_canary/scoring.json && \
    chmod 600 /boundary_canary/*.json
COPY runner.py /worker/runner.py
RUN chmod 555 /worker && chmod 444 /worker/runner.py
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
USER 65532:65532
WORKDIR /submit
ENTRYPOINT ["python", "-I", "-S", "-B", "/worker/runner.py"]

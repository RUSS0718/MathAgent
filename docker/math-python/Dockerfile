FROM python@sha256:b7a9e5f6a93d6d4a31f129bbd4bdee69efccb6ded0fb230d78aafaf37af98377
RUN pip install --no-cache-dir --disable-pip-version-check sympy==1.14.0 mpmath==1.3.0 numpy==2.3.4
ENV OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1
LABEL mathagent.python.policy="docker-python-v1" \
    mathagent.python.base_sha256="b7a9e5f6a93d6d4a31f129bbd4bdee69efccb6ded0fb230d78aafaf37af98377" \
    mathagent.python.version="3.11.17" \
    mathagent.python.sympy="1.14.0" \
    mathagent.python.numpy="2.3.4" \
    mathagent.python.mpmath="1.3.0"
USER 65534:65534

# CPU-only tooling image. The production photo editor does not use this image.
FROM python:3.12-slim-bookworm@sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258

ARG TARGETARCH
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HOME=/tmp \
    OMP_NUM_THREADS=2 \
    MKL_NUM_THREADS=2

WORKDIR /opt/colorcheck-ml
COPY requirements.txt ./requirements.txt
# Wheel hashes pin the CPU builds and avoid installing CUDA dependencies.
RUN case "$TARGETARCH" in \
      arm64) WHEEL="torch-2.13.0%2Bcpu-cp312-cp312-manylinux_2_28_aarch64.whl#sha256=6f307c2c32d764ffc6ff6893b801fad6d4752f3e67966cb8abf1843427c02604" ;; \
      amd64) WHEEL="torch-2.13.0%2Bcpu-cp312-cp312-manylinux_2_28_x86_64.whl#sha256=4ca4a9394b0c771238a4f73590fdbbc4debad85ed0fa63d026ae1b085da7d6e2" ;; \
      *) echo "Supported platforms: linux/arm64 and linux/amd64" >&2; exit 1 ;; \
    esac \
    && python -m pip install --no-cache-dir "https://download-r2.pytorch.org/whl/cpu/$WHEEL" \
    && python -m pip install --no-cache-dir -r requirements.txt \
    && python -m pip check

COPY export_adaptive_lut.py LICENSE.txt ./
RUN useradd --uid 10001 --no-create-home appuser
USER 10001:10001

ENTRYPOINT ["python", "/opt/colorcheck-ml/export_adaptive_lut.py"]
CMD ["--weights", "/weights", "--output", "/outputs"]

# RTLProbe tooling pipeline environment
#
# Historical: these pins (Icarus 12.0, Yosys 0.33, Verilator 5.038) are not the
# toolchain that qualified the accepted cases. See README.md, "Which toolchain
# is authoritative", before building or relying on this image.
#
# Base: Ubuntu 24.04 (Noble). Chosen deliberately: Ubuntu 24.04's apt repo
# ships Icarus Verilog 12.0-2build2, which is an EXACT match for the
# required 12.0 — no source build needed for that tool. Verilator's pinned
# patch version (5.038) isn't in apt (noble ships 5.020) or in current
# Homebrew (5.050 as of Sep 2026), so it's built from its exact git tag
# regardless of host OS — doing that once here means every team member,
# on macOS or Linux, gets an identical binary.
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

# --- Icarus Verilog 12.0 + Yosys (pinned exact apt package versions) ---
RUN apt-get update && apt-get install -y --no-install-recommends \
        iverilog=12.0-2build2 \
        yosys=0.33-5build2 \
        git build-essential help2man perl make autoconf g++ flex bison \
        ccache libgoogle-perftools-dev numactl libfl2 libfl-dev \
        zlib1g zlib1g-dev \
        python3 python3-pip python3-venv \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# --- Verilator 5.038 (pinned git tag — not available via apt on any distro) ---
RUN git clone --depth 1 --branch v5.038 https://github.com/verilator/verilator.git /opt/verilator-src \
    && cd /opt/verilator-src \
    && autoconf \
    && ./configure \
    && make -j"$(nproc)" \
    && make install \
    && cd / && rm -rf /opt/verilator-src

WORKDIR /workspace
CMD ["/bin/bash"]

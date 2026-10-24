# RTLProbe tooling pipeline environment
#
# Pinned to the native toolchain that qualified every accepted case, as
# recorded in the agents repository's environment/toolchain-versions-mac-2026-09.txt:
#
#   Icarus Verilog 13.0   built from git tag v13_0
#   Verilator 5.046       built from git tag v5.046
#   Yosys 0.69            built from git tag v0.69 (the Mac binary reports
#                         "0.69+post": one merge commit ahead of the tag with
#                         no source change beyond it)
#
# None of these versions is in Ubuntu 24.04's apt (which ships 12.0, 5.020 and
# 0.33), so all three are built from their tags. Override a pin at build time
# with --build-arg IVERILOG_TAG=... VERILATOR_TAG=... YOSYS_TAG=...
#
# The runner's environment fingerprint hashes each tool's version banner,
# which includes the compiler and git sha, so this image never reproduces the
# Mac fingerprint even at identical versions. Qualify fresh on the image
# (scripts/rtlprobe.py qualify) before generating cases with it.
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive
ARG IVERILOG_TAG=v13_0
ARG VERILATOR_TAG=v5.046
ARG YOSYS_TAG=v0.69

# Build dependencies for all three tools, plus the small utilities the runner's
# fingerprint records (git, patch) and Python for the runner itself.
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates git patch \
        build-essential g++ clang lld make cmake autoconf \
        gperf flex bison gawk help2man perl perl-doc pkg-config \
        python3 python3-pip python3-venv \
        ccache libgoogle-perftools-dev numactl libfl2 libfl-dev \
        libreadline-dev tcl-dev libffi-dev libbz2-dev zlib1g zlib1g-dev \
        libboost-system-dev libboost-python-dev libboost-filesystem-dev \
    && rm -rf /var/lib/apt/lists/*

# --- Icarus Verilog (iverilog, vvp) ---
# The tag ships a generated configure; running autoconf.sh would dirty the
# tree and make the version banner read "v13_0-dirty".
RUN git clone --depth 1 --branch "${IVERILOG_TAG}" https://github.com/steveicarus/iverilog.git /opt/iverilog-src \
    && cd /opt/iverilog-src \
    && ./configure \
    && make -j"$(nproc)" \
    && make install \
    && cd / && rm -rf /opt/iverilog-src

# --- Verilator ---
RUN git clone --depth 1 --branch "${VERILATOR_TAG}" https://github.com/verilator/verilator.git /opt/verilator-src \
    && cd /opt/verilator-src \
    && autoconf \
    && ./configure \
    && make -j"$(nproc)" \
    && make install \
    && cd / && rm -rf /opt/verilator-src

# --- Yosys (CMake build since 0.6x; abc and the other libraries are submodules) ---
RUN git clone --depth 1 --branch "${YOSYS_TAG}" --recurse-submodules --shallow-submodules \
        https://github.com/YosysHQ/yosys.git /opt/yosys-src \
    && cd /opt/yosys-src \
    && cmake -B build . -DCMAKE_BUILD_TYPE=Release -DYOSYS_ENABLE_UNIT_TESTS=OFF \
    && cmake --build build --config Release --parallel "$(nproc)" \
    && cmake --install build --strip \
    && cd / && rm -rf /opt/yosys-src

# Record the versions actually built into the image, for comparison with the
# native toolchain record and with the runner's fingerprint.
RUN { iverilog -V 2>&1 | head -1; vvp -V 2>&1 | head -1; verilator --version; yosys -V; } \
        | tee /etc/rtlprobe-toolchain-versions.txt

WORKDIR /workspace
CMD ["/bin/bash"]

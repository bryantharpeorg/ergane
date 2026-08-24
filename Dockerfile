# 088-US3: the Ergane engine container.
#
# This Dockerfile is the source of truth for what the image installs.  It is
# parsed by a committed drift test; removing a required binary fails the test.

FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

# Install the host-probed and sandbox-toolchain binaries.  Required binary
# names are derived from factory.controlplane.verify._inspect_host and
# factory.workgraph.adapter.BwrapBackend._toolchain:
#   bwrap, git, gh, claude, uv, node, python
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        bubblewrap \
        git \
        gh \
        curl \
        ca-certificates \
        python3 \
        python3-pip \
        python3-venv \
    && rm -rf /var/lib/apt/lists/*

# bubblewrap must land at the path the adapter and the gate both pin.
RUN test -f /usr/bin/bwrap

# Node.js is required by the agent toolchain; use the NodeSource LTS install.
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# uv is the package manager the factory gates use.
ADD --chmod=755 https://astral.sh/uv/install.sh /tmp/uv-install.sh
RUN /tmp/uv-install.sh \
    && install -m 755 "$HOME/.local/bin/uv" /usr/local/bin/uv \
    && rm /tmp/uv-install.sh

# The agent runner named by factory.workgraph.adapter.DEFAULT_EXECUTABLE.
RUN npm install -g @anthropic-ai/claude-code

# The factory's own distribution (ergane-cli).
COPY . /opt/ergane
WORKDIR /opt/ergane
RUN python3 -m venv .venv \
    && .venv/bin/pip install --no-cache-dir -e /opt/ergane \
    && .venv/bin/pip show ergane-cli >/dev/null \
    && .venv/bin/ergane --help >/dev/null

# Runtime user: non-root, fixed uid for compose file ownership parity.
RUN useradd -m -u 1000 -s /bin/bash ergane \
    && chown -R ergane:ergane /opt/ergane
USER 1000:1000

ENV PATH="/opt/ergane/.venv/bin:/usr/local/bin:/usr/bin:$PATH"
ENV HOME="/home/ergane"

ENTRYPOINT ["python3", "-m", "factory.supervision.container_supervisor"]

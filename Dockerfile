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
#
# The uid is what matters and the account name is not: compose declares
# `user: 1000:1000`, the AppArmor profile and the seccomp policy are written
# against that uid, and `USER` below is numeric. ubuntu:24.04 already ships an
# account at uid 1000 (`ubuntu`), so `useradd -u 1000` fails the build outright
# with `UID 1000 is not unique` — which is why this creates the home directory
# and takes ownership instead of minting a second account for an occupied id.
#
# $HOME is set below and nothing else creates it: `useradd -m` used to, so it is
# made explicitly here. An unwritable $HOME is not cosmetic in this image — the
# agent adapter writes a per-node home under it.
RUN install -d -m 755 -o 1000 -g 1000 /home/ergane \
    && chown -R 1000:1000 /opt/ergane
USER 1000:1000

ENV PATH="/opt/ergane/.venv/bin:/usr/local/bin:/usr/bin:$PATH"
ENV HOME="/home/ergane"

ENTRYPOINT ["python3", "-m", "factory.supervision.container_supervisor"]

FROM ghcr.io/extremscorner/libogc2:20260805

ENV DEVKITPRO=/opt/devkitpro
ENV DEVKITPPC=/opt/devkitpro/devkitPPC
ENV PATH=/opt/devkitpro/devkitPPC/bin:/opt/devkitpro/tools/bin:${PATH}

WORKDIR /workspace

FROM condaforge/miniforge3:latest

ARG QUETZ_VERSION=0.0.4

RUN conda install -q -y quetz==${QUETZ_VERSION} && \
    conda clean --all -f -y
ENV LANG=en_US.UTF-8

USER nobody
# TODO: use the CLI when available in the next release to set-up Quetz
CMD ["/bin/bash"]
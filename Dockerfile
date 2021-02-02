FROM ubuntu:20.04

RUN apt-get update && apt-get install -y \
    bzip2 \
    ca-certificates \
    curl \
    postgresql-client \
    && rm -rf /var/lib/{apt,dpkg,cache,log}
RUN curl -L https://micro.mamba.pm/api/micromamba/linux-64/latest | \
    tar -xj -C /tmp bin/micromamba
RUN cp /tmp/bin/micromamba /bin/micromamba

ENV MAMBA_ROOT_PREFIX=/opt/conda


RUN mkdir -p $(dirname $MAMBA_ROOT_PREFIX) && \
    /bin/micromamba shell init -s bash -p $MAMBA_ROOT_PREFIX && \
    echo "micromamba activate base" >> ~/.bashrc

ENV PATH="/opt/conda/bin:${PATH}"

RUN mkdir /code
WORKDIR /code
COPY environment.yml /code/

RUN micromamba install -v -y -n base -c conda-forge -f environment.yml

COPY . /code/
RUN pip install -e .

RUN useradd quetz --no-log-init -u 1000 -p "$(openssl passwd -1 mamba)" 

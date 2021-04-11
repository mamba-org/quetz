# Build the frontend
FROM node:14 as node

COPY quetz_frontend /quetz_frontend
RUN cd /quetz_frontend \
  && npm install \
  && npm run build

# Build conda environment
FROM condaforge/mambaforge:4.9.2-7 as conda

COPY environment.yml /tmp/environment.yml
RUN CONDA_COPY_ALWAYS=true mamba env create -p /env -f /tmp/environment.yml \
  && conda clean -afy

COPY . /code
RUN conda run -p /env python -m pip install --no-deps /code

# Create image
FROM debian:buster-slim

ENV LANG=C.UTF-8 LC_ALL=C.UTF-8

COPY --from=node /quetz_frontend/dist /quetz-frontend
COPY --from=conda /env /env

# Set WORKDIR to /tmp because quetz always creates a quetz.log file
# in the current directory
WORKDIR /tmp
ENV PATH /env/bin:$PATH
EXPOSE 8000

# The following command assumes that a deployment has been initialized
# in the /quetz-deployment volume
CMD ["quetz", "start", "/quetz-deployment", "--host", "0.0.0.0", "--port", "8000"]

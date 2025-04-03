FROM python:3.12.6-slim AS base
# Setup env
ENV LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONFAULTHANDLER=1

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        supervisor \
        bash \
        nginx \
        curl  \
        gettext-base && \
    python3 -m pip install --no-cache-dir uv && \
    rm -rf /var/lib/apt/lists/* /etc/nginx/sites-enabled/default

RUN mkdir -p /etc/nginx/ssl

# Set workdir and copy dependency files
WORKDIR /ecfr
COPY . .

# Install dependencies into /.venv
RUN uv venv /ecfr/.venv && \
    . /ecfr/.venv/bin/activate && \
    uv pip install --no-cache-dir .


# Add in the configuration files for running (SupervisorD) and NGINX config
COPY container/supervisord.conf /etc/supervisord.conf
COPY container/nginx-http.template.conf /etc/nginx/templates/nginx-http.template.conf
COPY container/nginx-tls.template.conf /etc/nginx/templates/nginx-tls.template.conf
COPY container/nginx-startup-script.sh /nginx-startup-script.sh

# Add in healthcheck script
COPY container/healthcheck.sh /ecfr/healthcheck.sh

RUN chmod +x main.py

EXPOSE 80
EXPOSE 443

CMD ["/nginx-startup-script.sh"]



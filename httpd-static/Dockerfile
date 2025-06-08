FROM debian:12-slim

RUN apt-get update && \
    apt-get install -y apache2 && \
    apt-get clean

RUN echo "#!/usr/bin/bash" > /apache.sh \
    && echo 'source /etc/apache2/envvars ; exec /usr/sbin/apache2 -DFOREGROUND' >> /apache.sh \
    && chmod +x /apache.sh

RUN mkdir /var/run/apache2 \
    && rm -f /etc/apache2/sites-enabled/000-default.conf \
    && echo "LISTEN 8080" > /etc/apache2/ports.conf \
    && sed -ri -e 's!^(\s*ErrorLog)\s+\S+!\1 /proc/self/fd/2!g' /etc/apache2/apache2.conf

COPY conf/apache/vhosts /etc/apache2/sites-enabled/

ENTRYPOINT ["/apache.sh"]

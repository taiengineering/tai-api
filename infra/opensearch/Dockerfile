FROM opensearchproject/opensearch:2.17.0

USER root

# Install gosu for privilege drop (opensearch base image may not include it)
RUN curl -fsSL https://github.com/tianon/gosu/releases/download/1.17/gosu-amd64 \
      -o /usr/local/bin/gosu \
    && chmod +x /usr/local/bin/gosu \
    && gosu nobody true

# Install analysis-nori at build time — never at runtime
RUN ./bin/opensearch-plugin install analysis-nori

COPY opensearch.yml /usr/share/opensearch/config/opensearch.yml
COPY --chmod=755 entrypoint.sh /usr/local/bin/tai-entrypoint.sh

EXPOSE 9200 9600

ENTRYPOINT ["/usr/local/bin/tai-entrypoint.sh"]

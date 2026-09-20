FROM opensearchproject/opensearch:2.17.0

# Install analysis-nori at build time — never at runtime
RUN ./bin/opensearch-plugin install analysis-nori

COPY opensearch.yml /usr/share/opensearch/config/opensearch.yml
COPY --chmod=755 entrypoint.sh /usr/local/bin/tai-entrypoint.sh

EXPOSE 9200 9600

# Start as root so entrypoint can fix volume ownership before dropping to opensearch user
USER root
ENTRYPOINT ["/usr/local/bin/tai-entrypoint.sh"]

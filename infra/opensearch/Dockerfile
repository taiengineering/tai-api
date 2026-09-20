FROM opensearchproject/opensearch:2.17.0

# Install analysis-nori at build time — never at runtime
RUN ./bin/opensearch-plugin install analysis-nori

COPY entrypoint.sh /usr/local/bin/tai-entrypoint.sh
RUN chmod +x /usr/local/bin/tai-entrypoint.sh

EXPOSE 9200 9600

ENTRYPOINT ["/usr/local/bin/tai-entrypoint.sh"]

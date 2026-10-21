FROM neo4j:2026.09.0-community@sha256:d6269a020149934597c8c3df926d080a612796dbbb48861ca9d5b1109cabf0d8
ADD --chmod=0444 --checksum=sha256:a95983fd96e865d2bcdf911cc500e7c82808c27ab9fd226bf96732b6c3d8c46e https://github.com/prometheus/jmx_exporter/releases/download/1.6.0/jmx_prometheus_javaagent-1.6.0.jar /opt/platform/jmx-agent.jar
COPY jmx.yaml /opt/platform/jmx.yaml
# The JVM agent is readable by the unprivileged Neo4j process.
RUN chmod 0755 /opt/platform \
    && printf '\nserver.jvm.additional=-javaagent:/opt/platform/jmx-agent.jar=9404:/opt/platform/jmx.yaml\n' \
        >> /var/lib/neo4j/conf/neo4j.conf
USER 7474:7474

"""Render explicitly managed, non-secret inventory options before host mutations."""
import ipaddress
import json
import math
import re

from ansible.errors import AnsibleFilterError


ADDRESSES = {
    'postgres': ('POSTGRES_IP', 10), 'platform-api': ('PLATFORM_API_IP', 11),
    'keycloak': ('KEYCLOAK_IP', 12), 'telemetry-gateway': ('TELEMETRY_GATEWAY_IP', 13),
    'alloy': ('ALLOY_IP', 14), 'store-access': ('STORE_RELAY_IP', 15),
    'rustfs': ('RUSTFS_IP', 16), 'opensearch': ('OPENSEARCH_IP', 17),
    'qdrant': ('QDRANT_IP', 18), 'opensearch-init': ('OPENSEARCH_INIT_IP', 19),
    'proxy': ('PROXY_IP', 20), 'blackbox-exporter': ('BLACKBOX_EXPORTER_IP', 21),
    'prometheus': ('PROMETHEUS_IP', 22), 'grafana': ('GRAFANA_IP', 23),
    'tempo': ('TEMPO_IP', 24), 'loki': ('LOKI_IP', 25),
    'alertmanager': ('ALERTMANAGER_IP', 26), 'node-exporter': ('NODE_EXPORTER_IP', 27),
    'keycloak-db-init': ('KEYCLOAK_DB_INIT_IP', 28),
    'keycloak-realm-init': ('KEYCLOAK_REALM_INIT_IP', 29),
    'postgres-exporter': ('POSTGRES_EXPORTER_IP', 30),
    'neo4j-controller': ('NEO4J_CONTROLLER_IP', 31),
}
PROFILES = {'s3', 'qdrant', 'opensearch', 'neo4j'}


def fail(message):
    # Never interpolate inventory values, which can accidentally contain secrets.
    raise AnsibleFilterError(message)


def mapping(value, allowed, name):
    if not isinstance(value, dict) or set(value) - set(allowed):
        fail(name + ' must be a mapping containing only documented keys')
    return value


def integer(value, lower, upper, name):
    if not isinstance(value, int) or isinstance(value, bool) or not lower <= value <= upper:
        fail(name + ' must be an integer within its documented range')
    return value


def network(value, prefix, name):
    try:
        if not isinstance(value, str):
            raise ValueError()
        result = ipaddress.IPv4Network(value)
        private = any(result.subnet_of(ipaddress.IPv4Network(block)) for block in
                      ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16'))
        if result.prefixlen != prefix or not private:
            raise ValueError()
        return result
    except (ValueError, TypeError):
        fail(name + ' must be an aligned private IPv4 /' + str(prefix) + ' subnet')


def addresses(settings, subnet, specification, name):
    overrides = mapping(settings.get('addresses', {}), specification, name + '.addresses')
    result = {}
    try:
        for service, (key, offset) in specification.items():
            ip = ipaddress.IPv4Address(overrides.get(service, str(subnet.network_address + offset)))
            if ip not in subnet or ip in (subnet.network_address, subnet.broadcast_address, subnet.network_address + 1):
                raise ValueError()
            result[key] = str(ip)
        if len(set(result.values())) != len(result):
            raise ValueError()
    except (ValueError, TypeError):
        fail(name + ' addresses must be distinct usable subnet members excluding the gateway')
    return result


def platform_inventory_settings(options):
    mapping(options, {'stores', 'network', 'search_console_network', 'k3s_image',
        'bootstrap_subject', 'store_ssh_host', 'bastion_bind_ip', 'bastion_port',
        'bootstrap_timeout_seconds', 'readiness_timeout_seconds', 'kubectl_version'}, 'Deployment options')
    result = {}
    stores = options.get('stores')
    if stores is not None:
        mapping(stores, {'profiles', 'capacity_bytes', 'neo4j'}, 'platform_stores')
        profiles = stores.get('profiles')
        if (not isinstance(profiles, list) or any(not isinstance(p, str) or p not in PROFILES for p in profiles)
                or len(set(profiles)) != len(profiles)):
            fail('platform_stores.profiles must be a list of distinct supported providers')
        capacity = mapping(stores.get('capacity_bytes'), PROFILES | {'postgresql'}, 'platform_stores.capacity_bytes')
        if not {'postgresql', *profiles} <= set(capacity):
            fail('Allocate capacity for PostgreSQL and every selected provider')
        for amount in capacity.values():
            integer(amount, 1, 2**63 - 1, 'Provider capacity in bytes')
        result.update(COMPOSE_PROFILES=','.join(profiles), STORE_CAPACITY_BYTES=json.dumps(capacity, separators=(',', ':'), sort_keys=True))
        neo4j = mapping(stores.get('neo4j', {}), {'max_instances', 'memory_bytes'}, 'platform_stores.neo4j')
        for field, key, lower, upper in [('max_instances', 'NEO4J_MAX_INSTANCES', 1, 64),
                ('memory_bytes', 'NEO4J_INSTANCE_MEMORY_BYTES', 2**30, 16 * 2**30)]:
            if field in neo4j:
                result[key] = str(integer(neo4j[field], lower, upper, 'platform_stores.neo4j.' + field))
    networks = []
    for field, prefix, key, specification in [
            ('network', 24, 'PLATFORM_SUBNET', ADDRESSES),
            ('search_console_network', 29, 'STORE_SEARCH_CONSOLE_SUBNET', {
                'platform-api': ('STORE_SEARCH_API_IP', 2), 'opensearch-dashboards': ('OPENSEARCH_DASHBOARDS_IP', 3)})]:
        config = options.get(field)
        if config is None:
            continue
        mapping(config, {'subnet', 'addresses'}, 'platform_' + field)
        subnet = network(config.get('subnet'), prefix, 'platform_' + field)
        networks.append(subnet)
        result[key] = str(subnet)
        result.update(addresses(config, subnet, specification, 'platform_' + field))
    if len(networks) == 2 and networks[0].overlaps(networks[1]):
        fail('Platform and search-console networks must not overlap')
    image = options.get('k3s_image')
    if image is not None:
        if not isinstance(image, str) or not re.fullmatch(r'rancher/k3s:v1\.(35|36|37)\.\d+-k3s\d+(?:@sha256:[a-f0-9]{64})?', image):
            fail('platform_k3s_image must pin a supported rancher/k3s release')
        kubectl = options.get('kubectl_version', 'v1.36.4')
        if not isinstance(kubectl, str) or not re.fullmatch(r'v1\.(35|36|37)\.\d+', kubectl):
            fail('platform_kubectl_version must pin a supported release')
        if abs(int(image.split('.')[1]) - int(kubectl.split('.')[1])) > 1:
            fail('kubectl must be within one minor version of the selected Kubernetes release')
        result['K3S_IMAGE'] = image
    subject = options.get('bootstrap_subject')
    if subject is not None:
        if not isinstance(subject, str) or (subject and not re.fullmatch(r'[A-Za-z0-9._:@-]{1,255}', subject)):
            fail('platform_bootstrap_subject must be an immutable subject identifier or empty')
        result['PLATFORM_BOOTSTRAP_SUBJECT'] = subject
    bind = options.get('bastion_bind_ip')
    if bind is not None:
        try:
            if not isinstance(bind, str):
                raise ValueError()
            ip = ipaddress.IPv4Address(bind)
            if ip.is_unspecified or ip.is_multicast or ip.is_reserved or ip.is_link_local or ip == ipaddress.IPv4Address('255.255.255.255'):
                raise ValueError()
        except (ValueError, TypeError):
            fail('Select a specific IPv4 bastion bind address; wildcard binding is unsupported')
    port = options.get('bastion_port')
    if port is not None:
        result['STORE_SSH_PORT'] = str(integer(port, 1024, 65535, 'platform_database_bastion_port'))
    host = options.get('store_ssh_host')
    if host is not None:
        if not isinstance(host, str) or (host and (len(host) > 253 or not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?', host))):
            fail('platform_store_ssh_host must be an SSH hostname or IPv4 address, without a URL or port')
        if host and (bind is None or ipaddress.IPv4Address(bind).is_loopback or port is None):
            fail('Advertising remote SSH access requires an explicit non-loopback bastion bind address and port')
        result['STORE_SSH_HOST'] = host
    for field, lower, upper in [('bootstrap_timeout_seconds', 60, 14400), ('readiness_timeout_seconds', 5, 3600)]:
        integer(options.get(field, 3600 if field.startswith('bootstrap') else 300), lower, upper, 'platform_' + field)
    return result


def platform_trace_settings(settings):
    mapping(settings, {'sample_rate', 'retention'}, 'Tracing settings')
    value = settings.get('sample_rate', 1.0)
    try:
        if isinstance(value, bool) or not isinstance(value, (str, int, float)):
            raise ValueError()
        rate = float(value)
        if not math.isfinite(rate) or not 0 <= rate <= 1:
            raise ValueError()
    except (ValueError, TypeError, OverflowError):
        fail('platform_trace_sample_rate must be a finite number between 0 and 1')
    retention = settings.get('retention', '24h')
    if not isinstance(retention, str) or not re.fullmatch(r'[1-9][0-9]{0,5}h', retention):
        fail('platform_trace_retention must be positive whole hours, such as 24h or 168h (maximum 999999h)')
    return {'sample_rate': str(rate), 'retention': retention}


class FilterModule:
    def filters(self):
        return {'platform_inventory_settings': platform_inventory_settings, 'platform_trace_settings': platform_trace_settings}

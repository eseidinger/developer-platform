import json
import os
# JSON is a YAML subset, accepted by k3d without a templating dependency.
print(json.dumps({
    "apiVersion": "k3d.io/v1alpha5", "kind": "Simple",
    "metadata": {"name": "workloads"}, "servers": 1, "agents": 2,
    "image": os.environ["K3S_IMAGE"], "network": "developer-platform",
    "ports": [{"port": "127.0.0.1:8081:80", "nodeFilters": ["loadbalancer"]}],
    "kubeAPI": {"hostIP": "127.0.0.1", "hostPort": "6445"},
    "options": {
        "k3d": {"wait": True, "timeout": "180s"},
        "kubeconfig": {"updateDefaultKubeconfig": False, "switchCurrentContext": False},
        "k3s": {"extraArgs": [
            {"arg": "--tls-san=k3d-workloads-server-0", "nodeFilters": ["server:*"]},
            {"arg": "--secrets-encryption", "nodeFilters": ["server:*"]}]},
        "runtime": {"serversMemory": "2g", "agentsMemory": "4g"}
    }
}, indent=2))

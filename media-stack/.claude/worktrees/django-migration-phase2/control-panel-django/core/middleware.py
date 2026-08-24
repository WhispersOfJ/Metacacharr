import os
import socket


def _own_network_gateway():
    """Best-effort Docker gateway lookup so requests from bridge-network
    containers (whose REMOTE_ADDR is the gateway IP, not a real host IP)
    are recognized as loopback. If Docker is unreachable the loopback set
    stays at just localhost/127.0.0.1 — the middleware still works but the
    narrower set may reject legitimate internal requests."""
    try:
        import docker

        client = docker.from_env()
        self_container = client.containers.get(socket.gethostname())
        for net in self_container.attrs.get("NetworkSettings", {}).get("Networks", {}).values():
            if net.get("Gateway"):
                return net["Gateway"]
    except Exception:
        pass
    return None


class VerifySameOriginMiddleware:
    """Ported 1:1 from control-panel/main.py's verify_same_origin (fixed
    under /cso, commit e360961). Defense-in-depth alongside Django's own
    CSRF middleware and session auth — stays in place unchanged through the
    migration per the spec's Auth section."""

    def __init__(self, get_response):
        self.get_response = get_response
        host_ip = os.environ.get("HOST_IP")
        self.allowed_hosts = {h for h in (host_ip, "localhost", "127.0.0.1") if h}
        self.loopback_ips = {"127.0.0.1", "::1"}
        gateway = _own_network_gateway()
        if gateway:
            self.loopback_ips.add(gateway)

    def __call__(self, request):
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            host = (request.META.get("HTTP_HOST") or "").split(":")[0]
            if host not in self.allowed_hosts:
                from django.http import JsonResponse

                return JsonResponse(
                    {"ok": False, "message": "Rejected: Host header did not match this panel's configured HOST_IP."},
                    status=403,
                )
            if host in ("localhost", "127.0.0.1"):
                client_host = request.META.get("REMOTE_ADDR")
                if client_host not in self.loopback_ips:
                    from django.http import JsonResponse

                    return JsonResponse(
                        {"ok": False, "message": "Rejected: Host header claimed localhost but the connection wasn't actually local."},
                        status=403,
                    )
            origin = request.META.get("HTTP_ORIGIN")
            if origin:
                origin_host = origin.split("://", 1)[-1].split(":")[0].split("/")[0]
                if origin_host not in self.allowed_hosts:
                    from django.http import JsonResponse

                    return JsonResponse(
                        {"ok": False, "message": "Rejected: Origin did not match this panel's host."},
                        status=403,
                    )
        return self.get_response(request)

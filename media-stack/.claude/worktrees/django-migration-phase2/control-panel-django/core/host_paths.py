"""Read-only host mounts shared across apps needing diagnostics/per-app
config reads - ported byte-identical from the FastAPI-era
control-panel/core/host_paths.py. See docker-compose.yml's control-panel
volumes for what backs each of these.
"""
HOST_CONFIG_DIR = "/host-config"
HOST_MNT_DIR = "/mnt"
# Only present once the compose privilege change for Force Unstick lands -
# every helper that reads these degrades gracefully (empty result, not a
# 500) if the mount isn't there.
HOST_PROC_DIR = "/host-proc"
HOST_SYS_FUSE_DIR = "/host-sys-fuse"
HOST_README = "/host-README.md"

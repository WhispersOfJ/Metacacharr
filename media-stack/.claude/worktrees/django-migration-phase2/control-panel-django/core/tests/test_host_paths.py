from core.host_paths import HOST_CONFIG_DIR, HOST_MNT_DIR, HOST_PROC_DIR, HOST_README, HOST_SYS_FUSE_DIR


def test_host_path_constants_are_populated_strings():
    for value in (HOST_CONFIG_DIR, HOST_MNT_DIR, HOST_PROC_DIR, HOST_SYS_FUSE_DIR, HOST_README):
        assert isinstance(value, str)
        assert value

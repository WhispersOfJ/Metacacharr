# Usage: stack-arr-import-all <radarr|sonarr>
# Bulk version of stack-arr-import - imports every candidate
# stack-arr-import-candidates currently lists for that app in one
# ManualImport command, instead of one call per file.
function stack-arr-import-all --description 'Import every stuck queue file for an *arr app in one go'
    if test (count $argv) -ne 1; or not __stack_arr_app $argv[1] >/dev/null
        echo "Usage: stack-arr-import-all <radarr|sonarr>" >&2
        return 1
    end
    set -l app (__stack_arr_app $argv[1])
    __stack_api POST "/api/arr/$app/manual-import-all"
end

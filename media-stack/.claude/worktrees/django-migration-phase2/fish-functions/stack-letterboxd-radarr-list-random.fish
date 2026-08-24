# Usage: stack-letterboxd-radarr-list-random [--no-search] [--no-monitor] [--limit N] [--dry-run]
# Picks one random URL out of ~/.cache/letterboxd_lists.txt (built by
# scripts/scrape_letterboxd.py off https://letterboxd.com/lists/featured/),
# removes it from the file so a future run won't repeat it, then runs
# stack-letterboxd-radarr-list against it to completion. All flags are
# passed straight through to that command.
#
# Per-film progress: control-panel's add-from-letterboxd-list endpoint
# prints one "letterboxd-list: [i/n] ..." line per film as it works
# (media-stack-only addition, not mirrored to the other stack-* repos -
# their copies of this command run silently until the final summary, same
# as this one did before). Tailed live here via `docker logs -f --tail 0`
# so only new lines from this run show, not the container's whole history.
function stack-letterboxd-radarr-list-random --description 'Add a random featured Letterboxd list to Radarr'
    set -l cache_file "$HOME/.cache/letterboxd_lists.txt"
    set -l scraper "$HOME/Claude/media-stack/scripts/scrape_letterboxd.py"

    if not test -f "$cache_file"
        echo "No cached list found - running the scraper first..." >&2
        python3 "$scraper"
        or return 1
    end

    set -l lines (cat "$cache_file")
    if test (count $lines) -eq 0
        echo "stack-letterboxd-radarr-list-random: $cache_file is empty - nothing to pick." >&2
        return 1
    end

    set -l idx (random 1 (count $lines))
    set -l picked $lines[$idx]
    set -l url (string trim --right --chars=/ -- $picked)

    # Atomic delete: write everything except the picked line to a temp file
    # in the same directory, then rename over the original - mv within one
    # filesystem is atomic on Linux, so a crash mid-write never leaves the
    # cache file half-written or the picked URL duplicated/lost.
    set -l tmp_file (mktemp "$cache_file.XXXXXX")
    for i in (seq (count $lines))
        if test $i -ne $idx
            echo $lines[$i] >>$tmp_file
        end
    end
    mv "$tmp_file" "$cache_file"

    echo "Selected: $url"

    # --tail 0 skips the container's existing log history - only lines
    # printed *after* this point stream, so an earlier run's progress lines
    # (or another concurrent call) don't bleed into this one's output.
    #
    # Backgrounding a `cmd1 | cmd2 &` pipeline directly in fish hangs the
    # whole function - confirmed live and reproduced down to a minimal
    # `sleep 5 | cat &` case, not specific to docker/grep. A single
    # backgrounded command doesn't hang, only a fish-native piped one does.
    # Wrapping the pipeline in `bash -c "..."` backgrounds one opaque
    # process instead - bash manages its own internal pipe, invisible to
    # fish's job control, and the hang doesn't happen.
    #
    # Cleanup uses pkill against the docker command specifically (not the
    # wrapping bash -c, and not `jobs -p`) - confirmed live that fish's job
    # table doesn't reliably track this in every invocation context either.
    bash -c "docker logs -f --tail 0 control-panel 2>&1 | grep --line-buffered 'letterboxd-list:'" &

    stack-letterboxd-radarr-list $url $argv
    set -l add_status $status

    pkill -f "docker logs -f --tail 0 control-panel" 2>/dev/null

    if test $add_status -ne 0
        echo "stack-letterboxd-radarr-list-random: stack-letterboxd-radarr-list failed for $url" >&2
        return 1
    end

    echo "Done - added films from $url to Radarr."
end

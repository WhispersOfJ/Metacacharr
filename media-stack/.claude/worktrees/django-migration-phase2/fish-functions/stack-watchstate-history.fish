# Usage: stack-watchstate-history [title] [limit]
# Watch history WatchState has recorded, newest first. With a title given it
# filters to matching titles (partial names work); with none it shows the most
# recent items across everything.
#
# Every row carries `via` (which backend reported it) and `updated_at`, which
# is how a webhook-delivered event is told apart from one the scheduled import
# picked up.
function stack-watchstate-history --description 'Watch history WatchState recorded, optionally filtered to a title'
    # urlencode rather than hand-joining: titles routinely contain spaces,
    # apostrophes and ampersands, and an unencoded space makes curl reject the
    # URL outright rather than failing usefully.
    set -l query (python3 -c "
import sys
from urllib.parse import urlencode
pairs = [(k, v) for k, v in zip(('item', 'limit'), sys.argv[1:]) if v.strip()]
print(('?' + urlencode(pairs)) if pairs else '')
" "$argv[1]" "$argv[2]")
    __stack_api GET "/api/watchstate/history$query"
end

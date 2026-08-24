# alacritty-use-theme is shipped as a bash function (source
# /usr/bin/alacritty-use-theme/use-theme.sh), not a standalone binary - this
# wrapper reuses that script under bash rather than reimplementing its
# aliases.toml lookup logic in fish.
function alacritty-use-theme --description 'Switch the active Alacritty theme (aliases.toml aware)'
    bash -c 'source /usr/bin/alacritty-use-theme/use-theme.sh && alacritty-use-theme "$1"' bash $argv[1]
end

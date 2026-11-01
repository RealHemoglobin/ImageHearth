#!/bin/sh
# ImageHearth installer for Linux. Read it before running it:
#   1. Checks the system and that there is a terminal to ask you questions.
#   2. Installs uv with its official installer, if it is missing.
#   3. Installs imagehearth-mcp, pinned to the version below.
#   4. Runs `setup`, which shows disk space and licenses before downloading,
#      and `connect --detect`, which asks before changing any agent.
# It never uses root privileges and never accepts a license for you.
#
# Everything is inside main(), so a cut-off download can't run half a script.

VERSION="0.1.0b1"
DOCS="https://github.com/RealHemoglobin/ImageHearth"

fail() {
    printf 'Error: %s\n' "$1" >&2
    exit 1
}

check_system() {
    case "$(uname -s)" in
        Linux) ;;
        Darwin)
            [ "$1" = "--experimental" ] || fail "macOS is prepared but has never been run on a real Mac, and it isn't supported.
To try it anyway on Apple Silicon, add --experimental:
  curl -LsSf https://raw.githubusercontent.com/RealHemoglobin/ImageHearth/main/install.sh | sh -s -- --experimental"
            ;;
        *)
            fail "This script is for Linux. On Windows, see $DOCS#installation."
            ;;
    esac
}

check_terminal() {
    # With `curl | sh`, standard input is this script: questions must use /dev/tty.
    (exec </dev/tty) 2>/dev/null || fail "No terminal available, so setup can't ask you to accept the model licenses. Nothing was changed.
Without a terminal, install it yourself:
  uv tool install imagehearth-mcp==$VERSION
  imagehearth-mcp setup --non-interactive
That command tells you which options it needs to continue. See $DOCS/blob/main/llms-install.md."
}

install_uv() {
    command -v uv >/dev/null 2>&1 && return

    # Where the official installer leaves uv; the current shell doesn't know it yet.
    PATH="${UV_INSTALL_DIR:-${XDG_BIN_HOME:-$HOME/.local/bin}}:$HOME/.local/bin:$PATH"
    export PATH
    command -v uv >/dev/null 2>&1 && return

    printf 'Installing uv with its official installer (https://astral.sh/uv)...\n'

    # A saved copy, because a failed download piped to sh would look like success.
    uv_installer=$(mktemp) || fail "Can't create a temporary file."

    if command -v curl >/dev/null 2>&1; then
        curl -LsSf https://astral.sh/uv/install.sh -o "$uv_installer" || uv_status=1
    elif command -v wget >/dev/null 2>&1; then
        wget -qO "$uv_installer" https://astral.sh/uv/install.sh || uv_status=1
    else
        uv_status=1
    fi

    if [ -z "${uv_status:-}" ]; then
        sh "$uv_installer" || uv_status=1
    fi

    rm -f "$uv_installer"
    [ -z "${uv_status:-}" ] && command -v uv >/dev/null 2>&1 || fail "Can't install uv. Check your network connection (curl or wget is needed) and try again, or install it by hand: https://docs.astral.sh/uv/getting-started/installation/"
}

main() {
    check_system "${1:-}"
    check_terminal
    install_uv

    # From a clone of the repository, install that code; with IMAGEHEARTH_INSTALL_SOURCE,
    # a local wheel; otherwise, the pinned version from PyPI.
    package="imagehearth-mcp==$VERSION"
    repo_dir=$(cd "$(dirname "$0")" 2>/dev/null && pwd) || repo_dir=""
    if [ -n "${IMAGEHEARTH_INSTALL_SOURCE:-}" ]; then
        package="$IMAGEHEARTH_INSTALL_SOURCE"
    elif [ -n "$repo_dir" ] && [ -f "$repo_dir/pyproject.toml" ]; then
        package="$repo_dir"
    fi
    printf 'Installing %s...\n' "$package"
    uv tool install "$package" || fail "Can't install $package. Check your network connection and try again."

    # It may not be in PATH yet.
    bin_dir=$(uv tool dir --bin) || fail "uv can't tell where it installs tools."
    command="$bin_dir/imagehearth-mcp"

    if [ "${1:-}" = "--experimental" ]; then
        "$command" setup --experimental </dev/tty || fail "Setup did not finish. Run this to continue where it stopped: \"$command\" setup --experimental"
    else
        "$command" setup </dev/tty || fail "Setup did not finish. Run this to continue where it stopped: \"$command\" setup"
    fi

    "$command" connect --detect </dev/tty || fail "Setup finished, but connecting your agents failed. Try again with: \"$command\" connect --detect"

    printf '\nDone. Restart your agent and ask it for an image.\n'
    printf 'Check the installation at any time with: "%s" doctor\n' "$command"

    case ":$PATH:" in
        *":$bin_dir:"*) ;;
        *) printf 'To use imagehearth-mcp by name, run: uv tool update-shell\n' ;;
    esac
}

main "$@"

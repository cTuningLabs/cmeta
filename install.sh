#!/bin/sh
# shellcheck shell=dash
# shellcheck disable=SC2039  # `local` is not POSIX but every real /bin/sh has it
#
# cMeta installer that installs cMeta FROM THIS DIRECTORY - not from PyPI, not
# from git.
#
#   ./install.sh
#   ./install.sh --with-deps
#   sh install.sh --home /home/me/CMETA --aops
#
# Use it after copying a cMeta source tree onto a machine (rclone, rsync, scp,
# a USB stick): it installs the package sitting next to this script, so the
# remote runs exactly the code you copied rather than whatever happens to be
# released. To install the released or the git version instead, use the
# installer on the website:
#
#   curl -LsSf https://cTuning.ai/project/cmeta/cmeta.install/install.sh | sh
#
# NETWORK: only cMeta itself comes from this directory. Its dependencies
# (pyyaml, requests, tabulate, ...) and uv are still fetched from the network,
# so PyPI and astral.sh have to be reachable. Nothing needs root unless
# --with-deps is used.
#
# Copyright (C) 2025-2026 Grigori Fursin and cTuning Labs.
# Licensed under Apache-2.0 - see https://github.com/cTuningLabs/cmeta
#
# NOTE FOR EDITORS: this script installs from its own directory, so unlike the
# website installer it can never be piped into `sh` - it has to exist as a file.
# Everything still lives inside a function with a single `main "$@"` at the end,
# to keep the two installers the same shape.

set -eu

UV_INSTALL_URL="https://astral.sh/uv/install.sh"
AOPS_REF="cTuningLabs@cmeta-aops"

# What setuptools needs in order to build this tree at all. pyproject.toml
# declares `readme = "README.md"` and
# `license-files = ["LICENSE", "COPYRIGHT", "NOTICE"]`, so a tree copied with a
# filter that took only cmeta/ and pyproject.toml fails deep inside the build
# with an obscure message. Checked up front instead - see check_source().
REQUIRED_FILES="pyproject.toml README.md LICENSE COPYRIGHT NOTICE"

# ---------------------------------------------------------------- output

say()  { [ "$QUIET" = 1 ] || printf '%s\n' "$*"; }
step() { [ "$QUIET" = 1 ] || printf '\n==> %s\n' "$*"; }
warn() { printf 'cmeta-install: warning: %s\n' "$*" >&2; }
err()  { printf 'cmeta-install: error: %s\n' "$*" >&2; exit 1; }

have() { command -v "$1" >/dev/null 2>&1; }

# Echo the command, then run it - unless --dry-run, in which case only echo.
# Everything that touches the machine goes through here, so --dry-run is a
# complete and truthful preview rather than an approximation.
run() {
    say "     \$ $*"
    [ "$DRY_RUN" = 1 ] && return 0
    "$@"
}

run_sh() {
    say "     \$ $1"
    [ "$DRY_RUN" = 1 ] && return 0
    sh -c "$1"
}

usage() {
    cat <<'EOF'
cMeta installer - installs from THIS directory (Linux, macOS)

Usage:
  ./install.sh [options]
  sh install.sh [options]

Options:
  --with-deps        also install git and curl with the OS package manager.
                     This is the only step that needs root (sudo).
  -e, --editable     install in editable mode: the installed cMeta keeps
                     pointing at this directory, so re-copying the tree
                     updates it with no reinstall. Do NOT use it if this
                     directory is temporary.
  --extras <a,b>     pip extras (default: server, which is what cserver needs)
  --no-extras        install the bare package with no extras at all
  --home <path>      value for CMETA_HOME (default: $HOME/CMETA). Always
                     wins, even inside an activated virtual environment.
  --home2 <path>     set CMETA_HOME2 instead: the same home, except that an
                     activated virtual environment is still allowed to win
  --no-home          set neither; let cMeta resolve the home on its own
  --aops             also plug in the cmeta-aops automation repository
  --no-modify-path   do not touch PATH or any shell rc file
  --dry-run          print every command without running anything
  -q, --quiet        only report errors
  -h, --help         this text

What it needs:
  This directory must be a complete cMeta source tree - pyproject.toml,
  README.md, LICENSE, COPYRIGHT, NOTICE and the cmeta/ package. Plus network
  access to astral.sh (for uv) and PyPI (for the dependencies). Python is NOT
  required - uv fetches its own.

  If you copied this tree with a filter, make sure it took those five files
  and not just cmeta/ and pyproject.toml.

EOF
}

# ---------------------------------------------------------------- arguments

parse_args() {
    # "server" by default: cserver is a first-class part of cMeta, and without
    # this extra `cx app run cserver` cannot start at all - there is no uvicorn
    # to run it with, and a uv tool environment has no pip to add one later, so
    # the only cure is a reinstall. Drop it with --no-extras, or replace the
    # whole list with --extras.
    WITH_DEPS=0; EXTRAS="server"; EDITABLE=0
    HOME_DIR="$HOME/CMETA"; SET_HOME=1; HOME_VAR=CMETA_HOME; WANT_AOPS=0
    NO_MODIFY_PATH=0; QUIET=0; DRY_RUN=0

    while [ $# -gt 0 ]; do
        case "$1" in
            --with-deps)      WITH_DEPS=1 ;;
            -e|--editable)    EDITABLE=1 ;;
            --extras)         shift; [ $# -gt 0 ] || err "--extras needs a value"; EXTRAS="$1" ;;
            --extras=*)       EXTRAS="${1#*=}" ;;
            --no-extras)      EXTRAS="" ;;
            --home)           shift; [ $# -gt 0 ] || err "--home needs a value"
                              HOME_DIR="$1"; HOME_VAR=CMETA_HOME ;;
            --home=*)         HOME_DIR="${1#*=}"; HOME_VAR=CMETA_HOME ;;
            --home2)          shift; [ $# -gt 0 ] || err "--home2 needs a value"
                              HOME_DIR="$1"; HOME_VAR=CMETA_HOME2 ;;
            --home2=*)        HOME_DIR="${1#*=}"; HOME_VAR=CMETA_HOME2 ;;
            --no-home)        SET_HOME=0 ;;
            --aops)           WANT_AOPS=1 ;;
            --no-modify-path) NO_MODIFY_PATH=1 ;;
            --dry-run)        DRY_RUN=1 ;;
            -q|--quiet)       QUIET=1 ;;
            -h|--help)        usage; exit 0 ;;
            *)                err "unknown option: $1  (try --help)" ;;
        esac
        shift
    done
    return 0
}

# ---------------------------------------------------------------- source tree

# Resolve the directory this script lives in - that is what gets installed.
# Deliberately not $PWD: the point is that "sh /somewhere/install.sh" from any
# working directory installs /somewhere, never the current folder.
find_source() {
    local d
    d="$(dirname -- "$0")"
    SRC_DIR="$(CDPATH='' cd -- "$d" && pwd)" \
        || err "cannot resolve this script's directory from \"$0\""
    return 0
}

check_source() {
    local missing f
    missing=""

    for f in $REQUIRED_FILES; do
        [ -f "$SRC_DIR/$f" ] || missing="$missing $f"
    done
    [ -f "$SRC_DIR/cmeta/__init__.py" ] || missing="$missing cmeta/__init__.py"

    [ -z "$missing" ] && return 0

    err "this is not a complete cMeta source tree.
                   Directory: $SRC_DIR
                   Missing:  $missing

                   pyproject.toml points setuptools at README.md and at
                   LICENSE/COPYRIGHT/NOTICE, so the build needs all of them
                   even though they are not code. If you copied this tree with
                   a filter, widen it - with rclone, for example:

                     --whitelist=/cmeta/,/pyproject.toml,/README.md,/LICENSE,/COPYRIGHT,/NOTICE"
}

# ---------------------------------------------------------------- platform

detect_os() {
    OS_ID=unknown; OS_NAME=unknown

    case "$(uname -s)" in
        Darwin) OS_ID=macos; OS_NAME="macOS"; return 0 ;;
        Linux)  : ;;
        *)      err "unsupported platform: $(uname -s). Windows has install.ps1 / install.bat." ;;
    esac

    if [ -r /etc/os-release ]; then
        # shellcheck disable=SC1091
        . /etc/os-release
        OS_NAME="${PRETTY_NAME:-${NAME:-Linux}}"
        for id in ${ID:-} ${ID_LIKE:-}; do
            case "$id" in
                ubuntu|debian)               OS_ID=debian;   break ;;
                fedora)                      OS_ID=fedora;   break ;;
                rhel|centos|rocky|almalinux) OS_ID=rhel;     break ;;
                opensuse*|suse|sles)         OS_ID=opensuse; break ;;
                arch|archarm|manjaro)        OS_ID=arch;     break ;;
                alpine)                      OS_ID=alpine;   break ;;
            esac
        done
    fi

    if [ "$OS_ID" = unknown ]; then
        if   have apt-get; then OS_ID=debian
        elif have dnf;     then OS_ID=fedora
        elif have zypper;  then OS_ID=opensuse
        elif have pacman;  then OS_ID=arch
        elif have apk;     then OS_ID=alpine
        fi
    fi
    return 0
}

set_sudo() {
    SUDO=""
    [ "$(id -u)" = 0 ] && return 0
    if have sudo; then
        SUDO="sudo"
    else
        err "--with-deps needs root and neither sudo nor a root shell is available.
                   Re-run as root, or drop --with-deps and install git yourself."
    fi
    return 0
}

install_deps() {
    step "Installing system packages (git, curl)"
    set_sudo

    case "$OS_ID" in
        debian)
            run ${SUDO:+$SUDO} apt-get update
            run ${SUDO:+$SUDO} apt-get install -y git curl ca-certificates ;;
        fedora|rhel)
            run ${SUDO:+$SUDO} dnf install -y git curl ca-certificates ;;
        opensuse)
            run ${SUDO:+$SUDO} zypper --non-interactive install git curl ca-certificates ;;
        arch)
            run ${SUDO:+$SUDO} pacman -Sy --needed --noconfirm git curl ca-certificates ;;
        alpine)
            run ${SUDO:+$SUDO} apk add --no-cache git curl ca-certificates ;;
        macos)
            have brew || err "--with-deps on macOS needs Homebrew.
                   Install it from https://brew.sh and re-run, or drop
                   --with-deps: the Command Line Tools already provide git
                   (xcode-select --install)."
            run brew install git curl ;;
        *)
            err "--with-deps does not know this system's package manager.
                   Install git yourself, then re-run without --with-deps." ;;
    esac
    return 0
}

# ---------------------------------------------------------------- uv & cMeta

# uv's installer puts its binaries in $XDG_BIN_HOME or ~/.local/bin, and this
# shell needs them on PATH straight away because the next step calls uv.
use_local_bin() {
    for d in "${XDG_BIN_HOME:-}" "$HOME/.local/bin"; do
        [ -n "$d" ] || continue
        [ -d "$d" ] || continue
        case ":$PATH:" in
            *":$d:"*) ;;
            *) PATH="$d:$PATH"; export PATH ;;
        esac
    done
    return 0
}

install_uv() {
    if have uv; then
        step "uv is already installed ($(uv --version 2>/dev/null || echo unknown))"
        return 0
    fi
    step "Installing uv"
    if ! have curl; then
        if [ "$DRY_RUN" = 1 ]; then
            warn "curl is not installed - a real run needs it"
            [ "$WITH_DEPS" = 1 ] && say "     (--with-deps installs it in the step above)"
        else
            err "curl is required to fetch uv.
                   Install curl (or re-run with --with-deps) and try again."
        fi
    fi

    if [ "$NO_MODIFY_PATH" = 1 ]; then
        run_sh "curl -LsSf $UV_INSTALL_URL | env UV_NO_MODIFY_PATH=1 sh"
    else
        run_sh "curl -LsSf $UV_INSTALL_URL | sh"
    fi

    use_local_bin
    [ "$DRY_RUN" = 1 ] && return 0
    have uv || err "uv was installed but is not on PATH.
                   Open a new shell and re-run, or add \$HOME/.local/bin to PATH."
    return 0
}

install_cmeta() {
    step "Installing cMeta from $SRC_DIR"

    # With extras the argument becomes a PEP 508 "extras @ path" requirement,
    # because "uv tool install ./dir[server]" is read as a glob-ish name rather
    # than a path with extras.
    local target
    if [ -n "$EXTRAS" ]; then
        target="cmeta[$EXTRAS] @ $SRC_DIR"
    else
        target="$SRC_DIR"
    fi

    # --force so that re-running upgrades in place: the version in
    # cmeta/version.py does not change between local edits, and uv would
    # otherwise decide there is nothing to do.
    if [ "$EDITABLE" = 1 ]; then
        say "     (editable: the install keeps pointing at this directory)"
        run uv tool install --force --editable "$target"
    else
        run uv tool install --force "$target"
    fi

    if [ "$NO_MODIFY_PATH" = 1 ]; then
        say "     (skipping uv tool update-shell: --no-modify-path)"
    else
        run uv tool update-shell
    fi
    use_local_bin
    return 0
}

# ---------------------------------------------------------------- cMeta home

shell_rc() {
    case "${SHELL:-}" in
        */zsh)  printf '%s\n' "${ZDOTDIR:-$HOME}/.zshrc" ;;
        */bash) [ "$(uname -s)" = Darwin ] \
                    && printf '%s\n' "$HOME/.bash_profile" \
                    || printf '%s\n' "$HOME/.bashrc" ;;
        */fish) printf '%s\n' "$HOME/.config/fish/config.fish" ;;
        *)      printf '%s\n' "$HOME/.profile" ;;
    esac
}

set_home() {
    if [ "$SET_HOME" = 0 ]; then
        step "Leaving CMETA_HOME unset (--no-home)"
        say "     cMeta will resolve it: an active venv wins, else ~/CMETA."
        return 0
    fi

    step "Pointing cMeta at $HOME_DIR via $HOME_VAR"
    if [ "$HOME_VAR" = CMETA_HOME ]; then
        say "     A global command does not imply a global home: with CMETA_HOME"
        say "     unset, an activated virtual environment captures it instead."
    else
        say "     CMETA_HOME2 is the fallback home: an activated virtual"
        say "     environment still takes precedence over it."
    fi
    export "$HOME_VAR=$HOME_DIR"

    [ "$NO_MODIFY_PATH" = 1 ] && {
        say "     (not written to any rc file: --no-modify-path)"
        return 0
    }

    local rc line
    rc="$(shell_rc)"
    case "$rc" in
        */config.fish) line="set -gx $HOME_VAR \"$HOME_DIR\"" ;;
        *)             line="export $HOME_VAR=\"$HOME_DIR\"" ;;
    esac

    if [ -r "$rc" ] && grep -qF "$HOME_VAR" "$rc" 2>/dev/null; then
        say "     $rc already mentions $HOME_VAR - leaving it alone"
        return 0
    fi
    say "     \$ echo '$line' >> $rc"
    [ "$DRY_RUN" = 1 ] && return 0
    mkdir -p "$(dirname "$rc")" 2>/dev/null || true
    printf '\n# cMeta - where repositories, the index and caches live\n%s\n' \
        "$line" >> "$rc"
    return 0
}

# ---------------------------------------------------------------- content

add_repos() {
    [ "$WANT_AOPS" = 1 ] || return 0
    step "Adding the cmeta-aops automation repository"
    have git || {
        warn "git is not installed, so cx repo get cannot clone. Skipping.
                   Install git (or re-run with --with-deps) and then:
                       cx repo get $AOPS_REF"
        return 0
    }
    run cx repo get "$AOPS_REF"
    return 0
}

# ---------------------------------------------------------------- verify

verify() {
    step "Verifying"
    if [ "$DRY_RUN" = 1 ]; then
        say "     \$ cx --version"
        return 0
    fi
    have cx || err "cMeta installed but 'cx' is not on PATH.
                   Open a new shell, or add \$HOME/.local/bin to PATH."
    if [ "$QUIET" = 1 ]; then
        cx --version >/dev/null 2>&1 || err "'cx --version' failed."
    else
        cx --version || err "'cx --version' failed."
    fi

    have git || warn "git is not installed. cMeta works, but 'cx repo get' needs
                   git to clone content repositories. Install it with your
                   package manager, or re-run this script with --with-deps."
    return 0
}

epilogue() {
    [ "$QUIET" = 1 ] && return 0
    cat <<EOF

cMeta is installed from $SRC_DIR

  Open a new shell (so PATH and CMETA_HOME are picked up), then:

    cx --version                 # prints the version and the home it resolved
    cx repo list                 # what is plugged in
    cx repo get $AOPS_REF   # the reference automation repository

  Re-copy this tree and re-run this script to update.
  Remove it with:  uv tool uninstall cmeta

  Docs: https://github.com/cTuningLabs/cmeta/blob/main/docs/installation.md
EOF
    return 0
}

# ---------------------------------------------------------------- main

main() {
    parse_args "$@"
    find_source
    check_source
    detect_os

    step "cMeta installer - $OS_NAME - source: $SRC_DIR"
    [ "$DRY_RUN" = 1 ] && say "     (dry run: nothing will be changed)"

    [ "$WITH_DEPS" = 1 ] && install_deps
    install_uv
    install_cmeta
    set_home
    add_repos
    verify
    epilogue
    return 0
}

main "$@"

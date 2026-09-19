#!/usr/bin/env bash
# Helper: run from anywhere, e.g.  ./run.sh test | ./run.sh find | ./run.sh position 123 --quote | ./run.sh serve
cd "$(dirname "$0")" || exit 1
case "$1" in
  test) shift; python3 -m unittest discover -s tests -v "$@" ;;
  *) python3 -m lpval "$@" ;;
esac

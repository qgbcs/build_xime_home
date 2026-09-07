#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

./git.py https://github.com/775cpu/build_xime_home.git --branch main pull

./git.py clone --depth=1 https://github.com/775cpu/Xime_rpc

cd Xime_rpc
#git submodule update --init --recursive
echo 第一次执行耗时约8分钟，后续执行耗时约几秒钟
./build.sh "$@"


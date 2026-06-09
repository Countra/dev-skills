#!/usr/bin/env sh
set -eu

usage() {
  cat <<'EOF'
用法：
  ./skill.sh install <target-skills-dir>

示例：
  ./skill.sh install "$HOME/.codex/skills"

说明：
  - 源码 skill 位于 ./skills。
  - 本脚本把 skill 复制到目标 skills 目录。
  - 本脚本不会创建 .harness 运行时任务文件。
EOF
}

if [ "${1:-}" != "install" ] || [ -z "${2:-}" ]; then
  usage
  exit 2
fi

target=$2
src_dir="skills"

if [ ! -d "$src_dir" ]; then
  echo "缺少源码 skills 目录：$src_dir" >&2
  exit 1
fi

mkdir -p "$target"
cp -R "$src_dir/complex-coding-harness" "$target/"

echo "已安装 complex-coding-harness 到 $target/complex-coding-harness"

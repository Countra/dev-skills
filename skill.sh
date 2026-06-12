#!/usr/bin/env sh
set -eu

usage() {
  cat <<'EOF'
用法：
  ./skill.sh install [--force] <target-skills-dir>

示例：
  ./skill.sh install "$HOME/.codex/skills"
  ./skill.sh install --force "$HOME/.codex/skills"

说明：
  - 源码 skill 位于 ./skills/。
  - 目标 skill 已存在时默认拒绝覆盖。
  - 使用 --force 时只替换目标目录下同名 skill。
  - 本脚本不会创建 .harness 运行时任务文件。
EOF
}

if [ "${1:-}" != "install" ]; then
  usage
  exit 2
fi

shift

force=0
if [ "${1:-}" = "--force" ]; then
  force=1
  shift
fi

if [ "$#" -ne 1 ] || [ -z "${1:-}" ]; then
  usage
  exit 2
fi

target=$1

if [ "$target" = "/" ]; then
  echo "拒绝安装到根目录：$target" >&2
  exit 1
fi

if [ ! -d "skills" ]; then
  echo "缺少源码 skills 目录" >&2
  exit 1
fi

mkdir -p "$target"

for src_dir in skills/*; do
  [ -d "$src_dir" ] || continue
  skill_name=$(basename "$src_dir")
  dest="$target/$skill_name"

  if [ ! -f "$src_dir/SKILL.md" ]; then
    echo "跳过非 skill 目录：$src_dir" >&2
    continue
  fi

  if [ -e "$dest" ]; then
    if [ "$force" -ne 1 ]; then
      echo "目标 skill 已存在：$dest" >&2
      echo "如需替换，请使用：./skill.sh install --force <target-skills-dir>" >&2
      exit 1
    fi

    case "$dest" in
      ""|"/"|".")
        echo "拒绝删除不安全目标：$dest" >&2
        exit 1
        ;;
      */"$skill_name"|"$skill_name")
        ;;
      *)
        echo "拒绝删除非预期 skill 目录：$dest" >&2
        exit 1
        ;;
    esac

    rm -rf "$dest"
  fi

  cp -R "$src_dir" "$dest"

  if [ ! -f "$dest/SKILL.md" ]; then
    echo "安装校验失败，缺少目标文件：$dest/SKILL.md" >&2
    exit 1
  fi

  echo "已安装 $skill_name 到 $dest"
done

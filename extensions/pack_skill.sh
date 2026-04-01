#!/bin/bash
# 将 skills/ 下的指定 skill 打包为 ZIP 压缩包（可直接通过 Web 上传）
#
# 用法：
#   ./pack_skill.sh <skill_name>    打包单个 skill（自动在 s1/s2 下搜索）
#   ./pack_skill.sh -all            打包所有 skills
#
# 输出：当前目录下的 <skill_name>.zip

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILLS_DIR="$SCRIPT_DIR/skills"

find_skill() {
    local SKILL_NAME="$1"
    for SUB_DIR in "$SKILLS_DIR"/*/; do
        if [ -d "$SUB_DIR$SKILL_NAME" ]; then
            echo "$SUB_DIR$SKILL_NAME"
            return 0
        fi
    done
    return 1
}

pack_one() {
    local SKILL_NAME="$1"
    local SKILL_PATH

    SKILL_PATH=$(find_skill "$SKILL_NAME") || {
        echo "错误: skill '$SKILL_NAME' 不存在（已搜索 s1/s2 子目录）"
        return 1
    }

    if [ ! -f "$SKILL_PATH/SKILL.md" ]; then
        echo "错误: skill '$SKILL_NAME' 缺少 SKILL.md"
        return 1
    fi

    local OUTPUT="$SCRIPT_DIR/$SKILL_NAME.zip"

    python3 -c "
import zipfile, os, sys
skill = sys.argv[1]
src = sys.argv[2]
out = sys.argv[3]
with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as zf:
    for root, dirs, files in os.walk(src):
        for f in files:
            full = os.path.join(root, f)
            arcname = os.path.join(skill, os.path.relpath(full, src))
            zf.write(full, arcname)
print(f'已打包: {os.path.basename(out)}')
" "$SKILL_NAME" "$SKILL_PATH" "$OUTPUT"
}

if [ -z "$1" ]; then
    echo "用法: $0 <skill_name>    打包单个 skill"
    echo "      $0 -all            打包所有 skills"
    echo ""
    echo "可用的 skills:"
    for SUB_DIR in "$SKILLS_DIR"/*/; do
        for SKILL_DIR in "$SUB_DIR"*/; do
            [ -f "$SKILL_DIR/SKILL.md" ] && echo "  $(basename "$SKILL_DIR")  ($(basename "$SUB_DIR"))"
        done
    done
    exit 1
fi

if [ "$1" = "-all" ]; then
    echo "打包所有 skills..."
    for SUB_DIR in "$SKILLS_DIR"/*/; do
        for SKILL_DIR in "$SUB_DIR"*/; do
            SKILL_NAME="$(basename "$SKILL_DIR")"
            [ -f "$SKILL_DIR/SKILL.md" ] && pack_one "$SKILL_NAME" || true
        done
    done
    echo "全部完成!"
else
    pack_one "$1"
fi

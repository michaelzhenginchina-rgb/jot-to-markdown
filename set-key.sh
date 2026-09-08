#!/bin/bash
# Store an Anthropic API key for the 生词 lookups. Reads it without echoing,
# writes it to <store>/.jot-api-key, and never prints it back.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STORE="${JOT_STORE:-$( [ -f "$HERE/.jot-store" ] && cat "$HERE/.jot-store" || echo "$HOME/highlights" )}"
KEYFILE="$STORE/.jot-api-key"

if [ ! -d "$STORE" ]; then
  echo "找不到 store 目录:$STORE" >&2
  echo "先跑一次 ./install.sh" >&2
  exit 1
fi

echo "把 API key 粘进来（不会显示，粘完直接回车）："
IFS= read -rs KEY
echo

if [ -z "${KEY:-}" ]; then
  echo "没输入内容，什么都没改。" >&2
  exit 1
fi

case "$KEY" in
  sk-ant-*) PROVIDER="Anthropic (Claude)" ;;
  sk-*)     PROVIDER="OpenAI" ;;
  *) echo "不认识这个格式（应以 sk-ant- 或 sk- 开头）。没保存。" >&2; exit 1 ;;
esac

umask 077
printf '%s\n' "$KEY" > "$KEYFILE"
chmod 600 "$KEYFILE"
unset KEY

echo "识别为：$PROVIDER"
echo "已保存到 $KEYFILE（权限 600，只有你能读）"
echo "重启服务让它生效..."
launchctl kickstart -k "gui/$(id -u)/com.jot.server" 2>/dev/null || true

for _ in $(seq 1 20); do
  if curl -fsS "http://127.0.0.1:${JOT_PORT:-7777}/ping" >/dev/null 2>&1; then
    echo "服务已就绪。现在划中一个英文词 → 右键 → 存为生词，几秒后释义会自己出现。"
    exit 0
  fi
  sleep 0.3
done
echo "服务没起来，看看 $STORE/.jot.log" >&2
exit 1

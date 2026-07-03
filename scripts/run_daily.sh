#!/bin/zsh
# 每日交易所监控（供 launchd 调用）。
# 计划：10:00 跑一次；11:00 仅在「当天尚未成功」时补跑一次。
# 成功判定 = python -m exchange_monitor 退出码 0（全部交易所抓取失败会退出 1）。
# 成功后把当天日期写入 marker；11:00 见到 marker=今天就跳过。

source "$HOME/.zshrc" 2>/dev/null   # 取 SLACK_WEBHOOK_URL（保持密钥在 ~/.zshrc，不入库）

PROJ="$(cd "$(dirname "$0")/.." && pwd)"
# 直接用 venv 的 python，绕过 `uv run`：uv run 每次会校验/同步依赖（会访问网络），
# 刚唤醒网络冷启动时曾卡住约 28 分钟。venv python 不碰网络、瞬时启动。
# （依赖变动后需手动 `uv sync` 一次。）
PY="$PROJ/.venv/bin/python"
MARKER="$HOME/.exchange_monitor_last_success"
LOG="$HOME/exchange_monitor_daily.log"
TODAY="$(date +%F)"

cd "$PROJ" || { echo "$(date '+%F %T') 无法进入 $PROJ" >> "$LOG"; exit 1; }

# 当天已成功 → 跳过（这样 11:00 只在 10:00 未成功时才真正跑）
if [ "$(cat "$MARKER" 2>/dev/null)" = "$TODAY" ]; then
  echo "$(date '+%F %T') 今日已成功，跳过本次触发" >> "$LOG"
  exit 0
fi

echo "$(date '+%F %T') === 开始运行 ===" >> "$LOG"
"$PY" -m exchange_monitor >> "$LOG" 2>&1
code=$?
if [ "$code" -eq 0 ]; then
  echo "$TODAY" > "$MARKER"
  echo "$(date '+%F %T') 成功 (exit 0)" >> "$LOG"
else
  echo "$(date '+%F %T') 失败 (exit $code)；若为 10:00，将在 11:00 重试" >> "$LOG"
fi
exit "$code"

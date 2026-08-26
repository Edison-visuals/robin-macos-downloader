#!/bin/bash
# Robin — 打包成 .dmg 安裝檔
set -e
cd "$(dirname "$0")"

APP="Robin.app"
NAME="Robin"
VOL="Robin"
OUT="$NAME.dmg"
STAGE="/tmp/robin_dmg_stage"

if [ ! -d "$APP" ]; then
  echo "找不到 $APP,請把這個腳本放在與 Robin.app 同一層資料夾"
  read -n 1 -s -r -p "按任意鍵關閉…"
  exit 1
fi

echo "→ 準備檔案…"
rm -rf "$STAGE" "$OUT"
mkdir -p "$STAGE"
cp -R "$APP" "$STAGE/"
rm -rf "$STAGE/$APP/Contents/Resources/__pycache__"
ln -s /Applications "$STAGE/Applications"

# 附上簡短說明
cat > "$STAGE/README-FIRST.txt" <<'EOF'
Robin — 影片 / 音訊下載器

安裝:
1. 把 Robin 拖進左邊的 Applications 資料夾
2. 首次開啟請對 Robin 按右鍵 →「打開」(未簽名 app,只需這樣做一次)
3. 首次啟動會自動安裝元件,約一分鐘

需求:
- ffmpeg(高畫質合併與音訊轉檔必需)
  終端機執行:brew install ffmpeg

檔案預設存到 ~/Downloads,可在 app 的 SETTINGS 頁更改。
請只下載你有權利下載的內容。
EOF

echo "→ 建立 DMG…"
hdiutil create -volname "$VOL" \
  -srcfolder "$STAGE" \
  -ov -format UDZO \
  -fs HFS+ \
  "$OUT" >/dev/null

rm -rf "$STAGE"

SIZE=$(du -h "$OUT" | cut -f1)
echo ""
echo "✓ 完成:$(pwd)/$OUT  ($SIZE)"
echo ""
if [ -t 0 ]; then
  open -R "$OUT"
  read -n 1 -s -r -p "按任意鍵關閉…"
fi

#!/bin/bash
# ~/Applications/집찾기.app 을 만들어 Launchpad·Dock에서 바로 열 수 있게 한다.
# 앱은 이 폴더의 코드를 실행하므로, 폴더를 옮기면 이 스크립트를 다시 실행하세요.
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
APP="$HOME/Applications/집찾기.app"

# 패키지를 먼저 설치해 둔다 (앱으로 열면 설치 과정이 보이지 않으므로)
cd "$HERE"
if [ ! -f .venv/.installed ]; then
  ./run.command --help >/dev/null
fi

rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS"
cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>집찾기</string>
  <key>CFBundleDisplayName</key><string>집찾기</string>
  <key>CFBundleIdentifier</key><string>local.landfinder</string>
  <key>CFBundleVersion</key><string>0.1.0</string>
  <key>CFBundleExecutable</key><string>LandFinder</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>LSMinimumSystemVersion</key><string>11.0</string>
  <key>NSHighResolutionCapable</key><true/>
</dict>
</plist>
PLIST
cat > "$APP/Contents/MacOS/LandFinder" <<LAUNCHER
#!/bin/bash
mkdir -p "\$HOME/Library/Logs"
cd "$HERE" && exec ./run.command >> "\$HOME/Library/Logs/LandFinder.log" 2>&1
LAUNCHER
chmod +x "$APP/Contents/MacOS/LandFinder"
echo "만들었습니다: $APP"
echo "Finder > 응용 프로그램(사용자) 또는 Launchpad에서 '집찾기'를 여세요."

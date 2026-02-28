#!/bin/bash
# setup_cron.sh — Oracle idle 방지 cron 설정 스크립트
# 서버에서 한 번만 실행하면 됩니다.
#
# 사용법:
#   chmod +x setup_cron.sh
#   sudo ./setup_cron.sh
#
# 결과:
#   /etc/cron.d/dummy-load 파일 생성
#   5분마다 290초(4분 50초)간 nice md5sum /dev/zero 실행

set -e

CRON_FILE="/etc/cron.d/dummy-load"

echo "[1/3] cron 파일 생성: $CRON_FILE"
echo "*/5 * * * * root timeout 290 nice md5sum /dev/zero" | sudo tee "$CRON_FILE" > /dev/null
sudo chmod 644 "$CRON_FILE"

echo "[2/3] cron 파일 내용 확인:"
cat "$CRON_FILE"

echo "[3/3] cron 서비스 재시작..."
sudo systemctl restart cron 2>/dev/null || sudo service cron restart 2>/dev/null || true

echo ""
echo "완료! cron idle 방지 작업이 등록되었습니다."
echo ""
echo "동작 방식:"
echo "  - 5분마다 md5sum /dev/zero 실행 (290초 = 4분 50초)"
echo "  - nice 로 낮은 우선순위 실행 → 실제 서비스에 영향 없음"
echo "  - CPU 사용률 목표: 7일 평균 95th percentile >= 20%"
echo ""
echo "확인 명령어:"
echo "  cat $CRON_FILE"
echo "  pgrep -a md5sum"

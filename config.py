import os
from dotenv import load_dotenv

load_dotenv()

# Discord 설정
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "")
MONITOR_CHANNEL_ID = int(os.getenv("MONITOR_CHANNEL_ID", "0"))

# 모니터링 설정
MONITOR_INTERVAL_SECONDS = 10  # 10초마다 보고

# 홈서버 정보 (표시용)
INSTANCE_NAME = os.getenv("INSTANCE_NAME", "ASUS PN40 홈서버")
INSTANCE_SHAPE = "Intel J4125 (4코어)"
TOTAL_CPU = 4      # 코어
TOTAL_RAM_GB = 4   # GB (추후 8GB 확장 예정)

# 임계값 (이 이상이면 경고 색상)
CPU_WARN_THRESHOLD = 80     # %
MEM_WARN_THRESHOLD = 80     # %
DISK_WARN_THRESHOLD = 85    # %

# 알림 임계값 (이 이상이면 @here 알림 전송)
CPU_ALERT_THRESHOLD  = 90       # %
DISK_ALERT_THRESHOLD = 50       # %
NET_ALERT_THRESHOLD_KB = 10 * 1024  # KB/s (10 MB/s)

# 임베드 색상
COLOR_NORMAL = 0x2ECC71   # 초록
COLOR_WARN   = 0xE67E22   # 주황
COLOR_CRIT   = 0xE74C3C   # 빨강
COLOR_INFO   = 0x3498DB   # 파랑

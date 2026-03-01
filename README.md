# discord-bot24

오라클 클라우드 무료 인스턴스(VM.Standard.A1.Flex, ARM64)의 시스템 리소스를 Discord 채널에 보고하는 모니터링 봇입니다.

## 구성 요소

| 파일 | 역할 |
|------|------|
| `bot.py` | 시스템 모니터링 봇 (10초 주기, Embed edit 방식) |
| `cpu_bot.py` | CPU / 메모리 상위 프로세스 모니터링 봇 (5분 주기) |

---

## 1. 시스템 모니터링 봇 (`bot.py`)

- CPU / 메모리 / 디스크 / 네트워크 사용량을 **10초마다** Embed edit
- **10분 이동평균** 표시
- 임계값 초과 시 `@here` 경고 알림, 회복 시 정상화 알림
- 재시작해도 메시지 누적 없음 (채널 히스토리에서 이전 메시지 복구)

### 알림 임계값

| 항목 | 경고 색상 | @here 알림 | 설정 위치 |
|------|-----------|------------|-----------|
| CPU | 80% | 90% | `config.py` |
| 디스크 | 85% | 50% | `config.py` |
| 네트워크 | — | 10 MB/s | `config.py` |

---

## 2. 프로세스 모니터링 봇 (`cpu_bot.py`)

- CPU / 메모리 사용량 **상위 5개 프로세스**를 5분마다 Embed edit
- 1위 프로세스가 50% 이상이면 주황색으로 표시
- 재시작해도 메시지 누적 없음

---

## 3. Oracle idle 판정 기준 (참고)

Oracle은 7일간 아래 세 조건을 **모두** 충족하면 Always Free 인스턴스를 회수합니다:

- CPU 95th percentile < **20%**
- 네트워크 < **20%**
- 메모리 < **20%** (A1 Flex 전용)

세 조건이 AND이므로 **CPU만 20% 이상 유지하면 회수되지 않습니다.**

---

## 파일 구조

```
discord-bot24/
├── bot.py                  # 시스템 모니터링 봇
├── cpu_bot.py              # 프로세스 모니터링 봇
├── config.py               # 설정값 및 임계값
├── system_info.py          # psutil 기반 시스템 정보 수집
├── oracle-monitor.service  # systemd 서비스 (bot.py)
├── cpu-bot.service         # systemd 서비스 (cpu_bot.py)
├── requirements.txt        # Python 의존성
└── .env.example            # 환경변수 템플릿
```

---

## 설치 및 배포

### 1. 레포 클론

```bash
git clone https://github.com/seonggyujo/discord-bot24.git
cd discord-bot24
```

### 2. 의존성 설치

```bash
pip install -r requirements.txt
```

### 3. 환경변수 설정

```bash
cp .env.example .env
nano .env
```

`.env` 내용:

```
DISCORD_BOT_TOKEN=디스코드_봇_토큰
MONITOR_CHANNEL_ID=채널_ID
INSTANCE_NAME=Oracle Cloud (ARM64)

CPU_BOT_TOKEN=프로세스_모니터_봇_토큰
CPU_CHANNEL_ID=채널_ID
```

### 4. systemd 등록

```bash
# 시스템 모니터링 봇
sudo cp oracle-monitor.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable oracle-monitor
sudo systemctl start oracle-monitor

# 프로세스 모니터링 봇
sudo cp cpu-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable cpu-bot
sudo systemctl start cpu-bot
```

### 5. 상태 확인

```bash
sudo systemctl status oracle-monitor cpu-bot
sudo journalctl -u oracle-monitor -f
sudo journalctl -u cpu-bot -f
```

---

## 업데이트 배포

```bash
cd ~/discord-bot24
git pull
sudo systemctl restart oracle-monitor cpu-bot
```

---

## 기술 스택

| 항목 | 내용 |
|------|------|
| Runtime | Python 3.10 |
| Discord | discord.py >= 2.3.0 |
| 시스템 정보 | psutil >= 5.9.0 |
| HTTP | aiohttp >= 3.9.0 |
| 환경변수 | python-dotenv >= 1.0.0 |
| 프로세스 관리 | systemd |
| 서버 | Oracle Cloud VM.Standard.A1.Flex (ARM64, 4 OCPU, 24GB) |

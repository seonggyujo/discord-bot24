# discord-bot24

오라클 클라우드 무료 인스턴스(VM.Standard.A1.Flex, ARM64)의 시스템 리소스를 1분마다 Discord 채널에 보고하는 모니터링 봇입니다.

## 기능

- CPU, 메모리, 디스크, 네트워크 사용량을 1분마다 Embed 메시지로 전송
- 리소스가 임계값을 초과하면 `@here` 경고 알림 전송
- 임계값 아래로 회복되면 정상화 알림 전송
- 경고 상태가 지속돼도 반복 알림 없음 (상태 변경 시에만 전송)

## 알림 임계값

| 항목 | 기본값 | 설정 위치 |
|------|--------|-----------|
| CPU | 50% | `config.py` `CPU_ALERT_THRESHOLD` |
| 디스크 | 50% | `config.py` `DISK_ALERT_THRESHOLD` |
| 네트워크 수신/송신 | 10 MB/s | `config.py` `NET_ALERT_THRESHOLD_KB` |

## 기술 스택

| 항목 | 내용 |
|------|------|
| Runtime | Python 3.10 |
| Discord | discord.py >= 2.3.0 |
| 시스템 정보 | psutil >= 5.9.0 |
| HTTP | aiohttp >= 3.9.0 |
| 환경변수 | python-dotenv >= 1.0.0 |
| 프로세스 관리 | systemd |

## 파일 구조

```
discord-bot24/
├── bot.py                  # 메인 봇 (1분 루프, Embed 전송, 알림 로직)
├── config.py               # 설정값 및 임계값
├── system_info.py          # psutil 기반 시스템 정보 수집
├── requirements.txt        # Python 의존성
├── .env.example            # 환경변수 템플릿
├── .env                    # 실제 환경변수 (git 제외)
└── oracle-monitor.service  # systemd 서비스 파일
```

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
```

- **DISCORD_BOT_TOKEN**: [Discord Developer Portal](https://discord.com/developers/applications) → Bot → Reset Token
- **MONITOR_CHANNEL_ID**: 디스코드 개발자 모드 ON → 채널 우클릭 → ID 복사

### 4. systemd 등록

```bash
sudo cp oracle-monitor.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable oracle-monitor
sudo systemctl start oracle-monitor
```

### 5. 상태 확인

```bash
sudo systemctl status oracle-monitor
sudo journalctl -u oracle-monitor -f
```

## 업데이트 배포

```bash
cd ~/discord-bot24
git pull origin main
sudo systemctl restart oracle-monitor
```

## 디스코드 출력 예시

```
✅ Oracle Cloud (ARM64) 시스템 모니터
VM.Standard.A1.Flex | 업타임: 121일 5시간 13분

CPU
██░░░░░░░░  21.3%
코어별: 18% / 24% / 19% / 24%

메모리 (RAM)              스왑
███░░░░░░░  28.5%         ░░░░░░░░░░  0.0%
6.8 GB / 24.0 GB          0.0 GB / 0.0 GB

디스크 (/)                네트워크
██░░░░░░░░  26.5%         수신 ↓ 12.3 KB/s
11.9 GB / 45.0 GB         송신 ↑ 4.1 KB/s
```

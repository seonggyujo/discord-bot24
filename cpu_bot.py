"""
cpu_bot.py — Oracle idle 방지 cron 모니터링 봇
/etc/cron.d/dummy-load 의 실행 상태를 주기적으로 Discord에 보고합니다.

cron 설정 예시:
  echo "*/5 * * * * root timeout 290 nice md5sum /dev/zero" | sudo tee /etc/cron.d/dummy-load

실행: python cpu_bot.py
"""

import asyncio
import logging
import os
import subprocess
from datetime import datetime, timezone, timedelta

import discord
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("cpu-bot")

KST = timezone(timedelta(hours=9))

# ── 환경변수 ──────────────────────────────────────────────
CPU_BOT_TOKEN  = os.getenv("CPU_BOT_TOKEN", "")
CPU_CHANNEL_ID = int(os.getenv("CPU_CHANNEL_ID", "0"))

# 보고 주기 (초) — 10분마다 한 번
REPORT_INTERVAL = 10 * 60

# cron 파일 경로
CRON_FILE = "/etc/cron.d/dummy-load"
# cron이 실행하는 명령어 키워드
CRON_PROCESS_KEYWORD = "md5sum"

# ── 임베드 색상 ───────────────────────────────────────────
COLOR_OK   = 0x2ECC71   # 초록 — cron 정상 동작
COLOR_WARN = 0xE67E22   # 주황 — cron 파일 있지만 프로세스 없음
COLOR_ERR  = 0xE74C3C   # 빨강 — cron 파일 없음


# ══════════════════════════════════════════════════════════
# 시스템 정보 수집 (블로킹, 별도 스레드에서 호출)
# ══════════════════════════════════════════════════════════

def _check_cron_file() -> bool:
    """cron 파일이 존재하는지 확인"""
    return os.path.isfile(CRON_FILE)


def _read_cron_file() -> str:
    """cron 파일 내용 반환 (없으면 빈 문자열)"""
    try:
        with open(CRON_FILE, "r") as f:
            return f.read().strip()
    except Exception:
        return ""


def _check_cron_process() -> int:
    """현재 실행 중인 md5sum 프로세스 수 반환"""
    try:
        result = subprocess.run(
            ["pgrep", "-c", CRON_PROCESS_KEYWORD],
            capture_output=True, text=True, timeout=5
        )
        count = result.stdout.strip()
        return int(count) if count.isdigit() else 0
    except Exception:
        return 0


def _get_cpu_percent() -> float:
    """현재 전체 CPU 사용률 반환 (psutil)"""
    try:
        import psutil
        return psutil.cpu_percent(interval=1)
    except Exception:
        return -1.0


def _get_load_avg() -> tuple[float, float, float]:
    """1분 / 5분 / 15분 load average 반환"""
    try:
        load = os.getloadavg()
        return load[0], load[1], load[2]
    except Exception:
        return (-1.0, -1.0, -1.0)


def collect_status() -> dict:
    """모든 상태 정보를 수집해 dict로 반환"""
    cron_exists  = _check_cron_file()
    cron_content = _read_cron_file() if cron_exists else ""
    proc_count   = _check_cron_process()
    cpu_pct      = _get_cpu_percent()
    load1, load5, load15 = _get_load_avg()

    return {
        "cron_exists":   cron_exists,
        "cron_content":  cron_content,
        "proc_count":    proc_count,
        "cpu_pct":       cpu_pct,
        "load1":         load1,
        "load5":         load5,
        "load15":        load15,
    }


# ══════════════════════════════════════════════════════════
# Discord Embed 빌더
# ══════════════════════════════════════════════════════════

def build_embed(s: dict) -> discord.Embed:
    now_kst = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S KST")

    # 상태 판정
    if not s["cron_exists"]:
        color  = COLOR_ERR
        status = "❌ cron 파일 없음"
        desc   = f"`{CRON_FILE}` 가 존재하지 않습니다.\n서버에서 아래 명령어로 설정하세요:"
    elif s["proc_count"] == 0:
        color  = COLOR_WARN
        status = "⚠️ cron 등록됨 / 현재 프로세스 없음"
        desc   = f"`{CRON_FILE}` 파일은 있지만 `{CRON_PROCESS_KEYWORD}` 프로세스가 실행 중이 아닙니다.\n(5분 주기 cron — 대기 중일 수 있습니다)"
    else:
        color  = COLOR_OK
        status = f"✅ cron 실행 중 ({s['proc_count']}개 프로세스)"
        desc   = f"`{CRON_PROCESS_KEYWORD}` 프로세스가 **{s['proc_count']}개** 실행 중입니다."

    embed = discord.Embed(
        title=f"🔧 Oracle idle 방지 — {status}",
        description=desc,
        color=color,
        timestamp=datetime.now(timezone.utc),
    )

    # cron 파일 내용
    if s["cron_exists"] and s["cron_content"]:
        embed.add_field(
            name="cron 설정",
            value=f"```\n{s['cron_content']}\n```",
            inline=False,
        )
    elif not s["cron_exists"]:
        embed.add_field(
            name="설정 방법",
            value=(
                "```bash\n"
                'echo "*/5 * * * * root timeout 290 nice md5sum /dev/zero" \\\n'
                "  | sudo tee /etc/cron.d/dummy-load\n"
                "```"
            ),
            inline=False,
        )

    # CPU 현황
    cpu_str = f"{s['cpu_pct']:.1f}%" if s["cpu_pct"] >= 0 else "측정 불가"
    load_str = (
        f"{s['load1']:.2f} / {s['load5']:.2f} / {s['load15']:.2f}"
        if s["load1"] >= 0 else "측정 불가"
    )
    embed.add_field(
        name="현재 CPU 상태",
        value=(
            f"사용률: **{cpu_str}**\n"
            f"Load avg (1 / 5 / 15분): **{load_str}**"
        ),
        inline=False,
    )

    # Oracle idle 기준 안내
    embed.add_field(
        name="Oracle idle 판정 기준 (A1 Flex)",
        value=(
            "7일 평균, 아래 세 조건 **모두** 충족 시 회수 대상:\n"
            "• CPU 95th percentile < **20%**\n"
            "• 네트워크 < **20%**\n"
            "• 메모리 < **20%**"
        ),
        inline=False,
    )

    embed.set_footer(text=now_kst)
    return embed


# ══════════════════════════════════════════════════════════
# Discord 봇
# ══════════════════════════════════════════════════════════

class CronMonitorBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(intents=intents)
        self._status_message: discord.Message | None = None

    async def setup_hook(self):
        self.loop.create_task(self._report_loop())

    async def on_ready(self):
        log.info(f"cron 모니터 봇 로그인 완료: {self.user} (ID: {self.user.id})")
        log.info(f"채널 ID: {CPU_CHANNEL_ID} | 보고 주기: {REPORT_INTERVAL // 60}분")
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="cron idle 방지 작업"
            )
        )
        # 재시작 후 이전 상태 메시지를 찾아 재사용 (메시지 누적 방지)
        await self._recover_status_message()

    async def _recover_status_message(self):
        """채널 최근 메시지에서 봇이 보낸 embed 메시지를 찾아 _status_message로 복구"""
        channel = self.get_channel(CPU_CHANNEL_ID)
        if channel is None:
            return
        try:
            async for msg in channel.history(limit=20):
                if msg.author.id == self.user.id and msg.embeds:
                    self._status_message = msg
                    log.info(f"이전 상태 메시지 복구: {msg.id}")
                    return
        except Exception as e:
            log.warning(f"메시지 복구 실패: {e}")

    async def _report_loop(self):
        await self.wait_until_ready()

        # 시작 직후 첫 보고
        await asyncio.sleep(5)

        while not self.is_closed():
            await self._send_report()
            await asyncio.sleep(REPORT_INTERVAL)

    async def _send_report(self):
        channel = self.get_channel(CPU_CHANNEL_ID)
        if channel is None:
            log.warning(f"채널을 찾을 수 없습니다: {CPU_CHANNEL_ID}")
            return

        try:
            loop = asyncio.get_event_loop()
            status = await loop.run_in_executor(None, collect_status)
            embed  = build_embed(status)

            if self._status_message is None:
                self._status_message = await channel.send(embed=embed)
            else:
                try:
                    await self._status_message.edit(embed=embed)
                except discord.NotFound:
                    self._status_message = await channel.send(embed=embed)

            log.info(
                f"보고 완료 | cron_exists={status['cron_exists']} "
                f"proc_count={status['proc_count']} "
                f"cpu={status['cpu_pct']:.1f}% "
                f"load={status['load1']:.2f}"
            )

        except Exception as e:
            log.error(f"보고 오류: {e}", exc_info=True)


def main():
    if not CPU_BOT_TOKEN:
        log.error("CPU_BOT_TOKEN 환경변수가 설정되지 않았습니다.")
        return
    if CPU_CHANNEL_ID == 0:
        log.error("CPU_CHANNEL_ID 환경변수가 설정되지 않았습니다.")
        return

    bot = CronMonitorBot()
    bot.run(CPU_BOT_TOKEN, log_handler=None)


if __name__ == "__main__":
    main()

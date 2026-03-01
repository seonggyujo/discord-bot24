"""
cpu_bot.py — 상위 프로세스 모니터링 봇
CPU / 메모리 사용량 상위 프로세스를 주기적으로 Discord에 보고합니다.

실행: python cpu_bot.py
"""

import asyncio
import logging
import os
from datetime import datetime, timezone, timedelta

import discord
import psutil
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("proc-monitor")

KST = timezone(timedelta(hours=9))

# ── 환경변수 ──────────────────────────────────────────────
CPU_BOT_TOKEN  = os.getenv("CPU_BOT_TOKEN", "")
CPU_CHANNEL_ID = int(os.getenv("CPU_CHANNEL_ID", "0"))

# 보고 주기 (초)
REPORT_INTERVAL = 10  # 10초마다
TOP_N = 5             # 상위 몇 개 프로세스

# ── 임베드 색상 ───────────────────────────────────────────
COLOR_NORMAL = 0x3498DB   # 파랑
COLOR_WARN   = 0xE67E22   # 주황 — CPU 1위 프로세스가 50% 이상


# ══════════════════════════════════════════════════════════
# 프로세스 정보 수집 (블로킹)
# ══════════════════════════════════════════════════════════

def collect_top_processes() -> dict:
    """CPU / 메모리 상위 프로세스 수집"""
    procs = []
    for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent", "username"]):
        try:
            info = p.info
            info["cpu_percent"]    = info["cpu_percent"]    or 0.0
            info["memory_percent"] = info["memory_percent"] or 0.0
            procs.append(info)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    top_cpu = sorted(procs, key=lambda x: x["cpu_percent"],    reverse=True)[:TOP_N]
    top_mem = sorted(procs, key=lambda x: x["memory_percent"], reverse=True)[:TOP_N]

    total_mem_gb = psutil.virtual_memory().total / (1024 ** 3)

    return {
        "top_cpu":      top_cpu,
        "top_mem":      top_mem,
        "total_mem_gb": total_mem_gb,
    }


# ══════════════════════════════════════════════════════════
# Discord Embed 빌더
# ══════════════════════════════════════════════════════════

def build_embed(data: dict) -> discord.Embed:
    now_kst = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S KST")

    top_cpu      = data["top_cpu"]
    top_mem      = data["top_mem"]
    total_mem_gb = data["total_mem_gb"]

    # 1위 프로세스 CPU가 50% 이상이면 주황
    color = COLOR_WARN if top_cpu and top_cpu[0]["cpu_percent"] >= 50 else COLOR_NORMAL

    embed = discord.Embed(
        title="📊 상위 프로세스 모니터",
        color=color,
        timestamp=datetime.now(timezone.utc),
    )

    # CPU 상위
    cpu_lines = []
    for i, p in enumerate(top_cpu, 1):
        name = (p["name"] or "?")[:20]
        user = (p["username"] or "?")[:10]
        cpu_lines.append(
            f"`{i}.` **{name}** ({user}) — **{p['cpu_percent']:.1f}%**  PID {p['pid']}"
        )
    embed.add_field(
        name=f"CPU 상위 {TOP_N}",
        value="\n".join(cpu_lines) if cpu_lines else "정보 없음",
        inline=False,
    )

    # 메모리 상위
    mem_lines = []
    for i, p in enumerate(top_mem, 1):
        name = (p["name"] or "?")[:20]
        user = (p["username"] or "?")[:10]
        used_mb = p["memory_percent"] / 100 * total_mem_gb * 1024
        mem_lines.append(
            f"`{i}.` **{name}** ({user}) — **{p['memory_percent']:.1f}%** ({used_mb:.0f} MB)  PID {p['pid']}"
        )
    embed.add_field(
        name=f"메모리 상위 {TOP_N}",
        value="\n".join(mem_lines) if mem_lines else "정보 없음",
        inline=False,
    )

    embed.set_footer(text=now_kst)
    return embed


# ══════════════════════════════════════════════════════════
# Discord 봇
# ══════════════════════════════════════════════════════════

class ProcMonitorBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(intents=intents)
        self._status_message: discord.Message | None = None

    async def setup_hook(self):
        self.loop.create_task(self._report_loop())

    async def on_ready(self):
        log.info(f"프로세스 모니터 봇 로그인 완료: {self.user} (ID: {self.user.id})")
        log.info(f"채널 ID: {CPU_CHANNEL_ID} | 보고 주기: {REPORT_INTERVAL // 60}분")
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="프로세스 모니터링"
            )
        )
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
            data  = await loop.run_in_executor(None, collect_top_processes)
            embed = build_embed(data)

            if self._status_message is None:
                self._status_message = await channel.send(embed=embed)
            else:
                try:
                    await self._status_message.edit(embed=embed)
                except discord.NotFound:
                    self._status_message = await channel.send(embed=embed)

            top1 = data["top_cpu"][0] if data["top_cpu"] else {}
            log.info(
                f"보고 완료 | CPU 1위: {top1.get('name', '?')} {top1.get('cpu_percent', 0):.1f}%"
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

    bot = ProcMonitorBot()
    bot.run(CPU_BOT_TOKEN, log_handler=None)


if __name__ == "__main__":
    main()

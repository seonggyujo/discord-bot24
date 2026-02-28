import asyncio
import logging
from datetime import datetime, timezone, timedelta

import discord
from discord.ext import tasks

import config
from system_info import get_system_stats, format_uptime, make_bar

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("oracle-monitor")

# 한국 시간대 (UTC+9)
KST = timezone(timedelta(hours=9))


def build_embed(stats) -> discord.Embed:
    """시스템 통계를 Discord Embed로 변환"""

    # 임계값 초과 여부에 따라 색상 결정
    if stats.cpu_percent >= config.CPU_WARN_THRESHOLD or \
       stats.mem_percent >= config.MEM_WARN_THRESHOLD or \
       stats.disk_percent >= config.DISK_WARN_THRESHOLD:
        color = config.COLOR_WARN
        status_icon = "⚠️"
    else:
        color = config.COLOR_NORMAL
        status_icon = "✅"

    now_kst = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S KST")

    embed = discord.Embed(
        title=f"{status_icon} {config.INSTANCE_NAME} 시스템 모니터",
        description=f"`{config.INSTANCE_SHAPE}` | 업타임: **{format_uptime(stats.uptime_seconds)}**",
        color=color,
        timestamp=datetime.now(timezone.utc),
    )

    # CPU
    cpu_bar = make_bar(stats.cpu_percent)
    cpu_warn = " ⚠️" if stats.cpu_percent >= config.CPU_WARN_THRESHOLD else ""
    embed.add_field(
        name="CPU",
        value=(
            f"`{cpu_bar}` **{stats.cpu_percent:.1f}%**{cpu_warn}\n"
            f"코어별: {' / '.join(f'{c:.0f}%' for c in stats.cpu_per_core)}"
        ),
        inline=False,
    )

    # 메모리
    mem_bar = make_bar(stats.mem_percent)
    mem_warn = " ⚠️" if stats.mem_percent >= config.MEM_WARN_THRESHOLD else ""
    embed.add_field(
        name="메모리 (RAM)",
        value=(
            f"`{mem_bar}` **{stats.mem_percent:.1f}%**{mem_warn}\n"
            f"{stats.mem_used_gb:.1f} GB / {stats.mem_total_gb:.1f} GB"
        ),
        inline=True,
    )

    # 스왑
    if stats.swap_total_gb > 0:
        swap_bar = make_bar(stats.swap_percent)
        embed.add_field(
            name="스왑",
            value=(
                f"`{swap_bar}` **{stats.swap_percent:.1f}%**\n"
                f"{stats.swap_used_gb:.1f} GB / {stats.swap_total_gb:.1f} GB"
            ),
            inline=True,
        )

    # 디스크
    disk_bar = make_bar(stats.disk_percent)
    disk_warn = " ⚠️" if stats.disk_percent >= config.DISK_WARN_THRESHOLD else ""
    embed.add_field(
        name="디스크 (/)",
        value=(
            f"`{disk_bar}` **{stats.disk_percent:.1f}%**{disk_warn}\n"
            f"{stats.disk_used_gb:.1f} GB / {stats.disk_total_gb:.1f} GB"
        ),
        inline=True,
    )

    # 네트워크
    embed.add_field(
        name="네트워크",
        value=(
            f"수신 ↓ **{stats.net_recv_kb:.1f} KB/s**\n"
            f"송신 ↑ **{stats.net_sent_kb:.1f} KB/s**"
        ),
        inline=True,
    )

    embed.set_footer(text=now_kst)
    return embed


def build_alert_embed(stats) -> discord.Embed:
    """임계값 초과 시 전송할 알림 Embed"""
    alerts = []
    if stats.cpu_percent >= config.CPU_ALERT_THRESHOLD:
        alerts.append(f"CPU **{stats.cpu_percent:.1f}%** (임계값: {config.CPU_ALERT_THRESHOLD}%)")
    if stats.disk_percent >= config.DISK_ALERT_THRESHOLD:
        alerts.append(f"디스크 **{stats.disk_percent:.1f}%** (임계값: {config.DISK_ALERT_THRESHOLD}%)")
    if stats.net_recv_kb >= config.NET_ALERT_THRESHOLD_KB:
        alerts.append(f"네트워크 수신 ↓ **{stats.net_recv_kb / 1024:.1f} MB/s** (임계값: {config.NET_ALERT_THRESHOLD_KB // 1024} MB/s)")
    if stats.net_sent_kb >= config.NET_ALERT_THRESHOLD_KB:
        alerts.append(f"네트워크 송신 ↑ **{stats.net_sent_kb / 1024:.1f} MB/s** (임계값: {config.NET_ALERT_THRESHOLD_KB // 1024} MB/s)")

    embed = discord.Embed(
        title="🚨 리소스 경고",
        description="\n".join(f"• {a}" for a in alerts),
        color=config.COLOR_CRIT,
        timestamp=datetime.now(timezone.utc),
    )
    embed.set_footer(text=datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S KST"))
    return embed


class OracleMonitorBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(intents=intents)
        # 이전 알림 상태 추적 (연속 알림 방지)
        self._alert_state = {"cpu": False, "disk": False, "net_recv": False, "net_sent": False}

    async def setup_hook(self):
        # 봇 준비 후 태스크 시작
        self.monitor_task.start()

    async def on_ready(self):
        log.info(f"봇 로그인 완료: {self.user} (ID: {self.user.id})")
        log.info(f"모니터링 채널 ID: {config.MONITOR_CHANNEL_ID}")
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="Oracle Cloud 서버 모니터링"
            )
        )

    @tasks.loop(seconds=config.MONITOR_INTERVAL_SECONDS)
    async def monitor_task(self):
        """1분마다 시스템 정보를 디스코드 채널에 전송"""
        channel = self.get_channel(config.MONITOR_CHANNEL_ID)
        if channel is None:
            log.warning(f"채널을 찾을 수 없습니다: {config.MONITOR_CHANNEL_ID}")
            return

        try:
            # 별도 스레드에서 blocking I/O 실행 (이벤트 루프 블로킹 방지)
            stats = await asyncio.get_event_loop().run_in_executor(
                None, get_system_stats
            )
            embed = build_embed(stats)
            await channel.send(embed=embed)

            # 알림 상태 확인 및 전송 (상태가 바뀔 때만)
            cpu_alert       = stats.cpu_percent  >= config.CPU_ALERT_THRESHOLD
            disk_alert      = stats.disk_percent >= config.DISK_ALERT_THRESHOLD
            net_recv_alert  = stats.net_recv_kb  >= config.NET_ALERT_THRESHOLD_KB
            net_sent_alert  = stats.net_sent_kb  >= config.NET_ALERT_THRESHOLD_KB
            newly_alert = (
                (cpu_alert      and not self._alert_state["cpu"])      or
                (disk_alert     and not self._alert_state["disk"])     or
                (net_recv_alert and not self._alert_state["net_recv"]) or
                (net_sent_alert and not self._alert_state["net_sent"])
            )
            newly_recover = (
                (not cpu_alert      and self._alert_state["cpu"])      or
                (not disk_alert     and self._alert_state["disk"])     or
                (not net_recv_alert and self._alert_state["net_recv"]) or
                (not net_sent_alert and self._alert_state["net_sent"])
            )

            if newly_alert:
                alert_embed = build_alert_embed(stats)
                await channel.send(content="@here", embed=alert_embed)
                log.warning(
                    f"알림 전송 | CPU: {stats.cpu_percent:.1f}% DISK: {stats.disk_percent:.1f}% "
                    f"NET_RECV: {stats.net_recv_kb:.0f} KB/s NET_SENT: {stats.net_sent_kb:.0f} KB/s"
                )
            elif newly_recover:
                recover_embed = discord.Embed(
                    title="✅ 리소스 정상화",
                    description=(
                        f"• CPU **{stats.cpu_percent:.1f}%**\n"
                        f"• 디스크 **{stats.disk_percent:.1f}%**\n"
                        f"• 네트워크 수신 ↓ **{stats.net_recv_kb / 1024:.1f} MB/s**\n"
                        f"• 네트워크 송신 ↑ **{stats.net_sent_kb / 1024:.1f} MB/s**"
                    ),
                    color=config.COLOR_NORMAL,
                    timestamp=datetime.now(timezone.utc),
                )
                recover_embed.set_footer(text=datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S KST"))
                await channel.send(embed=recover_embed)
                log.info("리소스 정상화 알림 전송")

            self._alert_state["cpu"]       = cpu_alert
            self._alert_state["disk"]      = disk_alert
            self._alert_state["net_recv"]  = net_recv_alert
            self._alert_state["net_sent"]  = net_sent_alert

            log.info(
                f"리포트 전송 | CPU: {stats.cpu_percent:.1f}% "
                f"MEM: {stats.mem_percent:.1f}% "
                f"DISK: {stats.disk_percent:.1f}%"
            )
        except Exception as e:
            log.error(f"모니터링 오류: {e}", exc_info=True)

    @monitor_task.before_loop
    async def before_monitor(self):
        """봇이 완전히 준비될 때까지 대기"""
        await self.wait_until_ready()


def main():
    if not config.DISCORD_BOT_TOKEN:
        log.error("DISCORD_BOT_TOKEN 환경변수가 설정되지 않았습니다.")
        return
    if config.MONITOR_CHANNEL_ID == 0:
        log.error("MONITOR_CHANNEL_ID 환경변수가 설정되지 않았습니다.")
        return

    bot = OracleMonitorBot()
    bot.run(config.DISCORD_BOT_TOKEN, log_handler=None)


if __name__ == "__main__":
    main()

"""
cpu_bot.py — CPU 부하 유지 봇
Oracle Cloud Free Tier의 idle 회수 정책 방지를 위해
주기적으로 무거운 수학 연산을 실행하고 결과를 Discord에 전송합니다.

실행: python cpu_bot.py
"""

import asyncio
import logging
import math
import multiprocessing
import os
import random
import time
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone, timedelta

import discord
from discord.ext import tasks
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
CPU_BOT_TOKEN      = os.getenv("CPU_BOT_TOKEN", "")
CPU_CHANNEL_ID     = int(os.getenv("CPU_CHANNEL_ID", "0"))
COMPUTE_INTERVAL   = 10 * 60          # 사용 안 함 (랜덤 주기로 대체)
NUM_WORKERS        = multiprocessing.cpu_count()   # 4코어 전부 사용
SIEVE_LIMIT        = 150_000_000      # 소수 탐색 상한 (1억5000만)
HASH_ITERATIONS    = 80_000_000       # SHA-256 반복 횟수 (8000만)
INTERVAL_MIN       = 5 * 60          # 최소 대기 (5분)
INTERVAL_MAX       = 20 * 60         # 최대 대기 (20분)

# ── 임베드 색상 ───────────────────────────────────────────
COLOR_INFO  = 0x3498DB
COLOR_WARN  = 0xE67E22


# ══════════════════════════════════════════════════════════
# 수학 연산 함수들 (별도 프로세스에서 실행)
# ══════════════════════════════════════════════════════════

def _sieve_of_eratosthenes(limit: int) -> int:
    """에라토스테네스의 체로 limit 이하 소수 개수 반환"""
    sieve = bytearray([1]) * (limit + 1)
    sieve[0] = sieve[1] = 0
    for i in range(2, int(math.sqrt(limit)) + 1):
        if sieve[i]:
            sieve[i * i::i] = bytearray(len(sieve[i * i::i]))
    return sum(sieve)


def _hash_stress(iterations: int) -> str:
    """SHA-256 해시를 반복 연산하여 CPU 부하 발생, 최종 해시값 반환"""
    import hashlib
    data = b"oracle-cpu-keepalive"
    for _ in range(iterations):
        data = hashlib.sha256(data).digest()
    return data.hex()


def _worker_task(worker_id: int) -> dict:
    """
    단일 워커가 수행하는 작업:
      1. 소수 탐색 (에라토스테네스의 체)
      2. SHA-256 해시 반복 연산
    결과를 dict로 반환
    """
    result = {"worker_id": worker_id}

    # 소수 탐색
    t0 = time.perf_counter()
    prime_count = _sieve_of_eratosthenes(SIEVE_LIMIT)
    sieve_time = time.perf_counter() - t0
    result["prime_count"] = prime_count
    result["sieve_time"]  = sieve_time

    # SHA-256 해시 반복
    t0 = time.perf_counter()
    final_hash = _hash_stress(HASH_ITERATIONS)
    hash_time = time.perf_counter() - t0
    result["final_hash"] = final_hash[:16]  # 앞 16자만 저장
    result["hash_time"]  = hash_time

    return result


def run_parallel_compute() -> dict:
    """
    모든 CPU 코어에서 병렬로 연산 실행.
    ProcessPoolExecutor를 사용해 GIL 우회.
    """
    t_start = time.perf_counter()

    with ProcessPoolExecutor(max_workers=NUM_WORKERS) as executor:
        futures = [executor.submit(_worker_task, i) for i in range(NUM_WORKERS)]
        results = [f.result() for f in futures]

    total_time = time.perf_counter() - t_start

    avg_sieve = sum(r["sieve_time"] for r in results) / NUM_WORKERS
    avg_hash  = sum(r["hash_time"]  for r in results) / NUM_WORKERS
    prime_count = results[0]["prime_count"]   # 모든 워커 동일

    return {
        "num_workers":   NUM_WORKERS,
        "sieve_limit":   SIEVE_LIMIT,
        "prime_count":   prime_count,
        "hash_iterations": HASH_ITERATIONS,
        "avg_sieve_sec": avg_sieve,
        "avg_hash_sec":  avg_hash,
        "total_sec":     total_time,
    }


# ══════════════════════════════════════════════════════════
# Discord 봇
# ══════════════════════════════════════════════════════════

def build_result_embed(info: dict, cpu_before: float, cpu_after: float) -> discord.Embed:
    now_kst = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S KST")

    embed = discord.Embed(
        title="🖥️ CPU 연산 완료",
        description=(
            f"**{info['num_workers']}코어** 병렬 연산이 완료되었습니다.\n"
            f"총 소요 시간: **{info['total_sec']:.2f}초**"
        ),
        color=COLOR_INFO,
        timestamp=datetime.now(timezone.utc),
    )

    embed.add_field(
        name="소수 탐색 (에라토스테네스의 체)",
        value=(
            f"범위: 2 ~ **{info['sieve_limit']:,}**\n"
            f"소수 개수: **{info['prime_count']:,}개**\n"
            f"코어당 평균 소요: **{info['avg_sieve_sec']:.2f}초**"
        ),
        inline=False,
    )

    embed.add_field(
        name="SHA-256 해시 반복 연산",
        value=(
            f"반복 횟수: **{info['hash_iterations']:,}회**\n"
            f"코어당 평균 소요: **{info['avg_hash_sec']:.2f}초**"
        ),
        inline=False,
    )

    embed.add_field(
        name="CPU 사용률 변화",
        value=f"연산 전: **{cpu_before:.1f}%** → 연산 후: **{cpu_after:.1f}%**",
        inline=False,
    )

    embed.set_footer(text=now_kst)
    return embed


class CpuBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(intents=intents)
        # 고정 결과 메시지 (edit용)
        self._result_message: discord.Message | None = None

    async def setup_hook(self):
        self.loop.create_task(self._compute_loop())

    async def on_ready(self):
        log.info(f"CPU 봇 로그인 완료: {self.user} (ID: {self.user.id})")
        log.info(f"채널 ID: {CPU_CHANNEL_ID} | 워커 수: {NUM_WORKERS} | 주기: {INTERVAL_MIN//60}~{INTERVAL_MAX//60}분 랜덤")
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.playing,
                name="수학 연산 중..."
            )
        )

    async def _compute_loop(self):
        await self.wait_until_ready()

        # 첫 연산 전 1분 대기
        log.info("첫 연산까지 1분 대기...")
        await asyncio.sleep(60)

        while not self.is_closed():
            await self._run_compute()

            # 다음 연산까지 랜덤 대기
            next_sec = random.randint(INTERVAL_MIN, INTERVAL_MAX)
            log.info(f"다음 연산까지 {next_sec // 60}분 {next_sec % 60}초 대기...")
            await asyncio.sleep(next_sec)

    async def _run_compute(self):
        channel = self.get_channel(CPU_CHANNEL_ID)
        if channel is None:
            log.warning(f"채널을 찾을 수 없습니다: {CPU_CHANNEL_ID}")
            return

        log.info("병렬 연산 시작...")

        try:
            import psutil
            cpu_before = psutil.cpu_percent(interval=1)
        except ImportError:
            cpu_before = 0.0

        try:
            loop = asyncio.get_event_loop()
            info = await loop.run_in_executor(None, run_parallel_compute)

            try:
                import psutil
                cpu_after = psutil.cpu_percent(interval=1)
            except ImportError:
                cpu_after = 0.0

            embed = build_result_embed(info, cpu_before, cpu_after)

            if self._result_message is None:
                self._result_message = await channel.send(embed=embed)
            else:
                try:
                    await self._result_message.edit(embed=embed)
                except discord.NotFound:
                    self._result_message = await channel.send(embed=embed)

            log.info(
                f"연산 완료 | 총 {info['total_sec']:.2f}초 | "
                f"소수 {info['prime_count']:,}개 | "
                f"CPU {cpu_before:.1f}% → {cpu_after:.1f}%"
            )

        except Exception as e:
            log.error(f"연산 오류: {e}", exc_info=True)
            try:
                err_embed = discord.Embed(
                    title="❌ 연산 오류",
                    description=f"```{e}```",
                    color=0xE74C3C,
                    timestamp=datetime.now(timezone.utc),
                )
                await channel.send(embed=err_embed)
            except Exception:
                pass


def main():
    if not CPU_BOT_TOKEN:
        log.error("CPU_BOT_TOKEN 환경변수가 설정되지 않았습니다.")
        return
    if CPU_CHANNEL_ID == 0:
        log.error("CPU_CHANNEL_ID 환경변수가 설정되지 않았습니다.")
        return

    bot = CpuBot()
    bot.run(CPU_BOT_TOKEN, log_handler=None)


if __name__ == "__main__":
    # Windows/macOS에서 multiprocessing 안전하게 사용하기 위해 필수
    multiprocessing.freeze_support()
    main()

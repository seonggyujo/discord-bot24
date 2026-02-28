import psutil
import time
from dataclasses import dataclass
from typing import Optional, Any

# 이전 네트워크 카운터 (전송량 계산용)
_prev_net_io: Optional[Any] = None
_prev_net_time: float = 0.0


@dataclass
class SystemStats:
    # CPU
    cpu_percent: float          # 전체 평균 사용률 (%)
    cpu_per_core: list[float]   # 코어별 사용률 (%)

    # 메모리
    mem_used_gb: float
    mem_total_gb: float
    mem_percent: float

    # 스왑
    swap_used_gb: float
    swap_total_gb: float
    swap_percent: float

    # 디스크 (루트 파티션)
    disk_used_gb: float
    disk_total_gb: float
    disk_percent: float

    # 네트워크 (초당 전송량)
    net_recv_kb: float   # KB/s 수신
    net_sent_kb: float   # KB/s 송신

    # 업타임
    uptime_seconds: int


def get_system_stats() -> SystemStats:
    global _prev_net_io, _prev_net_time

    # CPU - interval=1 로 1초 블로킹해서 정확한 수치 측정
    cpu_percent = psutil.cpu_percent(interval=1)
    cpu_per_core = psutil.cpu_percent(percpu=True)

    # 메모리
    mem = psutil.virtual_memory()
    mem_used_gb = mem.used / (1024 ** 3)
    mem_total_gb = mem.total / (1024 ** 3)

    # 스왑
    swap = psutil.swap_memory()
    swap_used_gb = swap.used / (1024 ** 3)
    swap_total_gb = swap.total / (1024 ** 3)

    # 디스크 (루트 파티션)
    disk = psutil.disk_usage("/")
    disk_used_gb = disk.used / (1024 ** 3)
    disk_total_gb = disk.total / (1024 ** 3)

    # 네트워크 (초당 전송량)
    now = time.monotonic()
    net_io = psutil.net_io_counters()
    if _prev_net_io is not None and (now - _prev_net_time) > 0:
        elapsed = now - _prev_net_time
        net_recv_kb = (net_io.bytes_recv - _prev_net_io.bytes_recv) / elapsed / 1024
        net_sent_kb = (net_io.bytes_sent - _prev_net_io.bytes_sent) / elapsed / 1024
    else:
        net_recv_kb = 0.0
        net_sent_kb = 0.0
    _prev_net_io = net_io
    _prev_net_time = now

    # 업타임
    boot_time = psutil.boot_time()
    uptime_seconds = int(time.time() - boot_time)

    return SystemStats(
        cpu_percent=cpu_percent,
        cpu_per_core=cpu_per_core,
        mem_used_gb=mem_used_gb,
        mem_total_gb=mem_total_gb,
        mem_percent=mem.percent,
        swap_used_gb=swap_used_gb,
        swap_total_gb=swap_total_gb,
        swap_percent=swap.percent,
        disk_used_gb=disk_used_gb,
        disk_total_gb=disk_total_gb,
        disk_percent=disk.percent,
        net_recv_kb=net_recv_kb,
        net_sent_kb=net_sent_kb,
        uptime_seconds=uptime_seconds,
    )


def format_uptime(seconds: int) -> str:
    days = seconds // 86400
    hours = (seconds % 86400) // 3600
    minutes = (seconds % 3600) // 60
    if days > 0:
        return f"{days}일 {hours}시간 {minutes}분"
    elif hours > 0:
        return f"{hours}시간 {minutes}분"
    else:
        return f"{minutes}분"


def make_bar(percent: float, width: int = 10) -> str:
    """퍼센트를 시각적 막대로 변환 (유니코드 블록 문자 사용)"""
    filled = round(percent / 100 * width)
    filled = max(0, min(width, filled))
    return "█" * filled + "░" * (width - filled)

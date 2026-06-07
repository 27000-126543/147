import uuid
import hashlib
from datetime import datetime, timedelta, timezone
from typing import List, Iterator, Dict, Any, Tuple, Optional
import pandas as pd
import numpy as np
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
import pytz
from config import settings


def generate_id(prefix: str = "") -> str:
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    unique_id = str(uuid.uuid4()).replace("-", "")[:12]
    return f"{prefix}_{timestamp}_{unique_id}" if prefix else f"{timestamp}_{unique_id}"


def parse_date_range(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    days: Optional[int] = None
) -> Tuple[datetime, datetime]:
    tz = pytz.timezone(settings.TIME_ZONE)
    now = datetime.now(tz)
    
    if days is not None:
        end = now
        start = end - timedelta(days=days)
    else:
        if start_date:
            start = datetime.strptime(start_date, "%Y-%m-%d")
        else:
            start = now - timedelta(days=30)
            
        if end_date:
            end = datetime.strptime(end_date, "%Y-%m-%d")
        else:
            end = now
    
    if start.tzinfo is None:
        start = tz.localize(start)
    if end.tzinfo is None:
        end = tz.localize(end)
    
    return start, end


def safe_divide(numerator: float, denominator: float, default: float = 0.0) -> float:
    return numerator / denominator if denominator != 0 else default


def round_float(value: float, decimals: int = 2) -> float:
    return round(value, decimals)


def calculate_confidence_interval(
    data,
    confidence_level: float = 0.95
) -> Dict[str, float]:
    if data is None or (isinstance(data, (list, tuple)) and len(data) == 0) or (hasattr(data, '__len__') and len(data) == 0):
        return {"lower": 0.0, "upper": 0.0, "mean": 0.0, "std": 0.0}
    
    arr = np.asarray(data)
    mean = np.mean(arr)
    std = np.std(arr, ddof=1) if len(arr) > 1 else 0
    
    if len(arr) < 30 and std > 0:
        from scipy import stats
        interval = stats.t.interval(
            confidence_level,
            len(arr) - 1,
            loc=mean,
            scale=std / np.sqrt(len(arr))
        )
    else:
        z_score = 1.96 if confidence_level == 0.95 else 1.645
        margin = z_score * (std / np.sqrt(len(arr))) if len(arr) > 0 else 0
        interval = (mean - margin, mean + margin)
    
    return {
        "lower": round_float(interval[0]),
        "upper": round_float(interval[1]),
        "mean": round_float(mean),
        "std": round_float(std)
    }


def convert_timezone(
    dt: datetime,
    from_tz: str = "UTC",
    to_tz: str = settings.TIME_ZONE
) -> datetime:
    if dt.tzinfo is None:
        dt = pytz.timezone(from_tz).localize(dt)
    return dt.astimezone(pytz.timezone(to_tz))


def batch_iterator(
    data: List[Any],
    batch_size: int = settings.BATCH_SIZE
) -> Iterator[List[Any]]:
    for i in range(0, len(data), batch_size):
        yield data[i:i + batch_size]


def parallel_process(
    func,
    items: List[Any],
    max_workers: int = settings.MAX_WORKERS,
    use_processes: bool = False,
    **kwargs
) -> List[Any]:
    if not items:
        return []
    
    if len(items) == 1:
        return [func(items[0], **kwargs)]
    
    executor_class = ProcessPoolExecutor if use_processes else ThreadPoolExecutor
    results = []
    
    with executor_class(max_workers=min(max_workers, len(items))) as executor:
        futures = {executor.submit(func, item, **kwargs): item for item in items}
        for future in as_completed(futures):
            try:
                results.append(future.result())
            except Exception as e:
                results.append({"error": str(e), "item": futures[future]})
    
    return results


def hash_dict(data: Dict[str, Any]) -> str:
    sorted_str = str(sorted(data.items())).encode('utf-8')
    return hashlib.md5(sorted_str).hexdigest()


def format_currency(value: float, currency: str = "CNY") -> str:
    symbols = {"CNY": "¥", "USD": "$", "EUR": "€"}
    symbol = symbols.get(currency, "¥")
    return f"{symbol}{value:,.2f}"


def format_percent(value: float, decimals: int = 2) -> str:
    return f"{value * 100:.{decimals}f}%"


def merge_dicts_deep(dict1: Dict[str, Any], dict2: Dict[str, Any]) -> Dict[str, Any]:
    result = dict1.copy()
    for key, value in dict2.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = merge_dicts_deep(result[key], value)
        else:
            result[key] = value
    return result


def async_retry(max_retries: int = 3, delay: float = 1.0):
    def decorator(func):
        import asyncio
        import functools
        
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        await asyncio.sleep(delay * (2 ** attempt))
            raise last_exception
        return wrapper
    return decorator


def retry(max_retries: int = 3, delay: float = 1.0):
    def decorator(func):
        import functools
        import time
        
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        time.sleep(delay * (2 ** attempt))
            raise last_exception
        return wrapper
    return decorator

import os
from typing import Dict, List, Optional
from pydantic import Field
from pydantic_settings import BaseSettings
from datetime import time


class Settings(BaseSettings):
    BASE_DIR: str = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    DATA_DIR: str = os.path.join(BASE_DIR, "data")
    OUTPUT_DIR: str = os.path.join(BASE_DIR, "output")
    LOG_DIR: str = os.path.join(BASE_DIR, "logs")
    
    DATABASE_URL: str = Field(default="sqlite:///marketing.db")
    
    AD_PLATFORMS: List[str] = Field(default_factory=lambda: [
        "baidu", "tencent", "aliyun", "bytedance", "kuaishou", "xiaohongshu"
    ])
    
    ATTRIBUTION_MODELS: List[str] = Field(default_factory=lambda: [
        "first_click", "last_click", "linear", "time_decay", "position_based"
    ])
    
    DEFAULT_ATTRIBUTION_MODEL: str = "last_click"
    
    ROI_THRESHOLD: float = 2.0
    
    CONSECUTIVE_DAYS_FOR_BUDGET_ADJUSTMENT: int = 3
    
    ROLLBACK_MONITORING_HOURS: int = 48
    
    DAILY_REPORT_TIME: time = Field(default=time(2, 0, 0))
    WEEKLY_REPORT_DAY: int = 1
    WEEKLY_REPORT_TIME: time = Field(default=time(3, 0, 0))
    
    CHANNEL_CONFIG: Dict[str, Dict] = Field(default_factory=lambda: {
        "baidu_search": {"weight": 0.15, "min_budget": 1000, "max_budget": 50000},
        "baidu_feed": {"weight": 0.10, "min_budget": 1000, "max_budget": 30000},
        "tencent_wechat": {"weight": 0.20, "min_budget": 2000, "max_budget": 80000},
        "tencent_qq": {"weight": 0.08, "min_budget": 500, "max_budget": 20000},
        "aliyun_zhima": {"weight": 0.12, "min_budget": 1000, "max_budget": 40000},
        "bytedance_douyin": {"weight": 0.20, "min_budget": 2000, "max_budget": 100000},
        "bytedance_toutiao": {"weight": 0.08, "min_budget": 1000, "max_budget": 30000},
        "kuaishou": {"weight": 0.05, "min_budget": 500, "max_budget": 15000},
        "xiaohongshu": {"weight": 0.02, "min_budget": 500, "max_budget": 10000},
    })
    
    TOTAL_DAILY_BUDGET: float = 200000.0
    
    TIME_ZONE: str = "Asia/Shanghai"
    
    DATA_PROCESSING_PARTITIONS: int = 8
    
    BATCH_SIZE: int = 10000
    
    MAX_WORKERS: int = 16
    
    PLATFORM_API_CONFIGS: Dict[str, Dict] = Field(default_factory=lambda: {
        "baidu": {
            "api_url": "https://api.baidu.com/marketing/v1",
            "timeout": 30,
            "retry_times": 3
        },
        "tencent": {
            "api_url": "https://api.tencent.com/marketing/v1",
            "timeout": 30,
            "retry_times": 3
        },
        "bytedance": {
            "api_url": "https://api.bytedance.com/open_api/v1",
            "timeout": 30,
            "retry_times": 3
        },
        "aliyun": {
            "api_url": "https://api.aliyun.com/marketing/v1",
            "timeout": 30,
            "retry_times": 3
        },
        "kuaishou": {
            "api_url": "https://api.kuaishou.com/rest/openapi",
            "timeout": 30,
            "retry_times": 3
        },
        "xiaohongshu": {
            "api_url": "https://api.xiaohongshu.com/galaxy",
            "timeout": 30,
            "retry_times": 3
        }
    })
    
    ENABLE_REAL_TIME_MONITORING: bool = True
    
    NOTIFICATION_EMAILS: List[str] = Field(default_factory=lambda: [
        "marketing_manager@company.com",
        "marketing_director@company.com"
    ])
    
    EXPORT_FORMATS: List[str] = Field(default_factory=lambda: ["pdf", "xlsx"])
    
    SIMULATION_RUNS: int = 1000
    
    CONFIDENCE_LEVEL: float = 0.95
    
    LOG_RETENTION_DAYS: int = 90
    
    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()

for directory in [settings.DATA_DIR, settings.OUTPUT_DIR, settings.LOG_DIR]:
    os.makedirs(directory, exist_ok=True)

import os
import asyncio
from typing import Dict, List, Any, Optional, Callable
from datetime import datetime, date, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR, JobExecutionEvent
from functools import wraps

from utils.logger import logger
from config.settings import settings
from logging_system import OperationLogger


class TaskScheduler:
    def __init__(self):
        self.scheduler = BackgroundScheduler(timezone=settings.TIME_ZONE)
        self.operation_logger = OperationLogger()
        self._registered_tasks: Dict[str, Callable] = {}
        self._task_status: Dict[str, Dict[str, Any]] = {}
        self._setup_event_listeners()
        
    def _setup_event_listeners(self):
        self.scheduler.add_listener(self._on_job_executed, EVENT_JOB_EXECUTED)
        self.scheduler.add_listener(self._on_job_error, EVENT_JOB_ERROR)
    
    def _on_job_executed(self, event: JobExecutionEvent):
        job_id = event.job_id
        task_name = self._task_status.get(job_id, {}).get('name', job_id)
        
        self.operation_logger.log_operation(
            operation_type="scheduled_task",
            module="scheduler",
            status="success",
            details={
                'job_id': job_id,
                'task_name': task_name,
                'scheduled_run_time': event.scheduled_run_time.isoformat() if event.scheduled_run_time else None,
                'duration_ms': event.duration * 1000 if event.duration else None
            }
        )
        
        self._update_task_status(job_id, 'last_run', datetime.now())
        self._update_task_status(job_id, 'last_status', 'success')
        
        logger.info(f"定时任务执行成功: {task_name} (job_id={job_id})")
    
    def _on_job_error(self, event: JobExecutionEvent):
        job_id = event.job_id
        task_name = self._task_status.get(job_id, {}).get('name', job_id)
        error_message = str(event.exception) if event.exception else "Unknown error"
        
        self.operation_logger.log_operation(
            operation_type="scheduled_task",
            module="scheduler",
            status="error",
            error_message=error_message,
            details={
                'job_id': job_id,
                'task_name': task_name,
                'scheduled_run_time': event.scheduled_run_time.isoformat() if event.scheduled_run_time else None,
                'duration_ms': event.duration * 1000 if event.duration else None,
                'traceback': event.traceback
            }
        )
        
        self._update_task_status(job_id, 'last_run', datetime.now())
        self._update_task_status(job_id, 'last_status', 'error')
        self._update_task_status(job_id, 'last_error', error_message)
        self._update_task_status(job_id, 'error_count', 
                                self._task_status.get(job_id, {}).get('error_count', 0) + 1)
        
        logger.error(f"定时任务执行失败: {task_name} (job_id={job_id}), 错误: {error_message}")
    
    def _update_task_status(self, job_id: str, key: str, value: Any):
        if job_id not in self._task_status:
            self._task_status[job_id] = {}
        self._task_status[job_id][key] = value
    
    def register_task(self, name: str, func: Callable) -> str:
        task_id = f"task_{name}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        self._registered_tasks[task_id] = func
        
        self._task_status[task_id] = {
            'name': name,
            'func_name': func.__name__,
            'registered_at': datetime.now(),
            'last_run': None,
            'last_status': None,
            'last_error': None,
            'error_count': 0,
            'trigger': None
        }
        
        logger.info(f"注册任务: {name} (task_id={task_id})")
        
        return task_id
    
    def schedule_daily(self, task_id: str, hour: int = 0, minute: int = 0, 
                       second: int = 0, *args, **kwargs) -> str:
        if task_id not in self._registered_tasks:
            raise ValueError(f"任务 {task_id} 未注册")
        
        func = self._registered_tasks[task_id]
        job = self.scheduler.add_job(
            func,
            trigger=CronTrigger(hour=hour, minute=minute, second=second, timezone=settings.TIME_ZONE),
            args=args,
            kwargs=kwargs,
            id=task_id,
            replace_existing=True
        )
        
        self._update_task_status(task_id, 'trigger', f'daily_{hour:02d}:{minute:02d}:{second:02d}')
        logger.info(f"任务 {task_id} 已设置为每日 {hour:02d}:{minute:02d}:{second:02d} 执行")
        
        return job.id
    
    def schedule_weekly(self, task_id: str, day_of_week: int = 0, 
                        hour: int = 0, minute: int = 0, *args, **kwargs) -> str:
        if task_id not in self._registered_tasks:
            raise ValueError(f"任务 {task_id} 未注册")
        
        func = self._registered_tasks[task_id]
        job = self.scheduler.add_job(
            func,
            trigger=CronTrigger(day_of_week=day_of_week, hour=hour, minute=minute, timezone=settings.TIME_ZONE),
            args=args,
            kwargs=kwargs,
            id=task_id,
            replace_existing=True
        )
        
        self._update_task_status(task_id, 'trigger', f'weekly_{day_of_week}_{hour:02d}:{minute:02d}')
        logger.info(f"任务 {task_id} 已设置为每周 {day_of_week} {hour:02d}:{minute:02d} 执行")
        
        return job.id
    
    def schedule_interval(self, task_id: str, hours: int = 0, minutes: int = 0, 
                          seconds: int = 0, *args, **kwargs) -> str:
        if task_id not in self._registered_tasks:
            raise ValueError(f"任务 {task_id} 未注册")
        
        func = self._registered_tasks[task_id]
        job = self.scheduler.add_job(
            func,
            trigger=IntervalTrigger(hours=hours, minutes=minutes, seconds=seconds, timezone=settings.TIME_ZONE),
            args=args,
            kwargs=kwargs,
            id=task_id,
            replace_existing=True
        )
        
        self._update_task_status(task_id, 'trigger', f'interval_{hours}h_{minutes}m_{seconds}s')
        logger.info(f"任务 {task_id} 已设置为每 {hours}小时{minutes}分钟{seconds}秒 执行")
        
        return job.id
    
    def schedule_custom(self, task_id: str, cron_expr: str, *args, **kwargs) -> str:
        if task_id not in self._registered_tasks:
            raise ValueError(f"任务 {task_id} 未注册")
        
        func = self._registered_tasks[task_id]
        job = self.scheduler.add_job(
            func,
            trigger=CronTrigger.from_crontab(cron_expr, timezone=settings.TIME_ZONE),
            args=args,
            kwargs=kwargs,
            id=task_id,
            replace_existing=True
        )
        
        self._update_task_status(task_id, 'trigger', f'cron_{cron_expr}')
        logger.info(f"任务 {task_id} 已设置为 cron 表达式 {cron_expr} 执行")
        
        return job.id
    
    def run_once(self, task_id: str, *args, **kwargs) -> Any:
        if task_id not in self._registered_tasks:
            raise ValueError(f"任务 {task_id} 未注册")
        
        func = self._registered_tasks[task_id]
        task_name = self._task_status.get(task_id, {}).get('name', task_id)
        
        logger.info(f"手动执行任务: {task_name} (task_id={task_id})")
        
        start_time = datetime.now()
        try:
            result = func(*args, **kwargs)
            duration_ms = (datetime.now() - start_time).total_seconds() * 1000
            
            self.operation_logger.log_operation(
                operation_type="manual_task",
                module="scheduler",
                status="success",
                details={
                    'task_id': task_id,
                    'task_name': task_name,
                    'duration_ms': duration_ms
                }
            )
            
            self._update_task_status(task_id, 'last_run', datetime.now())
            self._update_task_status(task_id, 'last_status', 'success')
            
            logger.info(f"手动任务执行成功: {task_name}, 耗时: {duration_ms:.2f}ms")
            
            return result
        except Exception as e:
            duration_ms = (datetime.now() - start_time).total_seconds() * 1000
            
            self.operation_logger.log_operation(
                operation_type="manual_task",
                module="scheduler",
                status="error",
                error_message=str(e),
                details={
                    'task_id': task_id,
                    'task_name': task_name,
                    'duration_ms': duration_ms
                }
            )
            
            self._update_task_status(task_id, 'last_run', datetime.now())
            self._update_task_status(task_id, 'last_status', 'error')
            self._update_task_status(task_id, 'last_error', str(e))
            
            logger.error(f"手动任务执行失败: {task_name}, 错误: {e}")
            raise
    
    def start(self):
        if not self.scheduler.running:
            self.scheduler.start()
            logger.info("调度器已启动")
        else:
            logger.warning("调度器已经在运行中")
    
    def shutdown(self, wait: bool = True):
        if self.scheduler.running:
            self.scheduler.shutdown(wait=wait)
            logger.info("调度器已关闭")
        else:
            logger.warning("调度器未在运行")
    
    def pause_task(self, task_id: str):
        self.scheduler.pause_job(task_id)
        self._update_task_status(task_id, 'paused', True)
        logger.info(f"任务已暂停: {task_id}")
    
    def resume_task(self, task_id: str):
        self.scheduler.resume_job(task_id)
        self._update_task_status(task_id, 'paused', False)
        logger.info(f"任务已恢复: {task_id}")
    
    def remove_task(self, task_id: str):
        self.scheduler.remove_job(task_id)
        if task_id in self._registered_tasks:
            del self._registered_tasks[task_id]
        if task_id in self._task_status:
            del self._task_status[task_id]
        logger.info(f"任务已移除: {task_id}")
    
    def get_task_status(self, task_id: Optional[str] = None) -> Dict[str, Any]:
        if task_id:
            return self._task_status.get(task_id, {})
        return self._task_status.copy()
    
    def get_jobs(self) -> List[Dict[str, Any]]:
        jobs = self.scheduler.get_jobs()
        job_info = []
        
        for job in jobs:
            task_status = self._task_status.get(job.id, {})
            job_info.append({
                'id': job.id,
                'name': task_status.get('name', job.name),
                'trigger': str(job.trigger),
                'next_run_time': job.next_run_time.isoformat() if job.next_run_time else None,
                'last_run': task_status.get('last_run'),
                'last_status': task_status.get('last_status'),
                'error_count': task_status.get('error_count', 0),
                'paused': task_status.get('paused', False)
            })
        
        return job_info
    
    def setup_default_schedule(self, system):
        logger.info("设置默认调度任务...")
        
        data_collection_task_id = self.register_task(
            name="每日数据采集",
            func=system.run_data_collection
        )
        self.schedule_daily(data_collection_task_id, hour=1, minute=0)
        
        daily_report_task_id = self.register_task(
            name="生成日报",
            func=system.generate_daily_report
        )
        self.schedule_daily(daily_report_task_id, 
                           hour=settings.DAILY_REPORT_TIME.hour,
                           minute=settings.DAILY_REPORT_TIME.minute)
        
        weekly_report_task_id = self.register_task(
            name="生成周报",
            func=system.generate_weekly_report
        )
        self.schedule_weekly(weekly_report_task_id,
                            day_of_week=settings.WEEKLY_REPORT_DAY,
                            hour=settings.WEEKLY_REPORT_TIME.hour,
                            minute=settings.WEEKLY_REPORT_TIME.minute)
        
        budget_optimization_task_id = self.register_task(
            name="预算优化分析",
            func=system.run_budget_optimization
        )
        self.schedule_daily(budget_optimization_task_id, hour=3, minute=0)
        
        rollback_monitor_task_id = self.register_task(
            name="回滚监控检查",
            func=system.check_rollback_conditions
        )
        self.schedule_interval(rollback_monitor_task_id, hours=2)
        
        model_evaluation_task_id = self.register_task(
            name="归因模型评估",
            func=system.evaluate_attribution_models
        )
        self.schedule_weekly(model_evaluation_task_id, day_of_week=0, hour=4, minute=0)
        
        log_cleanup_task_id = self.register_task(
            name="日志清理",
            func=system.cleanup_old_logs
        )
        self.schedule_weekly(log_cleanup_task_id, day_of_week=6, hour=5, minute=0)
        
        approval_escalation_task_id = self.register_task(
            name="审批逾期升级",
            func=system.escalate_pending_approvals
        )
        self.schedule_interval(approval_escalation_task_id, hours=6)
        
        logger.info("默认调度任务设置完成")
    
    def task_decorator(self, name: str, schedule_type: str = "daily", **schedule_kwargs):
        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                return func(*args, **kwargs)
            
            task_id = self.register_task(name, wrapper)
            
            if schedule_type == "daily":
                self.schedule_daily(task_id, **schedule_kwargs)
            elif schedule_type == "weekly":
                self.schedule_weekly(task_id, **schedule_kwargs)
            elif schedule_type == "interval":
                self.schedule_interval(task_id, **schedule_kwargs)
            elif schedule_type == "cron":
                self.schedule_custom(task_id, **schedule_kwargs)
            
            return wrapper
        
        return decorator

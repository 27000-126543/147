import os
import json
import sqlite3
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, date, timedelta
import pandas as pd
from contextlib import contextmanager
from functools import wraps

from utils.logger import logger
from utils.helpers import generate_id
from config.settings import settings
from models.schemas import LogEntry
from report_engine.export_engine import ExportEngine


class OperationLogger:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or os.path.join(settings.DATA_DIR, "operation_logs.db")
        self.export_engine = ExportEngine()
        self._init_database()
    
    def _init_database(self):
        with self._get_connection() as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS operation_logs (
                    log_id TEXT PRIMARY KEY,
                    timestamp DATETIME NOT NULL,
                    operation_type TEXT NOT NULL,
                    operator TEXT,
                    module TEXT NOT NULL,
                    status TEXT NOT NULL,
                    details TEXT,
                    error_message TEXT,
                    duration_ms REAL,
                    campaign TEXT,
                    channel TEXT,
                    date DATE
                )
            ''')
            
            conn.execute('CREATE INDEX IF NOT EXISTS idx_timestamp ON operation_logs(timestamp)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_operation_type ON operation_logs(operation_type)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_module ON operation_logs(module)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_status ON operation_logs(status)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_channel ON operation_logs(channel)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_date ON operation_logs(date)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_campaign ON operation_logs(campaign)')
            
            conn.commit()
        
        logger.info(f"操作日志数据库已初始化: {self.db_path}")
    
    @contextmanager
    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()
    
    def log_operation(self,
                      operation_type: str,
                      module: str,
                      status: str = "success",
                      operator: Optional[str] = None,
                      details: Optional[Dict[str, Any]] = None,
                      error_message: Optional[str] = None,
                      duration_ms: Optional[float] = None,
                      campaign: Optional[str] = None,
                      channel: Optional[str] = None) -> str:
        log_id = generate_id("log")
        timestamp = datetime.now()
        
        log_entry = LogEntry(
            log_id=log_id,
            timestamp=timestamp,
            operation_type=operation_type,
            operator=operator,
            module=module,
            status=status,
            details=details or {},
            error_message=error_message,
            duration_ms=duration_ms
        )
        
        try:
            with self._get_connection() as conn:
                conn.execute('''
                    INSERT INTO operation_logs 
                    (log_id, timestamp, operation_type, operator, module, status, 
                     details, error_message, duration_ms, campaign, channel, date)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    log_id,
                    timestamp.isoformat(),
                    operation_type,
                    operator,
                    module,
                    status,
                    json.dumps(details or {}, ensure_ascii=False),
                    error_message,
                    duration_ms,
                    campaign,
                    channel,
                    timestamp.date().isoformat()
                ))
                conn.commit()
        except Exception as e:
            logger.error(f"记录操作日志失败: {e}")
        
        if status == "error":
            logger.error(f"[{module}] {operation_type} 失败: {error_message}, log_id={log_id}")
        else:
            logger.info(f"[{module}] {operation_type} {status}, log_id={log_id}")
        
        return log_id
    
    def log_decorator(self, operation_type: str, module: str):
        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                start_time = datetime.now()
                status = "success"
                error_message = None
                details = {}
                
                try:
                    result = func(*args, **kwargs)
                    if isinstance(result, dict):
                        details.update(result)
                    return result
                except Exception as e:
                    status = "error"
                    error_message = str(e)
                    raise
                finally:
                    duration_ms = (datetime.now() - start_time).total_seconds() * 1000
                    self.log_operation(
                        operation_type=operation_type,
                        module=module,
                        status=status,
                        details=details,
                        error_message=error_message,
                        duration_ms=duration_ms
                    )
            
            return wrapper
        return decorator
    
    def query_logs(self,
                   start_date: Optional[date] = None,
                   end_date: Optional[date] = None,
                   operation_types: Optional[List[str]] = None,
                   modules: Optional[List[str]] = None,
                   statuses: Optional[List[str]] = None,
                   operators: Optional[List[str]] = None,
                   campaigns: Optional[List[str]] = None,
                   channels: Optional[List[str]] = None,
                   limit: int = 1000,
                   offset: int = 0) -> Tuple[List[LogEntry], int]:
        conditions = []
        params = []
        
        if start_date:
            conditions.append("date >= ?")
            params.append(start_date.isoformat())
        
        if end_date:
            conditions.append("date <= ?")
            params.append(end_date.isoformat())
        
        if operation_types:
            placeholders = ', '.join(['?'] * len(operation_types))
            conditions.append(f"operation_type IN ({placeholders})")
            params.extend(operation_types)
        
        if modules:
            placeholders = ', '.join(['?'] * len(modules))
            conditions.append(f"module IN ({placeholders})")
            params.extend(modules)
        
        if statuses:
            placeholders = ', '.join(['?'] * len(statuses))
            conditions.append(f"status IN ({placeholders})")
            params.extend(statuses)
        
        if operators:
            placeholders = ', '.join(['?'] * len(operators))
            conditions.append(f"operator IN ({placeholders})")
            params.extend(operators)
        
        if campaigns:
            placeholders = ', '.join(['?'] * len(campaigns))
            conditions.append(f"campaign IN ({placeholders})")
            params.extend(campaigns)
        
        if channels:
            placeholders = ', '.join(['?'] * len(channels))
            conditions.append(f"channel IN ({placeholders})")
            params.extend(channels)
        
        where_clause = " AND ".join(conditions) if conditions else "1=1"
        
        count_query = f"SELECT COUNT(*) as total FROM operation_logs WHERE {where_clause}"
        data_query = f"""
            SELECT * FROM operation_logs 
            WHERE {where_clause} 
            ORDER BY timestamp DESC 
            LIMIT ? OFFSET ?
        """
        params.extend([limit, offset])
        
        with self._get_connection() as conn:
            count_result = conn.execute(count_query, params[:-2]).fetchone()
            total = count_result['total'] if count_result else 0
            
            rows = conn.execute(data_query, params).fetchall()
        
        log_entries = []
        for row in rows:
            try:
                details = json.loads(row['details']) if row['details'] else {}
            except json.JSONDecodeError:
                details = {}
            
            log_entry = LogEntry(
                log_id=row['log_id'],
                timestamp=datetime.fromisoformat(row['timestamp']),
                operation_type=row['operation_type'],
                operator=row['operator'],
                module=row['module'],
                status=row['status'],
                details=details,
                error_message=row['error_message'],
                duration_ms=row['duration_ms']
            )
            log_entries.append(log_entry)
        
        logger.info(f"查询日志返回 {len(log_entries)}/{total} 条记录")
        
        return log_entries, total
    
    def query_logs_as_dataframe(self, **kwargs) -> pd.DataFrame:
        log_entries, total = self.query_logs(**kwargs)
        
        data = []
        for entry in log_entries:
            entry_dict = entry.model_dump()
            details = entry_dict.pop('details', {})
            entry_dict.update(details)
            data.append(entry_dict)
        
        df = pd.DataFrame(data)
        df.attrs['total'] = total
        
        return df
    
    def get_operation_statistics(self,
                                  start_date: date,
                                  end_date: date,
                                  group_by: str = "module") -> Dict[str, Any]:
        valid_group_bys = ["module", "operation_type", "status", "operator", "channel"]
        if group_by not in valid_group_bys:
            raise ValueError(f"group_by 必须是以下之一: {valid_group_bys}")
        
        query = f"""
            SELECT {group_by}, 
                   COUNT(*) as total_operations,
                   SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as success_count,
                   SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END) as error_count,
                   AVG(duration_ms) as avg_duration_ms
            FROM operation_logs
            WHERE date >= ? AND date <= ?
            GROUP BY {group_by}
            ORDER BY total_operations DESC
        """
        
        with self._get_connection() as conn:
            rows = conn.execute(query, [start_date.isoformat(), end_date.isoformat()]).fetchall()
        
        statistics = {
            'period': {
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat()
            },
            'group_by': group_by,
            'data': []
        }
        
        total_ops = 0
        total_success = 0
        total_errors = 0
        
        for row in rows:
            item = dict(row)
            success_rate = item['success_count'] / item['total_operations'] * 100 if item['total_operations'] > 0 else 0
            item['success_rate'] = round(success_rate, 2)
            statistics['data'].append(item)
            
            total_ops += item['total_operations']
            total_success += item['success_count']
            total_errors += item['error_count']
        
        statistics['summary'] = {
            'total_operations': total_ops,
            'success_count': total_success,
            'error_count': total_errors,
            'overall_success_rate': round(total_success / total_ops * 100, 2) if total_ops > 0 else 0
        }
        
        return statistics
    
    def get_recent_activities(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            rows = conn.execute('''
                SELECT * FROM operation_logs 
                ORDER BY timestamp DESC 
                LIMIT ?
            ''', [limit]).fetchall()
        
        activities = []
        for row in rows:
            try:
                details = json.loads(row['details']) if row['details'] else {}
            except json.JSONDecodeError:
                details = {}
            
            activity = {
                'log_id': row['log_id'],
                'timestamp': row['timestamp'],
                'operation_type': row['operation_type'],
                'module': row['module'],
                'status': row['status'],
                'operator': row['operator'],
                'summary': self._generate_activity_summary(row, details),
                'error_message': row['error_message']
            }
            activities.append(activity)
        
        return activities
    
    def _generate_activity_summary(self, row: sqlite3.Row, details: Dict[str, Any]) -> str:
        op_type = row['operation_type']
        module = row['module']
        channel = details.get('channel') or row['channel']
        
        summaries = {
            'data_collection': f"从{module}平台采集数据",
            'data_processing': f"处理{module}数据",
            'attribution_calculation': f"执行{module}归因计算",
            'roi_calculation': f"计算{module} ROI",
            'budget_adjustment': f"调整{channel or '渠道'}预算",
            'budget_rollback': f"回滚{channel or '渠道'}预算",
            'report_generation': f"生成{module}报告",
            'simulation': f"运行{module}模拟",
            'approval': f"{op_type}审批",
            'system': f"系统{op_type}"
        }
        
        base_summary = summaries.get(op_type, f"{op_type} - {module}")
        
        if row['status'] == 'success':
            return f"✓ {base_summary} 成功"
        else:
            return f"✗ {base_summary} 失败"
    
    def export_logs(self,
                    output_format: str = "xlsx",
                    filename_prefix: str = "operation_logs",
                    **query_kwargs) -> str:
        df = self.query_logs_as_dataframe(**query_kwargs)
        
        if df.empty:
            logger.warning("没有可导出的日志数据")
            return ""
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{filename_prefix}_{timestamp}.{output_format}"
        
        if output_format == "xlsx":
            output_path = self.export_engine.export_raw_data(df, filename)
        elif output_format == "csv":
            output_path = os.path.join(self.export_engine.output_dir, filename)
            df.to_csv(output_path, index=False, encoding='utf-8-sig')
            logger.info(f"日志已导出为CSV: {output_path}")
        elif output_format == "json":
            output_path = os.path.join(self.export_engine.output_dir, filename)
            df.to_json(output_path, orient='records', force_ascii=False, indent=2)
            logger.info(f"日志已导出为JSON: {output_path}")
        else:
            raise ValueError(f"不支持的导出格式: {output_format}")
        
        return output_path
    
    def batch_export(self,
                     export_configs: List[Dict[str, Any]]) -> List[str]:
        exported_files = []
        
        for config in export_configs:
            try:
                output_path = self.export_logs(**config)
                if output_path:
                    exported_files.append(output_path)
            except Exception as e:
                logger.error(f"批量导出失败: {e}, config={config}")
        
        return exported_files
    
    def cleanup_old_logs(self, retention_days: Optional[int] = None) -> int:
        retention_days = retention_days or settings.LOG_RETENTION_DAYS
        cutoff_date = date.today() - timedelta(days=retention_days)
        
        with self._get_connection() as conn:
            result = conn.execute('''
                DELETE FROM operation_logs 
                WHERE date < ?
            ''', [cutoff_date.isoformat()])
            conn.commit()
            
            deleted_count = result.rowcount
        
        logger.info(f"清理 {retention_days} 天前的日志，删除 {deleted_count} 条记录")
        
        return deleted_count
    
    def get_error_logs(self, 
                       start_date: Optional[date] = None,
                       end_date: Optional[date] = None,
                       limit: int = 100) -> List[Dict[str, Any]]:
        logs, _ = self.query_logs(
            start_date=start_date,
            end_date=end_date,
            statuses=["error"],
            limit=limit
        )
        
        return [log.model_dump() for log in logs]
    
    def get_channel_operations(self,
                                channel: str,
                                start_date: Optional[date] = None,
                                end_date: Optional[date] = None,
                                limit: int = 500) -> List[Dict[str, Any]]:
        logs, _ = self.query_logs(
            start_date=start_date,
            end_date=end_date,
            channels=[channel],
            limit=limit
        )
        
        return [log.model_dump() for log in logs]

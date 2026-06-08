import os
import sys
import argparse
from typing import Dict, List, Any, Optional
from datetime import date, datetime, timedelta
import pandas as pd

from utils.logger import logger
from config.settings import settings
from models.schemas import (
    AdPerformanceData, AttributionModelType, ChannelROI,
    BudgetAdjustmentSuggestion, SimulationConfig
)

from data_collector import DataCollectorManager, SampleDataGenerator
from data_processor import DataProcessor, DataAggregator
from attribution import (
    AttributionEngine, AttributionModelEvaluator,
    FirstClickAttribution, LastClickAttribution, LinearAttribution,
    TimeDecayAttribution, PositionBasedAttribution
)
from roi_analysis import ROICalculator, ChannelRanker
from budget_optimizer import BudgetOptimizer, RollbackManager
from approval import ApprovalWorkflow
from report_engine import ReportGenerator
from simulator import BudgetSimulator
from logging_system import OperationLogger
from scheduler import TaskScheduler


class MarketingAttributionSystem:
    def __init__(self, use_sample_data: bool = True):
        self.use_sample_data = use_sample_data
        
        self.data_collector = DataCollectorManager(use_sample_data=use_sample_data)
        self.sample_generator = SampleDataGenerator()
        self.data_processor = DataProcessor()
        self.data_aggregator = DataAggregator()
        
        self.attribution_models = {
            AttributionModelType.FIRST_CLICK: FirstClickAttribution(),
            AttributionModelType.LAST_CLICK: LastClickAttribution(),
            AttributionModelType.LINEAR: LinearAttribution(),
            AttributionModelType.TIME_DECAY: TimeDecayAttribution(),
            AttributionModelType.POSITION_BASED: PositionBasedAttribution()
        }
        self.attribution_engine = AttributionEngine()
        self.model_evaluator = AttributionModelEvaluator(self.attribution_engine)
        
        self.roi_calculator = ROICalculator()
        self.channel_ranker = ChannelRanker()
        
        self.budget_optimizer = BudgetOptimizer()
        self.rollback_manager = RollbackManager()
        self.approval_workflow = ApprovalWorkflow()
        
        self.report_generator = ReportGenerator()
        self.budget_simulator = BudgetSimulator()
        self.operation_logger = OperationLogger()
        self.scheduler = TaskScheduler()
        
        self._collected_data: List[AdPerformanceData] = []
        self._attribution_results: Dict[str, List] = {}
        self._roi_data: List[ChannelROI] = []
        self._budget_suggestions: List[BudgetAdjustmentSuggestion] = []
        
        logger.info("营销归因与预算优化系统已初始化")
    
    def run_data_collection(self, start_date: Optional[date] = None, 
                           end_date: Optional[date] = None,
                           days: int = 7,
                           records_per_day: int = 1000) -> pd.DataFrame:
        logger.info("开始数据采集流程...")
        
        if start_date is None and end_date is None:
            end_date = date.today()
            start_date = end_date - timedelta(days=days - 1)
        elif start_date is None:
            start_date = end_date - timedelta(days=days - 1)
        elif end_date is None:
            end_date = start_date + timedelta(days=days - 1)
        
        self.operation_logger.log_operation(
            operation_type="data_collection",
            module="data_collector",
            status="running",
            details={
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat()
            }
        )
        
        try:
            if self.use_sample_data:
                total_days = (end_date - start_date).days + 1
                self._collected_data = self.sample_generator.generate_massive_data(
                    num_days=total_days,
                    records_per_day=records_per_day,
                    start_date=start_date
                )
            else:
                self._collected_data = self.data_collector.collect_all_platforms(
                    start_date=start_date,
                    end_date=end_date
                )
            
            self.operation_logger.log_operation(
                operation_type="data_collection",
                module="data_collector",
                status="success",
                details={
                    'record_count': len(self._collected_data),
                    'start_date': start_date.isoformat(),
                    'end_date': end_date.isoformat()
                }
            )
            
            logger.info(f"数据采集完成，共 {len(self._collected_data)} 条记录")
            
            return self._collected_data
        except Exception as e:
            self.operation_logger.log_operation(
                operation_type="data_collection",
                module="data_collector",
                status="error",
                error_message=str(e)
            )
            raise
    
    def run_data_processing(self) -> pd.DataFrame:
        logger.info("开始数据处理流程...")
        
        if self._collected_data is None or (isinstance(self._collected_data, pd.DataFrame) and self._collected_data.empty) or (isinstance(self._collected_data, list) and len(self._collected_data) == 0):
            logger.warning("没有采集到的数据，先运行数据采集")
            return pd.DataFrame()
        
        self.operation_logger.log_operation(
            operation_type="data_processing",
            module="data_processor",
            status="running",
            details={'input_records': len(self._collected_data)}
        )
        
        try:
            df = self.data_processor.process_data(self._collected_data)
            
            processed_df = self.data_processor.clean_and_validate(df)
            
            self.operation_logger.log_operation(
                operation_type="data_processing",
                module="data_processor",
                status="success",
                details={
                    'processed_records': len(processed_df),
                    'removed_records': len(df) - len(processed_df)
                }
            )
            
            logger.info(f"数据处理完成，共 {len(processed_df)} 条有效记录")
            
            return processed_df
        except Exception as e:
            self.operation_logger.log_operation(
                operation_type="data_processing",
                module="data_processor",
                status="error",
                error_message=str(e)
            )
            raise
    
    def run_attribution(self, model_type: AttributionModelType = AttributionModelType.LAST_CLICK,
                       processed_df: Optional[pd.DataFrame] = None) -> List:
        logger.info(f"开始归因计算，使用模型: {model_type}")
        
        if processed_df is None and self._collected_data is not None and not (isinstance(self._collected_data, pd.DataFrame) and self._collected_data.empty):
            processed_df = self.run_data_processing()
        
        if processed_df is None or processed_df.empty:
            logger.warning("没有可用于归因的数据")
            return []
        
        self.operation_logger.log_operation(
            operation_type="attribution_calculation",
            module="attribution",
            status="running",
            details={'model': model_type.value}
        )
        
        try:
            model = self.attribution_models.get(model_type)
            if not model:
                raise ValueError(f"未知的归因模型: {model_type}")
            
            touchpoints = self.data_processor.extract_touchpoints(processed_df)
            conversion_paths = self.attribution_engine.build_conversion_paths(touchpoints)
            
            results = []
            for path in conversion_paths:
                result = model.attribute(path['touchpoints'], path['conversion_value'])
                results.append(result)
            
            self._attribution_results[model_type.value] = results
            
            self.operation_logger.log_operation(
                operation_type="attribution_calculation",
                module="attribution",
                status="success",
                details={
                    'model': model_type.value,
                    'paths_processed': len(results)
                }
            )
            
            logger.info(f"归因计算完成，处理 {len(results)} 条转化路径")
            
            return results
        except Exception as e:
            self.operation_logger.log_operation(
                operation_type="attribution_calculation",
                module="attribution",
                status="error",
                error_message=str(e)
            )
            raise
    
    def run_roi_analysis(self, attribution_results: Optional[List] = None,
                        model_type: AttributionModelType = AttributionModelType.LAST_CLICK,
                        processed_df: Optional[pd.DataFrame] = None) -> List[ChannelROI]:
        logger.info("开始ROI分析...")
        
        if processed_df is None and self._collected_data is not None and not (isinstance(self._collected_data, pd.DataFrame) and self._collected_data.empty):
            processed_df = self.run_data_processing()
        
        if processed_df is None or processed_df.empty:
            logger.warning("没有可用于ROI分析的数据")
            return []
        
        if attribution_results is None:
            attribution_results = self._attribution_results.get(model_type.value, [])
            if not attribution_results:
                attribution_results = self.run_attribution(model_type, processed_df)
        
        self.operation_logger.log_operation(
            operation_type="roi_calculation",
            module="roi_analysis",
            status="running"
        )
        
        try:
            daily_roi = self.roi_calculator.calculate_daily_roi(
                processed_df, attribution_results, model_type
            )
            
            self._roi_data = self.roi_calculator.calculate_weighted_roi(daily_roi)
            
            ranked_data = self.channel_ranker.rank_channels(self._roi_data)
            self._roi_data = ranked_data
            
            self.operation_logger.log_operation(
                operation_type="roi_calculation",
                module="roi_analysis",
                status="success",
                details={
                    'channels_analyzed': len(self._roi_data),
                    'model': model_type.value
                }
            )
            
            logger.info(f"ROI分析完成，分析 {len(self._roi_data)} 个渠道")
            
            return self._roi_data
        except Exception as e:
            self.operation_logger.log_operation(
                operation_type="roi_calculation",
                module="roi_analysis",
                status="error",
                error_message=str(e)
            )
            raise
    
    def run_budget_optimization(self, roi_data: Optional[List[ChannelROI]] = None,
                                historical_roi: Optional[Dict[str, List[float]]] = None,
                                processed_df: Optional[pd.DataFrame] = None) -> List[BudgetAdjustmentSuggestion]:
        logger.info("开始预算优化分析...")
        
        if roi_data is None:
            roi_data = self._roi_data
            if not roi_data:
                roi_data = self.run_roi_analysis()
        
        if processed_df is None and self._collected_data is not None and not (isinstance(self._collected_data, pd.DataFrame) and self._collected_data.empty):
            processed_df = self.run_data_processing()
        
        self.operation_logger.log_operation(
            operation_type="budget_optimization",
            module="budget_optimizer",
            status="running"
        )
        
        try:
            current_budgets = {roi.channel: roi.total_cost for roi in roi_data}
            
            self._budget_suggestions = self.budget_optimizer.generate_adjustment_suggestions(
                roi_data=roi_data,
                current_budgets=current_budgets,
                total_budget=settings.TOTAL_DAILY_BUDGET
            )
            
            if self._budget_suggestions:
                records = self.approval_workflow.submit_for_approval(
                    self._budget_suggestions
                )
                
                for suggestion, record in zip(self._budget_suggestions, records):
                    self.operation_logger.log_operation(
                        operation_type="budget_adjustment",
                        module="budget_optimizer",
                        status="pending_approval",
                        channel=suggestion.channel,
                        details={
                            'suggestion_id': suggestion.suggestion_id,
                            'adjustment_id': record.adjustment_id,
                            'current_budget': suggestion.current_budget,
                            'suggested_budget': suggestion.suggested_budget,
                            'adjustment_percent': suggestion.adjustment_percent
                        }
                    )
            
            self.operation_logger.log_operation(
                operation_type="budget_optimization",
                module="budget_optimizer",
                status="success",
                details={
                    'suggestions_count': len(self._budget_suggestions)
                }
            )
            
            logger.info(f"预算优化完成，生成 {len(self._budget_suggestions)} 条调整建议")
            
            return self._budget_suggestions
        except Exception as e:
            self.operation_logger.log_operation(
                operation_type="budget_optimization",
                module="budget_optimizer",
                status="error",
                error_message=str(e)
            )
            raise
    
    def check_rollback_conditions(self) -> List[Dict[str, Any]]:
        logger.info("检查回滚条件...")
        
        rollback_results = self.rollback_manager.check_all_monitoring_adjustments()
        
        for result in rollback_results:
            if result.get('rollback_needed'):
                self.operation_logger.log_operation(
                    operation_type="budget_rollback",
                    module="rollback_manager",
                    status="pending",
                    channel=result.get('channel'),
                    details={
                        'adjustment_id': result.get('adjustment_id'),
                        'reason': result.get('reason'),
                        'current_roi': result.get('current_roi'),
                        'baseline_roi': result.get('baseline_roi')
                    }
                )
        
        return rollback_results
    
    def approve_budget_adjustment(self, adjustment_id: str, approver: str,
                                  comments: Optional[str] = None) -> Optional[Any]:
        logger.info(f"批准预算调整: {adjustment_id}, 审批人: {approver}")
        
        record = self.approval_workflow.approve(adjustment_id, approver, comments)
        
        if record:
            self.rollback_manager.start_monitoring(record)
            
            self.operation_logger.log_operation(
                operation_type="approval",
                module="approval",
                status="approved",
                operator=approver,
                channel=record.channel,
                details={
                    'adjustment_id': adjustment_id,
                    'new_budget': record.new_budget,
                    'comments': comments
                }
            )
        
        return record
    
    def reject_budget_adjustment(self, adjustment_id: str, approver: str,
                                 reason: str) -> Optional[Any]:
        logger.info(f"拒绝预算调整: {adjustment_id}, 审批人: {approver}")
        
        record = self.approval_workflow.reject(adjustment_id, approver, reason)
        
        if record:
            self.operation_logger.log_operation(
                operation_type="approval",
                module="approval",
                status="rejected",
                operator=approver,
                channel=record.channel,
                details={
                    'adjustment_id': adjustment_id,
                    'reason': reason
                }
            )
        
        return record
    
    def generate_daily_report(self) -> Dict[str, Any]:
        logger.info("生成日报...")
        
        if not self._roi_data:
            self.run_roi_analysis()
        
        if not self._budget_suggestions:
            self.run_budget_optimization()
        
        daily_trends = {}
        dates = []
        if self._collected_data is not None and not (isinstance(self._collected_data, pd.DataFrame) and self._collected_data.empty):
            processed_df = self.run_data_processing()
            if not processed_df.empty:
                if hasattr(self.roi_calculator, 'get_daily_roi_trends'):
                    daily_trends = self.roi_calculator.get_daily_roi_trends(processed_df, days=7)
                dates = sorted(processed_df['date'].unique())[-7:]
        
        report = self.report_generator.generate_daily_report(
            roi_data=self._roi_data,
            daily_trends=daily_trends,
            dates=dates,
            budget_suggestions=self._budget_suggestions,
            adjustment_records=self.approval_workflow.approval_history[-10:]
        )
        
        self.operation_logger.log_operation(
            operation_type="report_generation",
            module="report_engine",
            status="success",
            details={
                'report_type': 'daily',
                'report_id': report.get('report_id'),
                'exported_files': list(report.get('exported_files', {}).values())
            }
        )
        
        return report
    
    def generate_weekly_report(self) -> Dict[str, Any]:
        logger.info("生成周报...")
        
        if not self._roi_data:
            self.run_roi_analysis()
        
        attribution_comparison = {}
        for model_type in AttributionModelType:
            results = self.run_attribution(model_type)
            if results:
                attribution_comparison[model_type.value] = self.attribution_engine.summarize_channel_contributions(results)
        
        model_evaluation = self.evaluate_attribution_models()
        
        conversion_paths = self._analyze_conversion_paths()
        
        report = self.report_generator.generate_weekly_report(
            weekly_roi_data=self._roi_data,
            attribution_comparison=attribution_comparison,
            model_evaluation=model_evaluation,
            conversion_paths=conversion_paths
        )
        
        self.operation_logger.log_operation(
            operation_type="report_generation",
            module="report_engine",
            status="success",
            details={
                'report_type': 'weekly',
                'report_id': report.get('report_id')
            }
        )
        
        return report
    
    def evaluate_attribution_models(self) -> Dict[str, Any]:
        logger.info("评估归因模型...")
        
        if not self._collected_data:
            self.run_data_collection()
        
        processed_df = self.run_data_processing()
        touchpoints = self.data_processor.extract_touchpoints(processed_df)
        conversion_paths = self.attribution_engine.build_conversion_paths(touchpoints)
        
        results = {}
        for model_type, model in self.attribution_models.items():
            model_results = []
            for path in conversion_paths:
                result = model.attribute(path['touchpoints'], path['conversion_value'])
                model_results.append(result)
            
            if model_results:
                results[model_type.value] = {
                    'attribution_results': model_results,
                    'channel_contributions': self.attribution_engine.summarize_channel_contributions(model_results)
                }
        
        evaluation = self.model_evaluator.evaluate_models(
            results=results,
            conversion_paths=conversion_paths
        )
        
        self.operation_logger.log_operation(
            operation_type="model_evaluation",
            module="attribution",
            status="success",
            details={
                'best_model': evaluation.get('best_model'),
                'models_evaluated': len(results)
            }
        )
        
        return evaluation
    
    def _analyze_conversion_paths(self) -> List[Dict[str, Any]]:
        if not self._collected_data:
            return []
        
        processed_df = self.run_data_processing()
        touchpoints = self.data_processor.extract_touchpoints(processed_df)
        conversion_paths = self.attribution_engine.build_conversion_paths(touchpoints)
        
        return self.attribution_engine.analyze_conversion_paths(conversion_paths)
    
    def run_budget_simulation(self, name: str, 
                              budget_adjustments: Dict[str, float],
                              description: Optional[str] = None) -> Any:
        logger.info(f"运行预算模拟: {name}")
        
        if not self._roi_data:
            self.run_roi_analysis()
        
        self.budget_simulator.load_historical_data(self._roi_data)
        
        config = self.budget_simulator.create_simulation(
            name=name,
            budget_adjustments=budget_adjustments,
            description=description
        )
        
        result = self.budget_simulator.run_simulation(config)
        
        self.operation_logger.log_operation(
            operation_type="simulation",
            module="simulator",
            status="success",
            details={
                'simulation_id': result.simulation_id,
                'name': name,
                'revenue_change_percent': result.revenue_change_percent,
                'roi_change_percent': result.roi_change_percent,
                'recommendation': result.recommendation
            }
        )
        
        return result
    
    def escalate_pending_approvals(self) -> List[Dict[str, Any]]:
        logger.info("检查逾期审批...")
        
        escalations = self.approval_workflow.escalate_pending_approvals()
        
        for escalation in escalations:
            self.operation_logger.log_operation(
                operation_type="approval_escalation",
                module="approval",
                status="pending",
                details=escalation
            )
        
        return escalations
    
    def cleanup_old_logs(self) -> int:
        logger.info("清理旧日志...")
        
        deleted_count = self.operation_logger.cleanup_old_logs()
        
        self.operation_logger.log_operation(
            operation_type="log_cleanup",
            module="system",
            status="success",
            details={'deleted_count': deleted_count}
        )
        
        return deleted_count
    
    def start_scheduler(self):
        logger.info("启动调度器...")
        
        self.scheduler.setup_default_schedule(self)
        self.scheduler.start()
        
        logger.info("调度器已启动，定时任务已配置")
    
    def stop_scheduler(self):
        logger.info("停止调度器...")
        self.scheduler.shutdown()
        logger.info("调度器已停止")
    
    def run_full_pipeline(self, days: int = 7) -> Dict[str, Any]:
        logger.info(f"运行完整处理流程，天数: {days}")
        
        end_date = date.today()
        start_date = end_date - timedelta(days=days)
        
        results = {}
        
        results['data_collection'] = self.run_data_collection(start_date, end_date)
        results['data_processing'] = self.run_data_processing()
        
        for model_type in AttributionModelType:
            results[f'attribution_{model_type.value}'] = self.run_attribution(model_type)
        
        results['roi_analysis'] = self.run_roi_analysis()
        results['budget_optimization'] = self.run_budget_optimization()
        results['daily_report'] = self.generate_daily_report()
        
        logger.info("完整处理流程完成")
        
        return results
    
    def get_system_status(self) -> Dict[str, Any]:
        return {
            'collected_data_count': len(self._collected_data),
            'roi_data_count': len(self._roi_data),
            'budget_suggestions_count': len(self._budget_suggestions),
            'pending_approvals_count': len(self.approval_workflow.pending_approvals),
            'scheduler_running': self.scheduler.scheduler.running,
            'scheduled_jobs': len(self.scheduler.get_jobs()),
            'use_sample_data': self.use_sample_data
        }


def main():
    parser = argparse.ArgumentParser(description='企业级营销归因与预算优化系统')
    parser.add_argument('--mode', choices=['demo', 'scheduler', 'pipeline', 'collect', 'attribution', 'optimize', 'report', 'simulate'],
                       default='demo', help='运行模式')
    parser.add_argument('--days', type=int, default=7, help='处理天数')
    parser.add_argument('--simulate-name', help='模拟场景名称')
    parser.add_argument('--simulate-channel', help='要调整的渠道')
    parser.add_argument('--simulate-percent', type=float, help='调整百分比(如0.1表示+10%)')
    parser.add_argument('--no-sample', action='store_true', help='不使用示例数据(需要真实API)')
    parser.add_argument('--no-scheduler', action='store_true', help='演示模式不启动调度器')
    parser.add_argument('--model', choices=['first_click', 'last_click', 'linear', 'time_decay', 'position_based'],
                       default='last_click', help='归因模型')
    parser.add_argument('--records-per-day', type=int, default=1000, help='每天生成的模拟数据量')
    
    args = parser.parse_args()
    
    system = MarketingAttributionSystem(use_sample_data=not args.no_sample)
    
    try:
        if args.mode == 'demo':
            logger.info("运行演示模式...")
            results = system.run_full_pipeline(days=args.days)
            
            print("\n" + "="*60)
            print("系统状态:")
            print("="*60)
            status = system.get_system_status()
            for key, value in status.items():
                print(f"  {key}: {value}")
            
            print("\n" + "="*60)
            print("渠道ROI排名:")
            print("="*60)
            for roi in sorted(system._roi_data, key=lambda x: x.rank):
                print(f"  #{roi.rank} {roi.channel:20s} ROI: {roi.roi:6.2f}  加权ROI: {roi.weighted_roi:6.2f}  ROAS: {roi.roas:6.2f}")
            
            if system._budget_suggestions:
                print("\n" + "="*60)
                print("预算调整建议:")
                print("="*60)
                for s in system._budget_suggestions:
                    print(f"  {s.channel:20s} {s.current_budget:10,.2f} → {s.suggested_budget:10,.2f} ({s.adjustment_percent*100:+6.1f}%)  原因: {s.reason}")
            
            report = results.get('daily_report', {})
            if 'exported_files' in report:
                print("\n" + "="*60)
                print("生成的报告文件:")
                print("="*60)
                for fmt, path in report['exported_files'].items():
                    print(f"  {fmt.upper()}: {path}")
            
            if not args.no_scheduler:
                print("\n" + "="*60)
                print("演示完成！启动调度器执行定时任务...")
                print("="*60)
                system.start_scheduler()
                
                print("\n调度器已启动，按 Ctrl+C 停止...")
                import time
                try:
                    while True:
                        time.sleep(60)
                except KeyboardInterrupt:
                    system.stop_scheduler()
                    print("\n调度器已停止")
            else:
                print("\n" + "="*60)
                print("演示完成！（未启动调度器）")
                print("="*60)
        
        elif args.mode == 'collect':
            logger.info(f"数据采集模式，采集 {args.days} 天数据...")
            data = system.run_data_collection(days=args.days, records_per_day=args.records_per_day)
            print("\n" + "="*60)
            print("数据采集完成:")
            print("="*60)
            print(f"  采集记录数: {len(data)}")
            print(f"  数据已保存到内存，可通过其他模式进一步处理")
            data.to_parquet('data/collected_data.parquet', index=False)
            print(f"  原始数据已保存: data/collected_data.parquet")
        
        elif args.mode == 'attribution':
            logger.info(f"归因计算模式，使用模型: {args.model}")
            from models import AttributionModelType
            model_type = AttributionModelType(args.model)
            
            if system._collected_data is None or (isinstance(system._collected_data, pd.DataFrame) and system._collected_data.empty):
                system.run_data_collection(days=args.days, records_per_day=args.records_per_day)
            
            processed_df = system.run_data_processing()
            results = system.run_attribution(model_type=model_type, processed_df=processed_df)
            
            print("\n" + "="*60)
            print(f"归因计算完成（模型: {args.model}）:")
            print("="*60)
            print(f"  处理转化路径数: {len(results)}")
            for i, result in enumerate(results[:5]):
                print(f"\n  路径 #{i+1}:")
                for channel, contribution in result.contributions.items():
                    print(f"    {channel}: {contribution:.2f}")
            
            import pickle
            with open('data/attribution_results.pkl', 'wb') as f:
                pickle.dump(results, f)
            print(f"\n  归因结果已保存: data/attribution_results.pkl")
        
        elif args.mode == 'optimize':
            logger.info("预算优化模式...")
            
            if system._collected_data is None or (isinstance(system._collected_data, pd.DataFrame) and system._collected_data.empty):
                system.run_data_collection(days=args.days, records_per_day=args.records_per_day)
            if not system._roi_data:
                system.run_roi_analysis()
            
            suggestions = system.run_budget_optimization()
            
            print("\n" + "="*60)
            print("预算优化建议:")
            print("="*60)
            if suggestions:
                for s in suggestions:
                    print(f"\n  渠道: {s.channel}")
                    print(f"    当前预算: {s.current_budget:,.2f} 元")
                    print(f"    建议预算: {s.suggested_budget:,.2f} 元")
                    print(f"    调整幅度: {s.adjustment_percent*100:+.1f}%")
                    print(f"    当前ROI: {s.current_roi:.2f}")
                    print(f"    预期ROI改善: {s.expected_roi_improvement:.2f}")
                    print(f"    风险等级: {s.risk_level}")
                    print(f"    原因: {s.reason}")
            else:
                print("  暂无预算调整建议，所有渠道表现正常")
            
            import json
            suggestions_data = [s.model_dump() for s in suggestions]
            with open('data/budget_suggestions.json', 'w', encoding='utf-8') as f:
                json.dump(suggestions_data, f, ensure_ascii=False, indent=2, default=str)
            print(f"\n  预算建议已保存: data/budget_suggestions.json")
        
        elif args.mode == 'scheduler':
            logger.info("启动调度模式...")
            system.start_scheduler()
            print("调度器已启动，按 Ctrl+C 停止...")
            
            import time
            try:
                while True:
                    time.sleep(60)
            except KeyboardInterrupt:
                system.stop_scheduler()
                print("\n调度器已停止")
        
        elif args.mode == 'pipeline':
            logger.info(f"运行完整处理流程，天数: {args.days}...")
            results = system.run_full_pipeline(days=args.days)
            print(f"处理完成！采集 {len(results.get('data_collection', []))} 条数据")
            print(f"生成报告: {results.get('daily_report', {}).get('exported_files', {})}")
        
        elif args.mode == 'report':
            logger.info("生成报告...")
            system.run_data_collection()
            system.run_roi_analysis()
            report = system.generate_daily_report()
            print(f"日报已生成: {report.get('exported_files', {})}")
            
            weekly_report = system.generate_weekly_report()
            print(f"周报已生成: {weekly_report.get('exported_files', {})}")
        
        elif args.mode == 'simulate':
            if not args.simulate_name or not args.simulate_channel or args.simulate_percent is None:
                print("错误: 模拟模式需要 --simulate-name, --simulate-channel, --simulate-percent 参数")
                print("示例: --mode simulate --simulate-name '增加抖音预算' --simulate-channel bytedance_douyin --simulate-percent 0.1")
                return
            
            logger.info(f"运行预算模拟: {args.simulate_name}")
            system.run_data_collection()
            system.run_roi_analysis()
            
            adjustments = {args.simulate_channel: args.simulate_percent}
            result = system.run_budget_simulation(
                name=args.simulate_name,
                budget_adjustments=adjustments,
                description=f"手动调整 {args.simulate_channel} 预算 {args.simulate_percent*100:+.1f}%"
            )
            
            print("\n" + "="*60)
            print(f"模拟结果: {args.simulate_name}")
            print("="*60)
            print(f"  基准总收入: {result.base_total_revenue:,.2f} 元")
            print(f"  模拟总收入: {result.simulated_total_revenue:,.2f} 元")
            print(f"  收入变化: {result.revenue_change_percent:+.2f}%")
            print(f"  基准ROI: {result.base_total_roi:.2f}")
            print(f"  模拟ROI: {result.simulated_total_roi:.2f}")
            print(f"  ROI变化: {result.roi_change_percent:+.2f}%")
            print(f"  置信区间: {result.confidence_interval['lower']:,.2f} ~ {result.confidence_interval['upper']:,.2f}")
            print(f"\n  建议: {result.recommendation}")
            
            print("\n  各渠道详细结果:")
            for channel, ch_result in result.channel_results.items():
                if ch_result['cost_change_percent'] != 0:
                    print(f"    {channel:20s} 预算: {ch_result['base_cost']:,.2f} → {ch_result['new_cost']:,.2f} ({ch_result['cost_change_percent']:+6.1f}%)  "
                          f"收入变化: {ch_result['revenue_change_percent']:+6.1f}%  ROI变化: {ch_result['roi_change_percent']:+6.1f}%")
    
    except Exception as e:
        logger.error(f"系统运行出错: {e}", exc_info=True)
        print(f"错误: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

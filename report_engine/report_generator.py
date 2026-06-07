import os
from typing import Dict, List, Any, Optional
from datetime import date, datetime, timedelta
import pandas as pd
import numpy as np

from utils.logger import logger
from utils.helpers import generate_id, round_float
from config.settings import settings
from models.schemas import (
    ReportConfig, ChannelROI, AttributionModelType,
    BudgetAdjustmentRecord
)
from .chart_generator import ChartGenerator
from .export_engine import ExportEngine


class ReportGenerator:
    def __init__(self):
        self.chart_generator = ChartGenerator()
        self.export_engine = ExportEngine()
        self.output_dir = os.path.join(settings.OUTPUT_DIR, "reports")
        os.makedirs(self.output_dir, exist_ok=True)
    
    def generate_daily_report(self, 
                              roi_data: List[ChannelROI],
                              daily_trends: Dict[str, List[float]],
                              dates: List[date],
                              budget_suggestions: List = None,
                              adjustment_records: List[BudgetAdjustmentRecord] = None) -> Dict[str, Any]:
        report_date = datetime.now().strftime('%Y-%m-%d')
        report_id = generate_id("report_daily")
        
        logger.info(f"开始生成日报: {report_id}, 日期: {report_date}")
        
        roi_dicts = [roi.model_dump() for roi in roi_data]
        
        summary = self._calculate_summary(roi_dicts)
        
        charts = []
        
        perf_chart_path = os.path.join(
            self.chart_generator.output_dir,
            f"channel_performance_{report_id}.png"
        )
        self.chart_generator.generate_channel_performance_chart(roi_dicts, perf_chart_path)
        if perf_chart_path:
            charts.append(perf_chart_path)
        
        if daily_trends and dates:
            trend_chart_path = os.path.join(
                self.chart_generator.output_dir,
                f"roi_trend_{report_id}.png"
            )
            self.chart_generator.generate_roi_trend_chart(daily_trends, dates, trend_chart_path)
            if trend_chart_path:
                charts.append(trend_chart_path)
        
        current_budget = {roi.channel: roi.total_cost for roi in roi_data}
        if budget_suggestions:
            suggested_budget = {s.channel: s.suggested_budget for s in budget_suggestions}
            budget_chart_path = os.path.join(
                self.chart_generator.output_dir,
                f"budget_distribution_{report_id}.png"
            )
            self.chart_generator.generate_budget_distribution_chart(
                current_budget, suggested_budget, budget_chart_path
            )
            if budget_chart_path:
                charts.append(budget_chart_path)
        
        data_tables = []
        
        channel_table = self._prepare_channel_table(roi_dicts)
        data_tables.append({
            'title': '渠道效能对比表',
            'sheet_name': '渠道效能',
            'data': channel_table
        })
        
        if budget_suggestions:
            budget_table = self._prepare_budget_suggestion_table(budget_suggestions)
            data_tables.append({
                'title': '预算调整建议',
                'sheet_name': '预算建议',
                'data': budget_table
            })
        
        if adjustment_records:
            adjustment_table = self._prepare_adjustment_records_table(adjustment_records)
            data_tables.append({
                'title': '预算调整记录',
                'sheet_name': '调整记录',
                'data': adjustment_table
            })
        
        recommendations = self._generate_recommendations(roi_dicts, budget_suggestions)
        
        report_data = {
            'report_id': report_id,
            'title': f'渠道效能日报 - {report_date}',
            'report_date': report_date,
            'summary': summary,
            'charts': charts,
            'data_tables': data_tables,
            'recommendations': recommendations
        }
        
        base_filename = f"daily_report_{report_date}_{report_id}"
        exported_files = self.export_engine.batch_export(report_data, base_filename)
        report_data['exported_files'] = exported_files
        
        logger.info(f"日报生成完成: {report_id}, 导出文件: {exported_files}")
        
        return report_data
    
    def generate_weekly_report(self,
                               weekly_roi_data: List[ChannelROI],
                               attribution_comparison: Dict[str, Dict[str, float]],
                               model_evaluation: Dict[str, Any],
                               conversion_paths: List[Dict]) -> Dict[str, Any]:
        report_date = datetime.now().strftime('%Y-%m-%d')
        report_id = generate_id("report_weekly")
        
        logger.info(f"开始生成周报: {report_id}, 日期: {report_date}")
        
        roi_dicts = [roi.model_dump() for roi in weekly_roi_data]
        
        summary = self._calculate_weekly_summary(roi_dicts, model_evaluation)
        
        charts = []
        
        perf_chart_path = os.path.join(
            self.chart_generator.output_dir,
            f"weekly_performance_{report_id}.png"
        )
        self.chart_generator.generate_channel_performance_chart(roi_dicts, perf_chart_path)
        if perf_chart_path:
            charts.append(perf_chart_path)
        
        if attribution_comparison:
            attr_chart_path = os.path.join(
                self.chart_generator.output_dir,
                f"attribution_comparison_{report_id}.png"
            )
            self.chart_generator.generate_attribution_model_comparison_chart(
                attribution_comparison, attr_chart_path
            )
            if attr_chart_path:
                charts.append(attr_chart_path)
        
        if conversion_paths:
            path_chart_path = os.path.join(
                self.chart_generator.output_dir,
                f"conversion_paths_{report_id}.png"
            )
            self.chart_generator.generate_conversion_path_chart(
                conversion_paths, path_chart_path
            )
            if path_chart_path:
                charts.append(path_chart_path)
        
        data_tables = []
        
        channel_table = self._prepare_channel_table(roi_dicts)
        data_tables.append({
            'title': '周度渠道效能对比',
            'sheet_name': '周度效能',
            'data': channel_table
        })
        
        if attribution_comparison:
            attr_table = self._prepare_attribution_comparison_table(attribution_comparison)
            data_tables.append({
                'title': '归因模型贡献对比',
                'sheet_name': '归因对比',
                'data': attr_table
            })
        
        if conversion_paths:
            path_table = self._prepare_conversion_path_table(conversion_paths)
            data_tables.append({
                'title': 'TOP转化路径',
                'sheet_name': '转化路径',
                'data': path_table
            })
        
        model_eval_table = self._prepare_model_evaluation_table(model_evaluation)
        data_tables.append({
            'title': '归因模型效果评估',
            'sheet_name': '模型评估',
            'data': model_eval_table
        })
        
        recommendations = self._generate_weekly_recommendations(roi_dicts, model_evaluation)
        
        report_data = {
            'report_id': report_id,
            'title': f'周度营销分析报告 - {report_date}',
            'report_date': report_date,
            'summary': summary,
            'charts': charts,
            'data_tables': data_tables,
            'recommendations': recommendations
        }
        
        base_filename = f"weekly_report_{report_date}_{report_id}"
        exported_files = self.export_engine.batch_export(report_data, base_filename)
        report_data['exported_files'] = exported_files
        
        logger.info(f"周报生成完成: {report_id}")
        
        return report_data
    
    def generate_attribution_model_report(self,
                                          model_results: Dict[str, Any],
                                          conversion_paths: List[Dict]) -> Dict[str, Any]:
        report_date = datetime.now().strftime('%Y-%m-%d')
        report_id = generate_id("report_attribution")
        
        logger.info(f"开始生成归因模型评估报告: {report_id}")
        
        charts = []
        
        comparison_data = {}
        for model_name, result in model_results.items():
            if 'channel_contributions' in result:
                comparison_data[model_name] = result['channel_contributions']
        
        if comparison_data:
            chart_path = os.path.join(
                self.chart_generator.output_dir,
                f"model_comparison_{report_id}.png"
            )
            self.chart_generator.generate_attribution_model_comparison_chart(
                comparison_data, chart_path
            )
            if chart_path:
                charts.append(chart_path)
        
        if conversion_paths:
            path_chart_path = os.path.join(
                self.chart_generator.output_dir,
                f"paths_{report_id}.png"
            )
            self.chart_generator.generate_conversion_path_chart(
                conversion_paths, path_chart_path
            )
            if path_chart_path:
                charts.append(path_chart_path)
        
        data_tables = []
        
        for model_name, result in model_results.items():
            if 'channel_contributions' in result:
                table_data = self._prepare_model_result_table(model_name, result)
                data_tables.append({
                    'title': f'{model_name}模型 - 渠道贡献',
                    'sheet_name': model_name[:31],
                    'data': table_data
                })
        
        eval_table = self._prepare_model_comparison_table(model_results)
        data_tables.append({
            'title': '模型效果对比',
            'sheet_name': '模型对比',
            'data': eval_table
        })
        
        summary = self._calculate_model_summary(model_results)
        recommendations = self._generate_model_recommendations(model_results)
        
        report_data = {
            'report_id': report_id,
            'title': f'归因模型效果评估报告 - {report_date}',
            'report_date': report_date,
            'summary': summary,
            'charts': charts,
            'data_tables': data_tables,
            'recommendations': recommendations
        }
        
        base_filename = f"attribution_report_{report_date}_{report_id}"
        exported_files = self.export_engine.batch_export(report_data, base_filename)
        report_data['exported_files'] = exported_files
        
        logger.info(f"归因模型报告生成完成: {report_id}")
        
        return report_data
    
    def _calculate_summary(self, roi_dicts: List[Dict]) -> Dict[str, Any]:
        df = pd.DataFrame(roi_dicts)
        if df.empty:
            return {}
        
        total_cost = df['total_cost'].sum()
        total_revenue = df['total_revenue'].sum()
        total_conversions = df['conversions'].sum()
        total_impressions = df['impressions'].sum()
        total_clicks = df['clicks'].sum()
        
        overall_roi = round_float(total_revenue / total_cost if total_cost > 0 else 0)
        overall_roas = round_float(total_revenue / total_cost if total_cost > 0 else 0)
        overall_cpa = round_float(total_cost / total_conversions if total_conversions > 0 else 0)
        overall_cvr = round_float(total_conversions / total_clicks if total_clicks > 0 else 0)
        overall_ctr = round_float(total_clicks / total_impressions if total_impressions > 0 else 0)
        
        channels_below_threshold = len(df[df['roi'] < settings.ROI_THRESHOLD])
        
        return {
            'total_cost': {'label': '总花费(元)', 'value': f"{total_cost:,.2f}", 'change': ''},
            'total_revenue': {'label': '总收入(元)', 'value': f"{total_revenue:,.2f}", 'change': ''},
            'total_conversions': {'label': '总转化数', 'value': f"{total_conversions:,}", 'change': ''},
            'total_impressions': {'label': '总曝光量', 'value': f"{total_impressions:,}", 'change': ''},
            'total_clicks': {'label': '总点击量', 'value': f"{total_clicks:,}", 'change': ''},
            'overall_roi': {'label': '整体ROI', 'value': f"{overall_roi:.2f}", 'change': ''},
            'overall_roas': {'label': '整体ROAS', 'value': f"{overall_roas:.2f}", 'change': ''},
            'overall_cpa': {'label': '整体CPA(元)', 'value': f"{overall_cpa:.2f}", 'change': ''},
            'overall_cvr': {'label': '整体CVR(%)', 'value': f"{overall_cvr * 100:.2f}%", 'change': ''},
            'overall_ctr': {'label': '整体CTR(%)', 'value': f"{overall_ctr * 100:.2f}%", 'change': ''},
            'channels_below_threshold': {
                'label': 'ROI低于阈值的渠道数', 
                'value': f"{channels_below_threshold}/{len(df)}", 
                'change': ''
            }
        }
    
    def _calculate_weekly_summary(self, roi_dicts: List[Dict], 
                                  model_evaluation: Dict[str, Any]) -> Dict[str, Any]:
        summary = self._calculate_summary(roi_dicts)
        
        if 'best_model' in model_evaluation:
            summary['best_attribution_model'] = {
                'label': '推荐归因模型',
                'value': model_evaluation['best_model'],
                'change': ''
            }
        
        if 'gini_coefficient' in model_evaluation:
            summary['model_gini'] = {
                'label': '最优模型Gini系数',
                'value': f"{model_evaluation['gini_coefficient']:.4f}",
                'change': ''
            }
        
        return summary
    
    def _calculate_model_summary(self, model_results: Dict[str, Any]) -> Dict[str, Any]:
        if not model_results:
            return {}
        
        best_model = None
        best_score = -1
        
        for model_name, result in model_results.items():
            score = result.get('overall_score', 0)
            if score > best_score:
                best_score = score
                best_model = model_name
        
        return {
            'total_models': {'label': '评估模型数', 'value': str(len(model_results)), 'change': ''},
            'best_model': {'label': '推荐最优模型', 'value': best_model or 'N/A', 'change': ''},
            'best_score': {'label': '最优模型评分', 'value': f"{best_score:.4f}" if best_score > 0 else 'N/A', 'change': ''}
        }
    
    def _prepare_channel_table(self, roi_dicts: List[Dict]) -> List[List[Any]]:
        if not roi_dicts:
            return []
        
        df = pd.DataFrame(roi_dicts).sort_values('rank')
        
        headers = ['排名', '渠道', '花费(元)', '收入(元)', 'ROI', 
                   '加权ROI', 'CPA(元)', 'CVR(%)', 'ROAS', 
                   '曝光量', '点击量', '转化量']
        
        rows = [headers]
        
        for _, row in df.iterrows():
            rows.append([
                int(row['rank']),
                row['channel'],
                round_float(row['total_cost']),
                round_float(row['total_revenue']),
                round_float(row['roi']),
                round_float(row['weighted_roi']),
                round_float(row['cpa']),
                round_float(row['cvr'] * 100),
                round_float(row['roas']),
                int(row['impressions']),
                int(row['clicks']),
                int(row['conversions'])
            ])
        
        return rows
    
    def _prepare_budget_suggestion_table(self, suggestions: List) -> List[List[Any]]:
        if not suggestions:
            return []
        
        headers = ['渠道', '当前预算(元)', '建议预算(元)', '调整幅度(%)', 
                   '当前ROI', '阈值', '连续低于阈值天数', 
                   '预期ROI提升', '预期收入变化', '风险等级', '原因']
        
        rows = [headers]
        
        for s in suggestions:
            s_dict = s.model_dump() if hasattr(s, 'model_dump') else s
            rows.append([
                s_dict['channel'],
                round_float(s_dict['current_budget']),
                round_float(s_dict['suggested_budget']),
                round_float(s_dict['adjustment_percent'] * 100),
                round_float(s_dict['current_roi']),
                round_float(s_dict['threshold']),
                int(s_dict['consecutive_days_below_threshold']),
                f"{round_float(s_dict['expected_roi_improvement'] * 100)}%",
                round_float(s_dict['expected_revenue_change']),
                s_dict['risk_level'],
                s_dict['reason']
            ])
        
        return rows
    
    def _prepare_adjustment_records_table(self, records: List[BudgetAdjustmentRecord]) -> List[List[Any]]:
        if not records:
            return []
        
        headers = ['调整ID', '渠道', '原预算(元)', '新预算(元)', '状态', 
                   '审批人', '审批时间', '执行时间', '回滚原因']
        
        rows = [headers]
        
        for r in records:
            r_dict = r.model_dump()
            rows.append([
                r_dict['adjustment_id'],
                r_dict['channel'],
                round_float(r_dict['old_budget']),
                round_float(r_dict['new_budget']),
                r_dict['status'],
                r_dict.get('approver') or '',
                str(r_dict.get('approved_at') or ''),
                str(r_dict.get('executed_at') or ''),
                r_dict.get('rollback_trigger') or ''
            ])
        
        return rows
    
    def _prepare_attribution_comparison_table(self, comparison: Dict[str, Dict[str, float]]) -> List[List[Any]]:
        if not comparison:
            return []
        
        channels = set()
        for result in comparison.values():
            channels.update(result.keys())
        channels = sorted(channels)
        
        headers = ['渠道'] + list(comparison.keys())
        rows = [headers]
        
        for ch in channels:
            row = [ch]
            for model in comparison.keys():
                row.append(round_float(comparison[model].get(ch, 0)))
            rows.append(row)
        
        return rows
    
    def _prepare_conversion_path_table(self, paths: List[Dict]) -> List[List[Any]]:
        if not paths:
            return []
        
        df = pd.DataFrame(paths).sort_values('conversion_count', ascending=False).head(20)
        
        headers = ['排名', '转化路径', '转化次数', '总价值(元)', '平均价值(元)']
        rows = [headers]
        
        for i, (_, row) in enumerate(df.iterrows(), 1):
            path_str = ' → '.join(row['path'][:5])
            if len(row['path']) > 5:
                path_str += f'...(+{len(row["path"]) - 5}步)'
            
            rows.append([
                i,
                path_str,
                int(row['conversion_count']),
                round_float(row['total_value']),
                round_float(row['avg_value'])
            ])
        
        return rows
    
    def _prepare_model_evaluation_table(self, evaluation: Dict[str, Any]) -> List[List[Any]]:
        if not evaluation or 'model_scores' not in evaluation:
            return []
        
        headers = ['模型', 'Gini系数', 'Spearman相关', 'MAE', 'RMSE', '综合评分', '推荐度']
        rows = [headers]
        
        for model, scores in evaluation['model_scores'].items():
            rows.append([
                model,
                round_float(scores.get('gini', 0)),
                round_float(scores.get('spearman', 0)),
                round_float(scores.get('mae', 0)),
                round_float(scores.get('rmse', 0)),
                round_float(scores.get('overall', 0)),
                '⭐' * int(scores.get('rating', 0))
            ])
        
        return rows
    
    def _prepare_model_result_table(self, model_name: str, result: Dict[str, Any]) -> List[List[Any]]:
        if 'channel_contributions' not in result:
            return []
        
        contributions = result['channel_contributions']
        headers = ['渠道', '贡献收入(元)', '占比(%)']
        rows = [headers]
        
        total = sum(contributions.values())
        for ch, value in sorted(contributions.items(), key=lambda x: x[1], reverse=True):
            rows.append([
                ch,
                round_float(value),
                round_float(value / total * 100 if total > 0 else 0)
            ])
        
        return rows
    
    def _prepare_model_comparison_table(self, model_results: Dict[str, Any]) -> List[List[Any]]:
        if not model_results:
            return []
        
        headers = ['指标']
        for model_name in model_results.keys():
            headers.append(model_name)
        rows = [headers]
        
        metrics = [
            ('gini_coefficient', 'Gini系数'),
            ('spearman_correlation', 'Spearman相关系数'),
            ('mae', '平均绝对误差'),
            ('rmse', '均方根误差'),
            ('overall_score', '综合评分'),
            ('conversions_covered', '覆盖转化数')
        ]
        
        for metric_key, metric_label in metrics:
            row = [metric_label]
            for result in model_results.values():
                row.append(round_float(result.get(metric_key, 0)))
            rows.append(row)
        
        return rows
    
    def _generate_recommendations(self, roi_dicts: List[Dict], 
                                  suggestions: List = None) -> List[str]:
        recommendations = []
        
        df = pd.DataFrame(roi_dicts)
        if df.empty:
            return recommendations
        
        below_threshold = df[df['roi'] < settings.ROI_THRESHOLD]
        if not below_threshold.empty:
            channels = ', '.join(below_threshold['channel'].tolist())
            recommendations.append(
                f"以下渠道ROI低于阈值({settings.ROI_THRESHOLD})，建议关注：{channels}"
            )
        
        top_3 = df.nsmallest(3, 'rank')
        for _, row in top_3.iterrows():
            recommendations.append(
                f"渠道【{row['channel']}】表现优异（排名第{int(row['rank'])}，ROI {row['roi']:.2f}），建议考虑增加预算"
            )
        
        if suggestions:
            recommendations.append(
                f"共有{len(suggestions)}条预算调整建议待审批，请及时处理"
            )
        
        return recommendations
    
    def _generate_weekly_recommendations(self, roi_dicts: List[Dict], 
                                         model_evaluation: Dict[str, Any]) -> List[str]:
        recommendations = self._generate_recommendations(roi_dicts)
        
        if 'best_model' in model_evaluation:
            recommendations.append(
                f"本周推荐使用【{model_evaluation['best_model']}】模型进行归因分析"
            )
        
        return recommendations
    
    def _generate_model_recommendations(self, model_results: Dict[str, Any]) -> List[str]:
        recommendations = []
        
        if not model_results:
            return recommendations
        
        best_model = None
        best_score = -1
        
        for model_name, result in model_results.items():
            score = result.get('overall_score', 0)
            if score > best_score:
                best_score = score
                best_model = model_name
        
        if best_model:
            recommendations.append(
                f"根据综合评估，推荐当前使用【{best_model}】归因模型（综合评分: {best_score:.4f}）"
            )
        
        for model_name, result in model_results.items():
            gini = result.get('gini_coefficient', 0)
            if gini < 0.3:
                recommendations.append(
                    f"模型【{model_name}】的Gini系数较低（{gini:.4f}），区分能力有限，建议谨慎使用"
                )
        
        return recommendations

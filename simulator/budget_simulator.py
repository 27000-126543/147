import os
from typing import Dict, List, Any, Optional, Tuple
from datetime import date, datetime
import pandas as pd
import numpy as np
from scipy import stats

from utils.logger import logger
from utils.helpers import generate_id, round_float, calculate_confidence_interval
from config.settings import settings
from models.schemas import (
    SimulationConfig, SimulationResult, ChannelROI,
    AttributionModelType
)
from report_engine.chart_generator import ChartGenerator


class BudgetSimulator:
    def __init__(self):
        self.chart_generator = ChartGenerator()
        self.historical_data: Optional[pd.DataFrame] = None
        self.channel_metrics: Optional[pd.DataFrame] = None
        self.output_dir = os.path.join(settings.OUTPUT_DIR, "simulations")
        os.makedirs(self.output_dir, exist_ok=True)
    
    def load_historical_data(self, roi_data: List[ChannelROI], 
                             daily_data: Optional[pd.DataFrame] = None):
        logger.info("加载历史数据用于模拟...")
        
        roi_dicts = [roi.model_dump() for roi in roi_data]
        self.channel_metrics = pd.DataFrame(roi_dicts)
        
        if daily_data is not None:
            self.historical_data = daily_data
        else:
            self.historical_data = self.channel_metrics.copy()
        
        logger.info(f"已加载 {len(self.channel_metrics)} 个渠道的历史数据")
    
    def create_simulation(self,
                          name: str,
                          budget_adjustments: Dict[str, float],
                          description: Optional[str] = None,
                          base_date: Optional[date] = None,
                          attribution_model: AttributionModelType = AttributionModelType.LAST_CLICK,
                          simulation_runs: int = 1000,
                          confidence_level: float = 0.95) -> SimulationConfig:
        sim_id = generate_id("sim")
        
        config = SimulationConfig(
            simulation_id=sim_id,
            name=name,
            description=description,
            base_date=base_date or date.today(),
            budget_adjustments=budget_adjustments,
            attribution_model=attribution_model,
            simulation_runs=simulation_runs,
            confidence_level=confidence_level
        )
        
        logger.info(f"创建模拟场景: {sim_id}, 名称: {name}")
        return config
    
    def run_simulation(self, config: SimulationConfig) -> SimulationResult:
        if self.channel_metrics is None:
            raise ValueError("请先调用 load_historical_data 加载历史数据")
        
        logger.info(f"开始运行模拟: {config.simulation_id}, 迭代次数: {config.simulation_runs}")
        
        base_metrics = self._calculate_base_metrics()
        base_total_revenue = base_metrics['total_revenue']
        base_total_roi = base_metrics['total_roi']
        
        channel_params = self._estimate_channel_parameters()
        
        simulation_results = []
        for i in range(config.simulation_runs):
            run_result = self._run_single_simulation(
                config.budget_adjustments, channel_params
            )
            simulation_results.append(run_result)
        
        sim_df = pd.DataFrame(simulation_results)
        
        simulated_total_revenue = sim_df['total_revenue'].mean()
        simulated_total_roi = sim_df['total_roi'].mean()
        
        revenue_change = (simulated_total_revenue - base_total_revenue) / base_total_revenue if base_total_revenue > 0 else 0
        roi_change = (simulated_total_roi - base_total_roi) / base_total_roi if base_total_roi > 0 else 0
        
        channel_results = self._calculate_channel_results(
            config.budget_adjustments, channel_params, sim_df
        )
        
        ci = calculate_confidence_interval(
            sim_df['total_revenue'].values,
            config.confidence_level
        )
        ci_lower, ci_upper = ci['lower'], ci['upper']
        confidence_interval = {
            'lower': round_float(ci_lower),
            'upper': round_float(ci_upper),
            'level': config.confidence_level,
            'margin': round_float((ci_upper - ci_lower) / 2)
        }
        
        recommendation = self._generate_recommendation(
            base_total_revenue, simulated_total_revenue,
            base_total_roi, simulated_total_roi,
            config.budget_adjustments
        )
        
        charts_data = self._generate_simulation_charts(
            config, base_metrics, channel_params, sim_df
        )
        
        result = SimulationResult(
            simulation_id=config.simulation_id,
            base_total_revenue=round_float(base_total_revenue),
            simulated_total_revenue=round_float(simulated_total_revenue),
            revenue_change_percent=round_float(revenue_change * 100),
            base_total_roi=round_float(base_total_roi),
            simulated_total_roi=round_float(simulated_total_roi),
            roi_change_percent=round_float(roi_change * 100),
            channel_results=channel_results,
            confidence_interval=confidence_interval,
            recommendation=recommendation,
            charts_data=charts_data
        )
        
        logger.info(f"模拟完成: {config.simulation_id}")
        logger.info(f"预期收入变化: {revenue_change * 100:+.2f}%, 预期ROI变化: {roi_change * 100:+.2f}%")
        
        return result
    
    def _calculate_base_metrics(self) -> Dict[str, float]:
        df = self.channel_metrics
        
        total_cost = df['total_cost'].sum()
        total_revenue = df['total_revenue'].sum()
        total_roi = total_revenue / total_cost if total_cost > 0 else 0
        
        return {
            'total_cost': total_cost,
            'total_revenue': total_revenue,
            'total_roi': total_roi,
            'total_conversions': df['conversions'].sum(),
            'total_clicks': df['clicks'].sum(),
            'total_impressions': df['impressions'].sum()
        }
    
    def _estimate_channel_parameters(self) -> Dict[str, Dict[str, float]]:
        params = {}
        
        for _, row in self.channel_metrics.iterrows():
            channel = row['channel']
            cost = row['total_cost']
            revenue = row['total_revenue']
            conversions = row['conversions']
            clicks = row['clicks']
            
            roas = revenue / cost if cost > 0 else 0
            cvr = conversions / clicks if clicks > 0 else 0
            cpa = cost / conversions if conversions > 0 else 0
            
            roas_std = abs(roas) * 0.15
            cvr_std = cvr * 0.1 if cvr > 0 else 0.01
            cpa_std = cpa * 0.1 if cpa > 0 else 10
            
            marginal_roi = self._estimate_marginal_roi(roas)
            
            params[channel] = {
                'base_cost': cost,
                'base_revenue': revenue,
                'base_conversions': conversions,
                'base_roas': roas,
                'base_cvr': cvr,
                'base_cpa': cpa,
                'roas_std': roas_std,
                'cvr_std': cvr_std,
                'cpa_std': cpa_std,
                'marginal_roi': marginal_roi,
                'saturation_point': cost * 3,
                'diminishing_factor': 0.85
            }
        
        return params
    
    def _estimate_marginal_roi(self, base_roas: float) -> float:
        if base_roas > 5:
            return 0.9
        elif base_roas > 3:
            return 0.75
        elif base_roas > 2:
            return 0.6
        elif base_roas > 1:
            return 0.4
        else:
            return 0.2
    
    def _run_single_simulation(self, 
                               budget_adjustments: Dict[str, float],
                               channel_params: Dict[str, Dict[str, float]]) -> Dict[str, float]:
        total_revenue = 0
        total_cost = 0
        channel_revenues = {}
        channel_costs = {}
        
        for channel, params in channel_params.items():
            base_cost = params['base_cost']
            
            adjustment = budget_adjustments.get(channel, 0)
            new_cost = base_cost * (1 + adjustment)
            
            min_budget = settings.CHANNEL_CONFIG.get(channel, {}).get('min_budget', 0)
            max_budget = settings.CHANNEL_CONFIG.get(channel, {}).get('max_budget', float('inf'))
            new_cost = max(min_budget, min(new_cost, max_budget))
            
            roas_mean = params['base_roas']
            roas_std = params['roas_std']
            simulated_roas = max(0, np.random.normal(roas_mean, roas_std))
            
            cost_ratio = new_cost / base_cost if base_cost > 0 else 1
            
            if cost_ratio > 1:
                excess_ratio = cost_ratio - 1
                diminishing = params['diminishing_factor'] ** min(excess_ratio, 5)
                effective_roas = simulated_roas * (1 - (1 - diminishing) * min(excess_ratio, 2))
            else:
                effective_roas = simulated_roas
            
            revenue = new_cost * effective_roas
            
            cvr_mean = params['base_cvr']
            cvr_std = params['cvr_std']
            simulated_cvr = max(0.001, np.random.normal(cvr_mean, cvr_std))
            
            cpc = base_cost / params['base_conversions'] * simulated_cvr if params['base_conversions'] > 0 else 1
            clicks = new_cost / cpc if cpc > 0 else 0
            conversions = clicks * simulated_cvr
            
            channel_revenues[channel] = revenue
            channel_costs[channel] = new_cost
            
            total_revenue += revenue
            total_cost += new_cost
        
        total_roi = total_revenue / total_cost if total_cost > 0 else 0
        
        result = {
            'total_revenue': total_revenue,
            'total_cost': total_cost,
            'total_roi': total_roi,
        }
        result.update({f'revenue_{ch}': rev for ch, rev in channel_revenues.items()})
        result.update({f'cost_{ch}': cost for ch, cost in channel_costs.items()})
        
        return result
    
    def _calculate_channel_results(self,
                                   budget_adjustments: Dict[str, float],
                                   channel_params: Dict[str, Dict[str, float]],
                                   sim_df: pd.DataFrame) -> Dict[str, Dict[str, float]]:
        results = {}
        
        for channel in channel_params.keys():
            params = channel_params[channel]
            base_cost = params['base_cost']
            base_revenue = params['base_revenue']
            base_roi = params['base_roas']
            
            adjustment = budget_adjustments.get(channel, 0)
            new_cost = base_cost * (1 + adjustment)
            
            sim_revenue_col = f'revenue_{channel}'
            if sim_revenue_col in sim_df.columns:
                simulated_revenue = sim_df[sim_revenue_col].mean()
            else:
                simulated_revenue = new_cost * params['base_roas']
            
            simulated_roi = simulated_revenue / new_cost if new_cost > 0 else 0
            
            revenue_change = (simulated_revenue - base_revenue) / base_revenue if base_revenue > 0 else 0
            roi_change = (simulated_roi - base_roi) / base_roi if base_roi > 0 else 0
            
            ci = calculate_confidence_interval(
                sim_df[sim_revenue_col].values if sim_revenue_col in sim_df.columns else [simulated_revenue],
                0.95
            )
            ci_lower, ci_upper = ci['lower'], ci['upper']
            
            results[channel] = {
                'base_cost': round_float(base_cost),
                'new_cost': round_float(new_cost),
                'cost_change_percent': round_float(adjustment * 100),
                'base_revenue': round_float(base_revenue),
                'simulated_revenue': round_float(simulated_revenue),
                'revenue_change_percent': round_float(revenue_change * 100),
                'base_roi': round_float(base_roi),
                'simulated_roi': round_float(simulated_roi),
                'roi_change_percent': round_float(roi_change * 100),
                'ci_lower': round_float(ci_lower),
                'ci_upper': round_float(ci_upper)
            }
        
        return results
    
    def _generate_simulation_charts(self,
                                    config: SimulationConfig,
                                    base_metrics: Dict[str, float],
                                    channel_params: Dict[str, Dict[str, float]],
                                    sim_df: pd.DataFrame) -> Dict[str, Any]:
        charts = {}
        
        base_chart_path = os.path.join(
            self.chart_generator.output_dir,
            f"sim_comparison_{config.simulation_id}.png"
        )
        
        channels = list(channel_params.keys())
        base_channel_revenue = {ch: params['base_revenue'] for ch, params in channel_params.items()}
        simulated_channel_revenue = {}
        for ch in channels:
            col = f'revenue_{ch}'
            if col in sim_df.columns:
                simulated_channel_revenue[ch] = sim_df[col].mean()
            else:
                simulated_channel_revenue[ch] = base_channel_revenue.get(ch, 0)
        
        base_metrics_simple = {
            '总收入': base_metrics['total_revenue'],
            '平均ROI': base_metrics['total_roi'],
            '总转化数': base_metrics['total_conversions'],
            '总花费': base_metrics['total_cost']
        }
        
        simulated_metrics_simple = {
            '总收入': sim_df['total_revenue'].mean(),
            '平均ROI': sim_df['total_roi'].mean(),
            '总转化数': base_metrics['total_conversions'] * (1 + (sim_df['total_revenue'].mean() - base_metrics['total_revenue']) / base_metrics['total_revenue']),
            '总花费': sim_df['total_cost'].mean()
        }
        
        self.chart_generator.generate_simulation_comparison_chart(
            base_metrics_simple, simulated_metrics_simple, base_chart_path
        )
        charts['comparison'] = base_chart_path
        
        dist_chart_path = os.path.join(
            self.chart_generator.output_dir,
            f"sim_distribution_{config.simulation_id}.png"
        )
        self._generate_revenue_distribution_chart(sim_df, dist_chart_path)
        charts['distribution'] = dist_chart_path
        
        return charts
    
    def _generate_revenue_distribution_chart(self, sim_df: pd.DataFrame, output_path: str):
        import matplotlib.pyplot as plt
        
        fig, ax = plt.subplots(figsize=(12, 6))
        
        revenues = sim_df['total_revenue'].values
        mean_rev = revenues.mean()
        median_rev = np.median(revenues)
        
        n, bins, patches = ax.hist(revenues, bins=50, alpha=0.7, 
                                  color='#3498db', edgecolor='white', density=True)
        
        ax.axvline(mean_rev, color='#e74c3c', linestyle='--', linewidth=2,
                  label=f'均值: {mean_rev:,.0f}')
        ax.axvline(median_rev, color='#2ecc71', linestyle='--', linewidth=2,
                  label=f'中位数: {median_rev:,.0f}')
        
        ax.set_title('模拟收入分布', fontsize=14, fontweight='bold')
        ax.set_xlabel('收入(元)')
        ax.set_ylabel('概率密度')
        ax.legend()
        ax.grid(axis='y', alpha=0.3)
        
        from scipy.stats import norm
        mu, std = norm.fit(revenues)
        xmin, xmax = ax.get_xlim()
        x = np.linspace(xmin, xmax, 100)
        p = norm.pdf(x, mu, std)
        ax.plot(x, p, 'k', linewidth=2, alpha=0.7, label=f'正态分布拟合\nμ={mu:,.0f}, σ={std:,.0f}')
        ax.legend()
        
        plt.tight_layout()
        plt.savefig(output_path, dpi=150, bbox_inches='tight')
        plt.close()
        
        return output_path
    
    def _generate_recommendation(self,
                                 base_revenue: float,
                                 simulated_revenue: float,
                                 base_roi: float,
                                 simulated_roi: float,
                                 budget_adjustments: Dict[str, float]) -> str:
        revenue_change = (simulated_revenue - base_revenue) / base_revenue if base_revenue > 0 else 0
        roi_change = (simulated_roi - base_roi) / base_roi if base_roi > 0 else 0
        
        increased_channels = [ch for ch, adj in budget_adjustments.items() if adj > 0]
        decreased_channels = [ch for ch, adj in budget_adjustments.items() if adj < 0]
        
        parts = []
        
        if revenue_change > 0.05 and roi_change > 0:
            parts.append(f"强烈推荐执行该预算调整方案。")
            parts.append(f"预期收入提升 {revenue_change * 100:+.2f}%，ROI提升 {roi_change * 100:+.2f}%。")
        elif revenue_change > 0:
            parts.append(f"建议执行该预算调整方案。")
            parts.append(f"预期收入提升 {revenue_change * 100:+.2f}%，但ROI变化 {roi_change * 100:+.2f}%。")
        elif roi_change > 0:
            parts.append(f"可考虑执行该方案。")
            parts.append(f"虽然预期收入变化 {revenue_change * 100:+.2f}%，但ROI提升 {roi_change * 100:+.2f}%。")
        else:
            parts.append(f"不推荐执行该预算调整方案。")
            parts.append(f"预期收入变化 {revenue_change * 100:+.2f}%，ROI变化 {roi_change * 100:+.2f}%。")
        
        if increased_channels:
            parts.append(f"增加预算的渠道: {', '.join(increased_channels)}")
        if decreased_channels:
            parts.append(f"削减预算的渠道: {', '.join(decreased_channels)}")
        
        return ' '.join(parts)
    
    def batch_simulate(self, scenarios: List[Dict[str, Any]]) -> List[SimulationResult]:
        results = []
        
        for scenario in scenarios:
            config = self.create_simulation(
                name=scenario['name'],
                budget_adjustments=scenario['budget_adjustments'],
                description=scenario.get('description')
            )
            result = self.run_simulation(config)
            results.append(result)
        
        return results
    
    def compare_scenarios(self, results: List[SimulationResult]) -> Dict[str, Any]:
        if not results:
            return {}
        
        best_revenue_idx = max(range(len(results)), 
                              key=lambda i: results[i].simulated_total_revenue)
        best_roi_idx = max(range(len(results)), 
                          key=lambda i: results[i].simulated_total_roi)
        
        comparison = {
            'total_scenarios': len(results),
            'best_revenue_scenario': {
                'simulation_id': results[best_revenue_idx].simulation_id,
                'revenue': results[best_revenue_idx].simulated_total_revenue,
                'change_percent': results[best_revenue_idx].revenue_change_percent
            },
            'best_roi_scenario': {
                'simulation_id': results[best_roi_idx].simulation_id,
                'roi': results[best_roi_idx].simulated_total_roi,
                'change_percent': results[best_roi_idx].roi_change_percent
            },
            'scenarios': []
        }
        
        for result in results:
            comparison['scenarios'].append({
                'simulation_id': result.simulation_id,
                'simulated_revenue': result.simulated_total_revenue,
                'revenue_change': result.revenue_change_percent,
                'simulated_roi': result.simulated_total_roi,
                'roi_change': result.roi_change_percent,
                'recommendation': result.recommendation
            })
        
        return comparison

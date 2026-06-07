import os
from typing import Dict, List, Any, Optional
from datetime import date
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib
from matplotlib import font_manager
from utils.logger import logger
from config.settings import settings

matplotlib.use('Agg')


class ChartGenerator:
    def __init__(self):
        self.output_dir = os.path.join(settings.OUTPUT_DIR, "charts")
        os.makedirs(self.output_dir, exist_ok=True)
        self._setup_chinese_font()
        
    def _setup_chinese_font(self):
        try:
            plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'SimHei', 'Microsoft YaHei']
            plt.rcParams['axes.unicode_minus'] = False
        except Exception as e:
            logger.warning(f"字体设置失败: {e}")
    
    def generate_channel_performance_chart(self, roi_data: List[Dict], output_path: str) -> str:
        df = pd.DataFrame(roi_data)
        if df.empty:
            logger.warning("ROI数据为空，跳过图表生成")
            return ""
        
        fig, axes = plt.subplots(2, 2, figsize=(16, 12))
        fig.suptitle('渠道效能对比分析', fontsize=16, fontweight='bold')
        
        channels = df['channel'].tolist()
        x = np.arange(len(channels))
        
        axes[0, 0].bar(x, df['roi'].values, color='#3498db', alpha=0.8)
        axes[0, 0].set_title('各渠道ROI对比')
        axes[0, 0].set_xticks(x)
        axes[0, 0].set_xticklabels(channels, rotation=45, ha='right')
        axes[0, 0].axhline(y=settings.ROI_THRESHOLD, color='red', linestyle='--', label=f'阈值={settings.ROI_THRESHOLD}')
        axes[0, 0].legend()
        axes[0, 0].grid(axis='y', alpha=0.3)
        
        axes[0, 1].bar(x, df['roas'].values, color='#2ecc71', alpha=0.8)
        axes[0, 1].set_title('各渠道ROAS对比')
        axes[0, 1].set_xticks(x)
        axes[0, 1].set_xticklabels(channels, rotation=45, ha='right')
        axes[0, 1].grid(axis='y', alpha=0.3)
        
        axes[1, 0].bar(x, df['cpa'].values, color='#e74c3c', alpha=0.8)
        axes[1, 0].set_title('各渠道CPA对比(元)')
        axes[1, 0].set_xticks(x)
        axes[1, 0].set_xticklabels(channels, rotation=45, ha='right')
        axes[1, 0].grid(axis='y', alpha=0.3)
        
        axes[1, 1].bar(x, df['cvr'].values * 100, color='#f39c12', alpha=0.8)
        axes[1, 1].set_title('各渠道CVR对比(%)')
        axes[1, 1].set_xticks(x)
        axes[1, 1].set_xticklabels(channels, rotation=45, ha='right')
        axes[1, 1].grid(axis='y', alpha=0.3)
        
        plt.tight_layout()
        plt.savefig(output_path, dpi=150, bbox_inches='tight')
        plt.close()
        
        logger.info(f"渠道效能图表已生成: {output_path}")
        return output_path
    
    def generate_roi_trend_chart(self, daily_roi: Dict[str, List[float]], dates: List[date], output_path: str) -> str:
        fig, ax = plt.subplots(figsize=(14, 7))
        
        colors = ['#3498db', '#e74c3c', '#2ecc71', '#f39c12', '#9b59b6', '#1abc9c', '#e67e22', '#34495e', '#16a085']
        
        for i, (channel, roi_values) in enumerate(daily_roi.items()):
            if len(roi_values) == len(dates):
                ax.plot(dates, roi_values, marker='o', label=channel, 
                       color=colors[i % len(colors)], linewidth=2, markersize=6)
        
        ax.axhline(y=settings.ROI_THRESHOLD, color='red', linestyle='--', 
                  label=f'ROI阈值={settings.ROI_THRESHOLD}', linewidth=2)
        ax.set_title('渠道ROI趋势分析', fontsize=14, fontweight='bold')
        ax.set_xlabel('日期')
        ax.set_ylabel('ROI')
        ax.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
        ax.grid(True, alpha=0.3)
        plt.xticks(rotation=45)
        
        plt.tight_layout()
        plt.savefig(output_path, dpi=150, bbox_inches='tight')
        plt.close()
        
        logger.info(f"ROI趋势图表已生成: {output_path}")
        return output_path
    
    def generate_budget_distribution_chart(self, current_budget: Dict[str, float], 
                                           suggested_budget: Optional[Dict[str, float]] = None,
                                           output_path: str = "") -> str:
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 8))
        
        channels = list(current_budget.keys())
        current_values = list(current_budget.values())
        
        colors = ['#3498db', '#e74c3c', '#2ecc71', '#f39c12', '#9b59b6', '#1abc9c', '#e67e22', '#34495e', '#16a085']
        
        wedges1, texts1, autotexts1 = ax1.pie(current_values, labels=channels, autopct='%1.1f%%',
                                              colors=colors, startangle=90)
        ax1.set_title('当前预算分配', fontsize=12, fontweight='bold')
        
        if suggested_budget:
            suggested_values = [suggested_budget.get(ch, 0) for ch in channels]
            wedges2, texts2, autotexts2 = ax2.pie(suggested_values, labels=channels, autopct='%1.1f%%',
                                                  colors=colors, startangle=90)
            ax2.set_title('建议预算分配', fontsize=12, fontweight='bold')
        else:
            ax2.remove()
        
        plt.tight_layout()
        plt.savefig(output_path, dpi=150, bbox_inches='tight')
        plt.close()
        
        logger.info(f"预算分配图表已生成: {output_path}")
        return output_path
    
    def generate_attribution_model_comparison_chart(self, model_results: Dict[str, Dict[str, float]], 
                                                    output_path: str) -> str:
        models = list(model_results.keys())
        channels = set()
        for result in model_results.values():
            channels.update(result.keys())
        channels = sorted(channels)
        
        fig, ax = plt.subplots(figsize=(14, 7))
        
        x = np.arange(len(channels))
        width = 0.15
        
        colors = ['#3498db', '#e74c3c', '#2ecc71', '#f39c12', '#9b59b6']
        
        for i, model in enumerate(models):
            values = [model_results[model].get(ch, 0) for ch in channels]
            ax.bar(x + i * width, values, width, label=model, 
                   color=colors[i % len(colors)], alpha=0.8)
        
        ax.set_title('不同归因模型下渠道贡献对比', fontsize=14, fontweight='bold')
        ax.set_xlabel('渠道')
        ax.set_ylabel('贡献收入(元)')
        ax.set_xticks(x + width * (len(models) - 1) / 2)
        ax.set_xticklabels(channels, rotation=45, ha='right')
        ax.legend()
        ax.grid(axis='y', alpha=0.3)
        
        plt.tight_layout()
        plt.savefig(output_path, dpi=150, bbox_inches='tight')
        plt.close()
        
        logger.info(f"归因模型对比图表已生成: {output_path}")
        return output_path
    
    def generate_conversion_path_chart(self, path_data: List[Dict], output_path: str) -> str:
        df = pd.DataFrame(path_data)
        if df.empty:
            return ""
        
        top_paths = df.head(10)
        
        fig, ax = plt.subplots(figsize=(12, 8))
        
        y_pos = np.arange(len(top_paths))
        ax.barh(y_pos, top_paths['conversion_count'].values, color='#3498db', alpha=0.8)
        ax.set_yticks(y_pos)
        ax.set_yticklabels(top_paths['path'].apply(lambda x: ' → '.join(x[:3]) + ('...' if len(x) > 3 else '')).values)
        ax.invert_yaxis()
        ax.set_xlabel('转化次数')
        ax.set_title('TOP10转化路径', fontsize=14, fontweight='bold')
        ax.grid(axis='x', alpha=0.3)
        
        for i, v in enumerate(top_paths['conversion_count'].values):
            ax.text(v + 0.5, i, str(v), va='center')
        
        plt.tight_layout()
        plt.savefig(output_path, dpi=150, bbox_inches='tight')
        plt.close()
        
        logger.info(f"转化路径图表已生成: {output_path}")
        return output_path
    
    def generate_simulation_comparison_chart(self, base_metrics: Dict[str, float], 
                                             simulated_metrics: Dict[str, float],
                                             output_path: str) -> str:
        metrics = list(base_metrics.keys())
        base_values = [base_metrics[m] for m in metrics]
        simulated_values = [simulated_metrics.get(m, 0) for m in metrics]
        
        fig, ax = plt.subplots(figsize=(12, 6))
        
        x = np.arange(len(metrics))
        width = 0.35
        
        bars1 = ax.bar(x - width/2, base_values, width, label='基准方案', color='#3498db', alpha=0.8)
        bars2 = ax.bar(x + width/2, simulated_values, width, label='模拟方案', color='#2ecc71', alpha=0.8)
        
        ax.set_title('模拟方案 vs 基准方案 效果对比', fontsize=14, fontweight='bold')
        ax.set_xticks(x)
        ax.set_xticklabels(metrics, rotation=45, ha='right')
        ax.legend()
        ax.grid(axis='y', alpha=0.3)
        
        for bars in [bars1, bars2]:
            for bar in bars:
                height = bar.get_height()
                ax.text(bar.get_x() + bar.get_width()/2., height,
                       f'{height:.2f}', ha='center', va='bottom', fontsize=9)
        
        plt.tight_layout()
        plt.savefig(output_path, dpi=150, bbox_inches='tight')
        plt.close()
        
        logger.info(f"模拟对比图表已生成: {output_path}")
        return output_path
    
    def generate_hourly_distribution_chart(self, hourly_data: Dict[int, Dict[str, float]], 
                                           output_path: str) -> str:
        hours = list(range(24))
        impressions = [hourly_data.get(h, {}).get('impressions', 0) for h in hours]
        clicks = [hourly_data.get(h, {}).get('clicks', 0) for h in hours]
        conversions = [hourly_data.get(h, {}).get('conversions', 0) for h in hours]
        
        fig, ax1 = plt.subplots(figsize=(14, 7))
        
        ax2 = ax1.twinx()
        
        x = np.arange(24)
        width = 0.25
        
        ax1.bar(x - width, impressions, width, label='曝光量', color='#3498db', alpha=0.7)
        ax1.bar(x, clicks, width, label='点击量', color='#2ecc71', alpha=0.7)
        ax2.bar(x + width, conversions, width, label='转化量', color='#e74c3c', alpha=0.7)
        
        ax1.set_xlabel('时段(小时)')
        ax1.set_ylabel('曝光/点击量', color='#34495e')
        ax2.set_ylabel('转化量', color='#e74c3c')
        ax1.set_title('24小时投放效果分布', fontsize=14, fontweight='bold')
        ax1.set_xticks(x)
        ax1.set_xticklabels([f'{h:02d}' for h in hours])
        
        lines1, labels1 = ax1.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        ax1.legend(lines1 + lines2, labels1 + labels2, loc='upper left')
        
        ax1.grid(axis='y', alpha=0.3)
        
        plt.tight_layout()
        plt.savefig(output_path, dpi=150, bbox_inches='tight')
        plt.close()
        
        logger.info(f"时段分布图表已生成: {output_path}")
        return output_path

import os
import sys
import unittest
from datetime import date, datetime, timedelta
import tempfile
import shutil

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.settings import settings
from models.schemas import AttributionModelType
from data_collector import SampleDataGenerator
from data_processor import DataProcessor
from attribution import (
    AttributionEngine, FirstClickAttribution, LastClickAttribution,
    LinearAttribution, TimeDecayAttribution, PositionBasedAttribution
)
from roi_analysis import ROICalculator, ChannelRanker
from budget_optimizer import BudgetOptimizer
from report_engine import ReportGenerator, ChartGenerator, ExportEngine
from simulator import BudgetSimulator
from logging_system import OperationLogger


class TestSampleDataGenerator(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.generator = SampleDataGenerator()
    
    def test_generate_daily_data(self):
        data = self.generator.generate_daily_data(date.today())
        self.assertIsInstance(data, list)
        self.assertGreater(len(data), 0)
        
        record = data[0]
        self.assertIsNotNone(record.platform)
        self.assertIsNotNone(record.channel)
        self.assertGreaterEqual(record.impressions, 0)
        self.assertGreaterEqual(record.clicks, 0)
        self.assertGreaterEqual(record.conversions, 0)
        self.assertGreaterEqual(record.cost, 0)
        self.assertGreaterEqual(record.revenue, 0)
    
    def test_generate_massive_data(self):
        data = self.generator.generate_massive_data(num_days=3, records_per_day=100)
        self.assertEqual(len(data), 300)


class TestDataProcessor(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.processor = DataProcessor()
        cls.generator = SampleDataGenerator()
        cls.test_data = cls.generator.generate_massive_data(num_days=3, records_per_day=100)
    
    def test_process_data(self):
        df = self.processor.process_data(self.test_data)
        self.assertFalse(df.empty)
        self.assertIn('platform', df.columns)
        self.assertIn('channel', df.columns)
        self.assertIn('date', df.columns)
        self.assertIn('impressions', df.columns)
    
    def test_clean_and_validate(self):
        df = self.processor.process_data(self.test_data)
        clean_df = self.processor.clean_and_validate(df)
        self.assertFalse(clean_df.empty)
        
        self.assertTrue((clean_df['impressions'] >= 0).all())
        self.assertTrue((clean_df['clicks'] >= 0).all())
        self.assertTrue((clean_df['cost'] >= 0).all())


class TestAttributionModels(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.generator = SampleDataGenerator()
        cls.processor = DataProcessor()
        cls.engine = AttributionEngine()
        
        data = cls.generator.generate_massive_data(num_days=7, records_per_day=50)
        df = cls.processor.process_data(data)
        cls.touchpoints = cls.processor.extract_touchpoints(df)
        cls.conversion_paths = cls.engine.build_conversion_paths(cls.touchpoints)
    
    def test_first_click_attribution(self):
        model = FirstClickAttribution()
        for path in self.conversion_paths[:5]:
            result = model.attribute(path['touchpoints'], path['conversion_value'])
            self.assertIsNotNone(result)
            self.assertIn('contributions', result.model_dump())
            total = sum(result.contributions.values())
            self.assertAlmostEqual(total, path['conversion_value'], places=5)
    
    def test_last_click_attribution(self):
        model = LastClickAttribution()
        for path in self.conversion_paths[:5]:
            result = model.attribute(path['touchpoints'], path['conversion_value'])
            self.assertIsNotNone(result)
            total = sum(result.contributions.values())
            self.assertAlmostEqual(total, path['conversion_value'], places=5)
    
    def test_linear_attribution(self):
        model = LinearAttribution()
        for path in self.conversion_paths[:5]:
            result = model.attribute(path['touchpoints'], path['conversion_value'])
            self.assertIsNotNone(result)
            total = sum(result.contributions.values())
            self.assertAlmostEqual(total, path['conversion_value'], places=5)
    
    def test_time_decay_attribution(self):
        model = TimeDecayAttribution()
        for path in self.conversion_paths[:5]:
            result = model.attribute(path['touchpoints'], path['conversion_value'])
            self.assertIsNotNone(result)
            total = sum(result.contributions.values())
            self.assertAlmostEqual(total, path['conversion_value'], places=5)
    
    def test_position_based_attribution(self):
        model = PositionBasedAttribution()
        for path in self.conversion_paths[:5]:
            result = model.attribute(path['touchpoints'], path['conversion_value'])
            self.assertIsNotNone(result)
            total = sum(result.contributions.values())
            self.assertAlmostEqual(total, path['conversion_value'], places=5)


class TestROIAnalysis(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.generator = SampleDataGenerator()
        cls.processor = DataProcessor()
        cls.roi_calculator = ROICalculator()
        cls.channel_ranker = ChannelRanker()
        
        data = cls.generator.generate_massive_data(num_days=7, records_per_day=100)
        cls.df = cls.processor.process_data(data)
        
        model = LastClickAttribution()
        touchpoints = cls.processor.extract_touchpoints(cls.df)
        conversion_paths = cls.engine = AttributionEngine()
        paths = cls.engine.build_conversion_paths(touchpoints)
        
        cls.attribution_results = []
        for path in paths:
            result = model.attribute(path['touchpoints'], path['conversion_value'])
            cls.attribution_results.append(result)
    
    def test_calculate_daily_roi(self):
        roi_data = self.roi_calculator.calculate_daily_roi(
            self.df, self.attribution_results, AttributionModelType.LAST_CLICK
        )
        self.assertIsInstance(roi_data, list)
        self.assertGreater(len(roi_data), 0)
    
    def test_calculate_weighted_roi(self):
        daily_roi = self.roi_calculator.calculate_daily_roi(
            self.df, self.attribution_results, AttributionModelType.LAST_CLICK
        )
        weighted_roi = self.roi_calculator.calculate_weighted_roi(daily_roi)
        self.assertIsInstance(weighted_roi, list)
        
        for roi in weighted_roi:
            self.assertIsNotNone(roi.weighted_roi)
            self.assertGreaterEqual(roi.weighted_roi, 0)
    
    def test_rank_channels(self):
        daily_roi = self.roi_calculator.calculate_daily_roi(
            self.df, self.attribution_results, AttributionModelType.LAST_CLICK
        )
        weighted_roi = self.roi_calculator.calculate_weighted_roi(daily_roi)
        ranked = self.channel_ranker.rank_channels(weighted_roi)
        
        ranks = [roi.rank for roi in ranked]
        self.assertEqual(sorted(ranks), list(range(1, len(ranks) + 1)))


class TestBudgetOptimizer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.generator = SampleDataGenerator()
        cls.processor = DataProcessor()
        cls.roi_calculator = ROICalculator()
        cls.channel_ranker = ChannelRanker()
        cls.budget_optimizer = BudgetOptimizer()
        
        data = cls.generator.generate_massive_data(num_days=7, records_per_day=100)
        cls.df = cls.processor.process_data(data)
        
        model = LastClickAttribution()
        engine = AttributionEngine()
        touchpoints = cls.processor.extract_touchpoints(cls.df)
        paths = engine.build_conversion_paths(touchpoints)
        
        attribution_results = []
        for path in paths:
            result = model.attribute(path['touchpoints'], path['conversion_value'])
            attribution_results.append(result)
        
        daily_roi = cls.roi_calculator.calculate_daily_roi(
            cls.df, attribution_results, AttributionModelType.LAST_CLICK
        )
        cls.roi_data = cls.roi_calculator.calculate_weighted_roi(daily_roi)
        cls.roi_data = cls.channel_ranker.rank_channels(cls.roi_data)
    
    def test_generate_adjustment_suggestions(self):
        current_budgets = {roi.channel: roi.total_cost for roi in self.roi_data}
        channel_grades = {roi.channel: 'A' for roi in self.roi_data}
        
        suggestions = self.budget_optimizer.generate_adjustment_suggestions(
            roi_data=self.roi_data,
            current_budgets=current_budgets,
            total_budget=settings.TOTAL_DAILY_BUDGET
        )
        
        self.assertIsInstance(suggestions, list)


class TestReportEngine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.mkdtemp()
        cls.chart_generator = ChartGenerator()
        cls.export_engine = ExportEngine()
        cls.report_generator = ReportGenerator()
        
        cls.generator = SampleDataGenerator()
        cls.processor = DataProcessor()
        cls.roi_calculator = ROICalculator()
        cls.channel_ranker = ChannelRanker()
        
        data = cls.generator.generate_massive_data(num_days=7, records_per_day=50)
        cls.df = cls.processor.process_data(data)
        
        model = LastClickAttribution()
        engine = AttributionEngine()
        touchpoints = cls.processor.extract_touchpoints(cls.df)
        paths = engine.build_conversion_paths(touchpoints)
        
        attribution_results = []
        for path in paths:
            result = model.attribute(path['touchpoints'], path['conversion_value'])
            attribution_results.append(result)
        
        daily_roi = cls.roi_calculator.calculate_daily_roi(
            cls.df, attribution_results, AttributionModelType.LAST_CLICK
        )
        cls.roi_data = cls.roi_calculator.calculate_weighted_roi(daily_roi)
        cls.roi_data = cls.channel_ranker.rank_channels(cls.roi_data)
    
    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.temp_dir)
    
    def test_chart_generator(self):
        roi_dicts = [roi.model_dump() for roi in self.roi_data]
        chart_path = os.path.join(self.temp_dir, 'test_chart.png')
        result = self.chart_generator.generate_channel_performance_chart(roi_dicts, chart_path)
        self.assertTrue(os.path.exists(result))
    
    def test_export_to_excel(self):
        report_data = {
            'title': '测试报告',
            'report_date': date.today().isoformat(),
            'summary': {
                '总花费': {'label': '总花费', 'value': '10000'},
                '总收入': {'label': '总收入', 'value': '25000'}
            },
            'data_tables': [{
                'title': '测试数据',
                'sheet_name': '数据',
                'data': [
                    ['渠道', 'ROI', '花费'],
                    ['渠道1', 2.5, 1000]
                ]
            }]
        }
        
        output_path = self.export_engine.export_to_excel(report_data, 'test_report.xlsx')
        self.assertTrue(os.path.exists(output_path))
    
    def test_generate_daily_report(self):
        report = self.report_generator.generate_daily_report(
            roi_data=self.roi_data,
            daily_trends={},
            dates=[]
        )
        self.assertIn('report_id', report)
        self.assertIn('exported_files', report)


class TestBudgetSimulator(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.simulator = BudgetSimulator()
        
        cls.generator = SampleDataGenerator()
        cls.processor = DataProcessor()
        cls.roi_calculator = ROICalculator()
        cls.channel_ranker = ChannelRanker()
        
        data = cls.generator.generate_massive_data(num_days=7, records_per_day=50)
        cls.df = cls.processor.process_data(data)
        
        model = LastClickAttribution()
        engine = AttributionEngine()
        touchpoints = cls.processor.extract_touchpoints(cls.df)
        paths = engine.build_conversion_paths(touchpoints)
        
        attribution_results = []
        for path in paths:
            result = model.attribute(path['touchpoints'], path['conversion_value'])
            attribution_results.append(result)
        
        daily_roi = cls.roi_calculator.calculate_daily_roi(
            cls.df, attribution_results, AttributionModelType.LAST_CLICK
        )
        cls.roi_data = cls.roi_calculator.calculate_weighted_roi(daily_roi)
        cls.roi_data = cls.channel_ranker.rank_channels(cls.roi_data)
        
        cls.simulator.load_historical_data(cls.roi_data)
    
    def test_create_simulation(self):
        config = self.simulator.create_simulation(
            name='测试模拟',
            budget_adjustments={'bytedance_douyin': 0.1}
        )
        self.assertIsNotNone(config)
        self.assertEqual(config.name, '测试模拟')
    
    def test_run_simulation(self):
        config = self.simulator.create_simulation(
            name='测试模拟',
            budget_adjustments={'bytedance_douyin': 0.1},
            simulation_runs=100
        )
        result = self.simulator.run_simulation(config)
        
        self.assertIsNotNone(result)
        self.assertIsNotNone(result.simulated_total_revenue)
        self.assertIsNotNone(result.simulated_total_roi)


class TestOperationLogger(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.test_db = tempfile.mktemp(suffix='.db')
        cls.logger = OperationLogger(db_path=cls.test_db)
    
    @classmethod
    def tearDownClass(cls):
        if os.path.exists(cls.test_db):
            os.remove(cls.test_db)
    
    def test_log_operation(self):
        log_id = self.logger.log_operation(
            operation_type='test',
            module='test_module',
            status='success',
            details={'test_key': 'test_value'}
        )
        self.assertIsNotNone(log_id)
    
    def test_query_logs(self):
        self.logger.log_operation(
            operation_type='test_query',
            module='test_module',
            status='success'
        )
        
        logs, total = self.logger.query_logs(
            operation_types=['test_query'],
            modules=['test_module']
        )
        self.assertGreater(total, 0)
        self.assertGreater(len(logs), 0)
    
    def test_export_logs(self):
        self.logger.log_operation(
            operation_type='test_export',
            module='test_module',
            status='success'
        )
        
        export_path = self.logger.export_logs(
            output_format='xlsx',
            operation_types=['test_export']
        )
        self.assertTrue(os.path.exists(export_path))


if __name__ == '__main__':
    unittest.main(verbosity=2)

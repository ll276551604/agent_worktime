# -*- coding: utf-8 -*-
"""
评估模型模块
支持多种业内标准评估模型：
1. 功能点分析法 (Function Point Analysis)
2. COCOMO II 模型
3. 敏捷故事点估算
4. 自定义规则引擎
"""
import logging
from typing import Dict, List, Any

logger = logging.getLogger(__name__)

class EvaluationModel:
    """评估模型基类"""
    
    def evaluate(self, requirement: Dict, decomposition: List[Dict]) -> Dict:
        """评估需求，返回工时估算"""
        raise NotImplementedError
    
    def get_name(self) -> str:
        """返回模型名称"""
        raise NotImplementedError

class FunctionPointModel(EvaluationModel):
    """
    功能点分析法 (Function Point Analysis)
    基于Albrecht方法，通过计算功能点来估算工作量
    
    功能点类型：
    - EI (External Input): 外部输入
    - EO (External Output): 外部输出
    - EQ (External Inquiry): 外部查询
    - ILF (Internal Logical File): 内部逻辑文件
    - EIF (External Interface File): 外部接口文件
    """
    
    COMPLEXITY_WEIGHTS = {
        "EI": {"low": 3, "medium": 4, "high": 6},
        "EO": {"low": 4, "medium": 5, "high": 7},
        "EQ": {"low": 3, "medium": 4, "high": 6},
        "ILF": {"low": 7, "medium": 10, "high": 15},
        "EIF": {"low": 5, "medium": 7, "high": 10},
    }
    
    # 复杂度判断阈值
    LOW_THRESHOLD = 10  # 字段数/功能点
    HIGH_THRESHOLD = 20
    
    def __init__(self):
        self.conversion_factor = 0.3  # 功能点转人天系数（可根据团队调整）
    
    def get_name(self) -> str:
        return "功能点分析法 (FPA)"
    
    def evaluate(self, requirement: Dict, decomposition: List[Dict]) -> Dict:
        feature = requirement.get("feature", "")
        detail = requirement.get("detail", "")
        
        # 识别功能点类型
        function_points = self._count_function_points(feature, detail, decomposition)
        
        # 计算未调整功能点 (UFP)
        ufp = sum(
            self.COMPLEXITY_WEIGHTS[fp_type][complexity]
            for fp_type, complexity, _ in function_points
        )
        
        # 计算调整因子（基于复杂度加成）
        adjustment_factor = self._calculate_adjustment_factor(requirement)
        
        # 计算调整后功能点 (AFP)
        afp = ufp * adjustment_factor
        
        # 转换为工时（人天）
        effort_days = afp * self.conversion_factor
        
        return {
            "model": self.get_name(),
            "function_points": function_points,
            "ufp": ufp,
            "adjustment_factor": round(adjustment_factor, 2),
            "afp": round(afp, 2),
            "effort_days": round(max(effort_days, 0.5), 2),
            "breakdown": self._generate_breakdown(decomposition),
        }
    
    def _count_function_points(self, feature: str, detail: str, decomposition: List[Dict]) -> List:
        """统计功能点"""
        points = []
        
        # 根据拆解结果识别功能点
        for part in decomposition:
            part_type = part.get("type", "")
            part_name = part.get("name", "")
            features = part.get("features", [])
            
            # 估算字段数（基于功能点数量）
            field_count = len(features) * 2
            
            # 判断复杂度
            if field_count <= self.LOW_THRESHOLD:
                complexity = "low"
            elif field_count >= self.HIGH_THRESHOLD:
                complexity = "high"
            else:
                complexity = "medium"
            
            # 根据类型分配功能点
            if part_type == "页面":
                if "列表" in part_name:
                    points.append(("EI", complexity, f"{part_name}-查询输入"))
                    points.append(("EO", complexity, f"{part_name}-结果输出"))
                    points.append(("ILF", complexity, f"{part_name}-数据存储"))
                elif "表单" in part_name or "新增" in part_name or "编辑" in part_name:
                    points.append(("EI", complexity, f"{part_name}-表单输入"))
                    points.append(("ILF", complexity, f"{part_name}-数据存储"))
                elif "详情" in part_name:
                    points.append(("EQ", complexity, f"{part_name}-查询"))
                    points.append(("EO", complexity, f"{part_name}-详情输出"))
            
            elif part_type == "功能":
                if "导入" in part_name:
                    points.append(("EI", complexity, f"{part_name}-文件导入"))
                    points.append(("ILF", complexity, f"{part_name}-数据存储"))
                elif "导出" in part_name:
                    points.append(("EQ", complexity, f"{part_name}-数据查询"))
                    points.append(("EO", complexity, f"{part_name}-文件输出"))
                else:
                    points.append(("EI", complexity, f"{part_name}-输入"))
                    points.append(("EO", complexity, f"{part_name}-输出"))
        
        return points
    
    def _calculate_adjustment_factor(self, requirement: Dict) -> float:
        """计算调整因子"""
        factor = 1.0
        detail = requirement.get("detail", "")
        
        # 复杂度加成
        complexity_factors = [
            ("审批流", 0.15),
            ("多角色", 0.1),
            ("批量操作", 0.1),
            ("外部接口", 0.15),
            ("复杂计算", 0.15),
            ("实时数据", 0.1),
            ("多语言", 0.1),
            ("移动端", 0.1),
        ]
        
        for keyword, add_factor in complexity_factors:
            if keyword in detail:
                factor += add_factor
        
        return factor
    
    def _generate_breakdown(self, decomposition: List[Dict]) -> List[Dict]:
        """生成拆解详情"""
        breakdown = []
        for part in decomposition:
            effort = len(part.get("features", [])) * 0.3  # 每个功能点约0.3天
            breakdown.append({
                "item": part.get("name", ""),
                "type": part.get("type", ""),
                "features": part.get("features", []),
                "estimated_days": round(effort, 2),
            })
        return breakdown

class COCOMOModel(EvaluationModel):
    """
    COCOMO II 模型 (Constructive Cost Model)
    面向对象和组件化开发的成本估算模型
    
    基本公式：
    Effort = A * Size^B * EAF
    
    其中：
    - A: 系数（默认2.94）
    - B: 指数（默认1.10）
    - Size: 规模（千行代码/KLOC）
    - EAF: 成本驱动因子
    """
    
    def __init__(self):
        self.A = 2.94  # 基本系数
        self.B = 1.10  # 规模指数
    
    def get_name(self) -> str:
        return "COCOMO II 模型"
    
    def evaluate(self, requirement: Dict, decomposition: List[Dict]) -> Dict:
        # 估算代码规模（基于功能点）
        total_features = sum(len(part.get("features", [])) for part in decomposition)
        kloc = self._estimate_kloc(total_features)
        
        # 计算成本驱动因子
        eaf = self._calculate_eaf(requirement)
        
        # 计算工作量（人月）
        effort_person_months = self.A * (kloc ** self.B) * eaf
        
        # 转换为人天（按月22天计算）
        effort_days = effort_person_months * 22
        
        return {
            "model": self.get_name(),
            "kloc": round(kloc, 2),
            "eaf": round(eaf, 2),
            "effort_person_months": round(effort_person_months, 2),
            "effort_days": round(max(effort_days, 0.5), 2),
            "breakdown": self._generate_breakdown(decomposition),
        }
    
    def _estimate_kloc(self, feature_count: int) -> float:
        """估算代码规模（千行）"""
        # 每个功能点平均约50-100行代码
        lines_per_feature = 75
        return (feature_count * lines_per_feature) / 1000
    
    def _calculate_eaf(self, requirement: Dict) -> float:
        """计算成本驱动因子"""
        eaf = 1.0
        detail = requirement.get("detail", "")
        
        # 产品复杂度因子
        product_factors = [
            ("复杂业务", 1.15),
            ("大数据量", 1.1),
            ("高并发", 1.15),
            ("安全性要求", 1.1),
        ]
        
        # 开发环境因子
        env_factors = [
            ("新技术", 1.1),
            ("跨平台", 1.05),
            ("遗留系统", 1.1),
        ]
        
        for keyword, multiplier in product_factors + env_factors:
            if keyword in detail:
                eaf *= multiplier
        
        return eaf
    
    def _generate_breakdown(self, decomposition: List[Dict]) -> List[Dict]:
        """生成拆解详情"""
        breakdown = []
        for part in decomposition:
            features = part.get("features", [])
            kloc = len(features) * 0.075  # 每个功能点约75行代码
            effort = self.A * (kloc ** self.B) * 22  # 转人天
            breakdown.append({
                "item": part.get("name", ""),
                "type": part.get("type", ""),
                "features": features,
                "estimated_days": round(max(effort, 0.2), 2),
            })
        return breakdown

class StoryPointModel(EvaluationModel):
    """
    敏捷故事点估算模型
    使用斐波那契数列（1, 2, 3, 5, 8, 13）估算故事点
    
    故事点与工时转换：
    - 1点 ≈ 0.5-1天
    - 2点 ≈ 1-2天
    - 3点 ≈ 2-3天
    - 5点 ≈ 3-5天
    - 8点 ≈ 5-8天
    """
    
    STORY_POINTS = [1, 2, 3, 5, 8, 13]
    
    def get_name(self) -> str:
        return "敏捷故事点估算"
    
    def evaluate(self, requirement: Dict, decomposition: List[Dict]) -> Dict:
        total_features = sum(len(part.get("features", [])) for part in decomposition)
        
        # 根据功能点数量确定故事点
        story_points = self._calculate_story_points(total_features)
        
        # 转换为人天（1点≈0.8天）
        effort_days = story_points * 0.8
        
        return {
            "model": self.get_name(),
            "story_points": story_points,
            "effort_days": round(max(effort_days, 0.5), 2),
            "breakdown": self._generate_breakdown(decomposition),
        }
    
    def _calculate_story_points(self, feature_count: int) -> int:
        """计算故事点"""
        if feature_count <= 2:
            return 1
        elif feature_count <= 4:
            return 2
        elif feature_count <= 6:
            return 3
        elif feature_count <= 10:
            return 5
        elif feature_count <= 15:
            return 8
        else:
            return 13
    
    def _generate_breakdown(self, decomposition: List[Dict]) -> List[Dict]:
        """生成拆解详情"""
        breakdown = []
        for part in decomposition:
            features = part.get("features", [])
            points = self._calculate_story_points(len(features))
            effort = points * 0.8
            breakdown.append({
                "item": part.get("name", ""),
                "type": part.get("type", ""),
                "features": features,
                "story_points": points,
                "estimated_days": round(max(effort, 0.2), 2),
            })
        return breakdown

class RuleBasedModel(EvaluationModel):
    """
    规则引擎模型
    基于预定义的工时规则进行评估
    """
    
    def __init__(self):
        from agent.knowledge_manager import get_knowledge_manager
        self.kb_manager = get_knowledge_manager()
    
    def get_name(self) -> str:
        return "规则引擎模型"
    
    def evaluate(self, requirement: Dict, decomposition: List[Dict]) -> Dict:
        worktime_rules = self.kb_manager._load_worktime_rules()
        base_rules = worktime_rules.get("基础工时", {})
        complexity_rules = worktime_rules.get("复杂度加成", {})
        
        total_days = 0.0
        breakdown = []
        
        # 基于拆解结果计算工时
        for part in decomposition:
            part_type = part.get("type", "")
            part_name = part.get("name", "")
            features = part.get("features", [])
            
            # 根据类型获取基础工时
            base_hours = 0.0
            if "页面" in part_type:
                if "调整" in requirement.get("feature", ""):
                    base_hours = (base_rules.get("调整页面", {}).get("min", 0.2) + 
                                 base_rules.get("调整页面", {}).get("max", 0.5)) / 2
                else:
                    base_hours = (base_rules.get("新增页面", {}).get("min", 0.5) + 
                                 base_rules.get("新增页面", {}).get("max", 1.0)) / 2
            elif "功能" in part_type:
                if len(features) <= 3:
                    base_hours = (base_rules.get("简单功能", {}).get("min", 0.1) + 
                                 base_rules.get("简单功能", {}).get("max", 0.3)) / 2
                else:
                    base_hours = (base_rules.get("复杂功能", {}).get("min", 0.5) + 
                                 base_rules.get("复杂功能", {}).get("max", 1.0)) / 2
            
            # 每个子功能额外加成
            base_hours += len(features) * 0.1
            
            # 复杂度加成
            detail = requirement.get("detail", "")
            for keyword, rule in complexity_rules.items():
                if keyword in detail or keyword in part_name:
                    base_hours *= (1 + rule.get("加成", 0))
            
            breakdown.append({
                "item": part_name,
                "type": part_type,
                "features": features,
                "estimated_days": round(max(base_hours, 0.1), 2),
            })
            
            total_days += base_hours
        
        return {
            "model": self.get_name(),
            "effort_days": round(max(total_days, 0.5), 2),
            "breakdown": breakdown,
        }

class CompositeModel(EvaluationModel):
    """
    组合评估模型
    综合多个模型的结果，取加权平均值
    """
    
    def __init__(self):
        self.models = [
            (FunctionPointModel(), 0.35),
            (COCOMOModel(), 0.25),
            (StoryPointModel(), 0.2),
            (RuleBasedModel(), 0.2),
        ]
    
    def get_name(self) -> str:
        return "综合评估模型"
    
    def evaluate(self, requirement: Dict, decomposition: List[Dict]) -> Dict:
        results = []
        total_weight = 0.0
        weighted_sum = 0.0
        
        for model, weight in self.models:
            try:
                result = model.evaluate(requirement, decomposition)
                result["weight"] = weight
                results.append(result)
                weighted_sum += result["effort_days"] * weight
                total_weight += weight
            except Exception as e:
                logger.error(f"模型 {model.get_name()} 评估失败: {e}")
        
        # 归一化权重
        if total_weight > 0:
            weighted_sum /= total_weight
        
        return {
            "model": self.get_name(),
            "effort_days": round(max(weighted_sum, 0.5), 2),
            "sub_models": results,
            "breakdown": results[-1].get("breakdown", []),  # 使用规则引擎的拆解
        }


def get_model(model_name: str = None) -> EvaluationModel:
    """获取评估模型"""
    models = {
        "fpa": FunctionPointModel(),
        "cocomo": COCOMOModel(),
        "storypoint": StoryPointModel(),
        "rule": RuleBasedModel(),
        "composite": CompositeModel(),
    }
    
    return models.get(model_name.lower(), CompositeModel())


def evaluate_requirement(requirement: Dict, model_name: str = "composite") -> Dict:
    """评估单个需求"""
    from agent.knowledge_manager import get_knowledge_manager
    
    kb_manager = get_knowledge_manager()
    
    # 分析需求（新增vs调整）
    analysis = kb_manager.analyze_requirement(requirement)
    
    # 初步拆解
    decomposition = kb_manager.suggest_decomposition(requirement)
    
    # 使用评估模型
    model = get_model(model_name)
    evaluation = model.evaluate(requirement, decomposition)
    
    return {
        "original_requirement": requirement,
        "analysis": analysis,
        "decomposition": decomposition,
        "evaluation": evaluation,
    }

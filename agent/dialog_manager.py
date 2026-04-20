"""引导对话管理器 - 负责意图识别、需求收集和追问逻辑"""
import json
import os
import re
from typing import Dict, List, Optional, Any

class DialogManager:
    """智能引导对话管理器"""
    
    def __init__(self):
        self.prompt_path = os.path.join(os.path.dirname(__file__), '..', 'prompts', 'guiding_prompt.txt')
        self.system_prompt = self._load_prompt()
        # 延迟导入知识库管理器，避免循环依赖
        self.knowledge_manager = None
        
        # 业务模块关键词库（增强版）
        self.module_keywords = {
            '用户管理': ['用户', '登录', '注册', '账号', '个人中心', '权限', '角色', '会员', '账户', '登录页', '注册页', '个人资料'],
            '订单管理': ['订单', '下单', '购物车', '支付', '退款', '发货', '物流', '订单列表', '订单详情', '结算'],
            '报表系统': ['报表', '统计', '数据', '图表', '分析', 'dashboard', '仪表盘', '看板', '数据可视化'],
            '商品管理': ['商品', '产品', '库存', 'SKU', '价格', '上架', '下架', '商品列表', '商品详情', '商品分类'],
            '配置管理': ['配置', '设置', '参数', '选项', '偏好', '系统配置', '参数配置'],
            '系统设置': ['系统', '全局', '基础', '后台', '管理', '系统管理', '后台管理'],
            '数据管理': ['数据', '导入', '导出', '同步', '备份', '数据迁移', '数据清洗'],
            '消息通知': ['消息', '通知', '推送', '邮件', '短信', '提醒', '站内信', '消息中心'],
            '审批流程': ['审批', '流程', '审核', '工单', '审批流程', '工作流'],
            '营销活动': ['活动', '营销', '促销', '优惠券', '红包', '满减', '团购', '秒杀'],
            '内容管理': ['内容', '文章', '新闻', '资讯', '发布', '编辑', '栏目'],
            '搜索功能': ['搜索', '查询', '筛选', '过滤', '关键词'],
            '移动端': ['手机', '移动端', 'APP', '小程序', 'H5'],
            '接口开发': ['接口', 'API', '接口开发', 'API对接', '第三方接口'],
        }
        
        # 需求类型关键词（增强版）
        self.type_keywords = {
            '新增功能': ['新增', '添加', '创建', '开发', '实现', '构建', '新建', '开发新功能', '新增需求'],
            '调整优化': ['调整', '优化', '改进', '修改', '更新', '升级', '增强', '改善', '提升', '改造'],
            'Bug修复': ['bug', '问题', '错误', '修复', '解决', '异常', '缺陷', 'bug修复', '修复bug'],
            '重构': ['重构', '重构代码', '代码优化', '架构优化'],
            '技术债务': ['技术债务', '技术债', '代码清理'],
        }
    
    def _load_prompt(self) -> str:
        """加载系统提示词"""
        if os.path.exists(self.prompt_path):
            with open(self.prompt_path, 'r', encoding='utf-8') as f:
                return f.read()
        return self._get_default_prompt()
    
    def _get_default_prompt(self) -> str:
        """默认提示词"""
        return """你是一位专业的产品工时评估顾问，擅长与用户沟通需求并进行准确评估。

## 核心任务
引导用户提供完整的需求信息，然后进行专业的工时评估。

## 对话流程
1. **意图识别**：首先判断用户意图（评估需求、询问问题、闲聊）
2. **需求收集**：如果是评估需求，引导用户提供完整信息
3. **信息确认**：检查信息完整性，必要时追问
4. **专业评估**：信息完整后进行需求分析和工时估算

## 需要收集的信息
- ✅ 需求描述（必须）
- ✅ 所属模块（必须）：如用户管理、订单管理、报表系统等
- ✅ 需求类型（必须）：新增功能 / 调整优化 / Bug修复

## 追问策略
- 每次只问一个问题
- 使用自然友好的口语化表达

## 回答格式
### 需要追问
直接输出追问内容

### 信息完整
<ASSESSMENT_READY>
{
  "requirement": "完整需求描述",
  "module": "所属模块",
  "type": "需求类型"
}
</ASSESSMENT_READY>
"""
    
    def analyze_intent(self, user_input: str) -> str:
        """分析用户意图"""
        user_input = user_input.lower().strip()
        
        # 识别评估需求意图
        eval_keywords = ['评估', '工时', '估算', '需求', '功能', '开发', '工作量', '拆解']
        if any(keyword in user_input for keyword in eval_keywords):
            return 'evaluation'
        
        # 识别问题意图
        question_keywords = ['什么', '怎么', '如何', '为什么', '哪个', '吗', '?', '？']
        if any(keyword in user_input for keyword in question_keywords):
            return 'question'
        
        # 默认视为评估需求
        return 'evaluation'
    
    def _init_knowledge_manager(self):
        """延迟初始化知识库管理器"""
        if self.knowledge_manager is None:
            from agent.knowledge_manager import KnowledgeManager
            self.knowledge_manager = KnowledgeManager()
    
    def _analyze_from_knowledge_base(self, requirement_text: str) -> Dict:
        """通过知识库智能分析需求，识别模块和需求类型"""
        self._init_knowledge_manager()
        
        result = {
            'module': '',
            'type': '',
            'confidence': 0.0
        }
        
        try:
            # 调用知识库进行分析
            requirement = {
                "feature": requirement_text,
                "detail": requirement_text,
                "module": ""
            }
            analysis = self.knowledge_manager.analyze_requirement(requirement)
            
            # 从分析结果中提取模块信息
            if analysis.get('related_modules'):
                result['module'] = analysis['related_modules'][0]
            
            # 根据知识库判断需求类型（新增/调整）
            if analysis.get('judgment'):
                if analysis['judgment'] == '新增':
                    result['type'] = '新增功能'
                else:
                    result['type'] = '调整优化'
            
            result['confidence'] = analysis.get('confidence', 0.0)
            
        except Exception as e:
            # 如果知识库分析失败，使用默认规则
            pass
        
        return result
    
    def _extract_module_by_keyword(self, text: str) -> str:
        """通过关键词匹配识别业务模块"""
        text_lower = text.lower()
        
        for module, keywords in self.module_keywords.items():
            for keyword in keywords:
                if keyword in text or keyword.lower() in text_lower:
                    return module
        
        return ''
    
    def _extract_type_by_keyword(self, text: str) -> str:
        """通过关键词匹配识别需求类型"""
        text_lower = text.lower()
        
        # Bug修复优先级最高（因为可能同时包含"修复"和"新增"等词）
        for keyword in self.type_keywords['Bug修复']:
            if keyword in text or keyword.lower() in text_lower:
                return 'Bug修复'
        
        # 然后检查新增功能
        for keyword in self.type_keywords['新增功能']:
            if keyword in text or keyword.lower() in text_lower:
                return '新增功能'
        
        # 最后检查调整优化
        for keyword in self.type_keywords['调整优化']:
            if keyword in text or keyword.lower() in text_lower:
                return '调整优化'
        
        return ''
    
    def _is_requirement_description(self, text: str) -> bool:
        """检查输入文本是否是需求描述"""
        if not text or len(text.strip()) < 5:
            return False
        
        text_lower = text.lower()
        
        # 检查是否包含需求相关的关键词
        requirement_indicators = [
            '需求', '功能', '开发', '实现', '添加', '新增', '修改', '调整', '优化', '修复', 'bug', '问题',
            '页面', '接口', '按钮', '表单', '列表', '详情', '登录', '注册', '用户', '订单', '商品',
            '系统', '后台', '前端', '后端', '数据库', 'API', '模块', '菜单', '权限', '角色',
            '报表', '统计', '数据', '导入', '导出', '查询', '搜索', '筛选', '排序', '分页'
        ]
        
        # 如果包含多个需求关键词，认为是需求
        keyword_count = sum(1 for keyword in requirement_indicators if keyword in text_lower)
        if keyword_count >= 2:
            return True
        
        # 检查是否包含模块关键词
        module_keyword_count = 0
        for module, keywords in self.module_keywords.items():
            for keyword in keywords:
                if keyword in text_lower:
                    module_keyword_count += 1
                    break
        if module_keyword_count >= 1:
            return True
        
        # 检查是否包含需求类型关键词
        type_keyword_count = 0
        for type_name, keywords in self.type_keywords.items():
            for keyword in keywords:
                if keyword in text_lower:
                    type_keyword_count += 1
                    break
        if type_keyword_count >= 1:
            return True
        
        # 如果是简单的问候或闲聊，返回False
        casual_phrases = ['你好', 'hello', 'hi', '您好', '早上好', '晚上好', '谢谢', '请问', '什么', '怎么', '为什么']
        if any(phrase in text_lower for phrase in casual_phrases):
            return False
        
        # 默认情况下，如果文本较长且不像是闲聊，认为是需求
        if len(text.strip()) > 20:
            return True
        
        return False
    
    def extract_requirement_info(self, conversation_history: List[Dict]) -> Dict[str, str]:
        """从对话历史中提取需求信息（结合知识库智能分析）"""
        info = {
            'requirement': '',
            'module': '',
            'type': '',
            'auto_detected': {
                'module': False,
                'type': False
            }
        }
        
        # 收集所有用户消息
        user_messages = []
        for msg in conversation_history:
            if msg['role'] == 'user':
                user_messages.append(msg['content'])
        
        # 合并所有用户消息作为需求描述
        requirement_text = ' '.join(user_messages).strip()
        
        # 检查是否是需求描述
        if not self._is_requirement_description(requirement_text):
            return info  # 返回空info，表示不是需求
        
        info['requirement'] = requirement_text
        
        if not requirement_text:
            return info
        
        # ============== 第一步：规则匹配识别（优先级最高）==============
        
        # 尝试提取模块信息
        module_from_rule = self._extract_module_by_keyword(requirement_text)
        if module_from_rule:
            info['module'] = module_from_rule
            info['auto_detected']['module'] = True
        
        # 尝试提取需求类型
        type_from_rule = self._extract_type_by_keyword(requirement_text)
        if type_from_rule:
            info['type'] = type_from_rule
            info['auto_detected']['type'] = True
        
        # ============== 第二步：如果规则匹配未能识别，使用知识库分析 ==============
        
        if (not info['module'] or not info['type']):
            kb_result = self._analyze_from_knowledge_base(requirement_text)
            
            # 如果知识库分析有较高置信度（>=0.6），使用分析结果
            if kb_result['confidence'] >= 0.6:
                if kb_result['module'] and not info['module']:
                    info['module'] = kb_result['module']
                    info['auto_detected']['module'] = True
                if kb_result['type'] and not info['type']:
                    info['type'] = kb_result['type']
                    info['auto_detected']['type'] = True
        
        return info
    
    def check_info_complete(self, info: Dict) -> bool:
        """检查信息是否完整（需求描述是必须的，模块和类型可以使用默认值）"""
        requirement = info.get('requirement', '').strip()
        
        # 只要有需求描述就认为可以进行评估
        if not requirement:
            return False
        
        # 如果模块或类型未识别，使用默认值
        if not info.get('module', '').strip():
            info['module'] = '未指定模块'
            info['auto_detected']['module'] = False
        
        if not info.get('type', '').strip():
            info['type'] = '新增功能'  # 默认视为新增功能
            info['auto_detected']['type'] = False
        
        return True
    
    def get_next_question(self, info: Dict) -> Optional[str]:
        """获取下一个需要追问的问题（智能确认已识别信息）"""
        requirement = info.get('requirement', '').strip()
        module = info.get('module', '').strip()
        req_type = info.get('type', '').strip()
        auto_detected = info.get('auto_detected', {})
        
        # 如果需求描述为空
        if not requirement:
            return '请描述一下具体的需求内容~'
        
        # 如果模块为空
        if not module:
            # 提供模块选择建议
            module_list = ', '.join(self.module_keywords.keys())
            return f'请问这个需求属于哪个业务模块呢？（如：{module_list}）'
        
        # 如果需求类型为空
        if not req_type:
            return f'这个需求是新增功能、调整优化还是Bug修复呢？'
        
        # 信息完整，返回None表示可以直接评估
        return None
    
    def build_prompt(self, conversation_history: List[Dict]) -> str:
        """构建完整的对话提示词"""
        messages = []
        
        # 系统提示
        messages.append({"role": "system", "content": self.system_prompt})
        
        # 对话历史
        for msg in conversation_history:
            role = "user" if msg['role'] == 'user' else "assistant"
            messages.append({"role": role, "content": msg['content']})
        
        return messages
    
    def parse_assessment_ready(self, response: str) -> Optional[Dict]:
        """解析评估准备就绪的响应"""
        pattern = r'<ASSESSMENT_READY>\s*({.*?})\s*</ASSESSMENT_READY>'
        match = re.search(pattern, response, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                return None
        return None
    
    def analyze_and_extract(self, requirement_text: str) -> Dict:
        """
        智能分析需求文本，自动提取所有信息
        :param requirement_text: 用户输入的需求文本
        :return: 包含需求描述、模块、类型的字典
        """
        info = {
            'requirement': requirement_text.strip(),
            'module': '',
            'type': '',
            'auto_detected': {
                'module': False,
                'type': False
            },
            'confidence': 0.0
        }
        
        if not info['requirement']:
            return info
        
        # 第一步：规则匹配识别
        module_from_rule = self._extract_module_by_keyword(requirement_text)
        type_from_rule = self._extract_type_by_keyword(requirement_text)
        
        if module_from_rule:
            info['module'] = module_from_rule
            info['auto_detected']['module'] = True
        
        if type_from_rule:
            info['type'] = type_from_rule
            info['auto_detected']['type'] = True
        
        # 第二步：知识库分析作为补充
        if not info['module'] or not info['type']:
            kb_result = self._analyze_from_knowledge_base(requirement_text)
            
            if kb_result['confidence'] >= 0.5:
                if kb_result['module'] and not info['module']:
                    info['module'] = kb_result['module']
                    info['auto_detected']['module'] = True
                if kb_result['type'] and not info['type']:
                    info['type'] = kb_result['type']
                    info['auto_detected']['type'] = True
            
            info['confidence'] = kb_result['confidence']
        else:
            # 如果规则匹配成功，置信度设为较高值
            info['confidence'] = 0.8
        
        return info

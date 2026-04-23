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
    
    def analyze_intent(self, user_input: str, has_history: bool = False, has_evaluation: bool = False) -> str:
        """
        分析用户意图，输出固定JSON格式
        :param user_input: 用户输入
        :param has_history: 是否有历史对话
        :param has_evaluation: 是否有评估结果
        :return: JSON字符串 {"intent":"", "reason":""}
        """
        import json
        
        user_input = user_input.lower().strip()
        
        # 1. 识别 chat 意图（闲聊、问候、提问Agent本身、无关业务沟通、规则咨询、日常对话）
        chat_keywords = [
            # 问候类
            '你好', 'hello', 'hi', '您好', '早上好', '晚上好', '下午好', '嗨',
            '你好啊', '哈喽', '嘿', '嗨喽',
            # 感谢告别类
            '谢谢', '谢谢了', '感谢', '拜拜', '再见', '再见了', '回见',
            # 关于Agent本身
            '你是谁', '你叫什么', '你能做什么', '你的功能', '介绍一下',
            '规则', '说明', '帮助', '使用方法', '怎么用', '什么是',
            # 无关业务
            '天气', '吃饭', '今天', '周末', '放假',
        ]
        
        if any(keyword in user_input for keyword in chat_keywords):
            return json.dumps({
                "intent": "chat",
                "reason": "识别到闲聊、问候、规则咨询或无关业务内容"
            })
        
        # 2. 识别 revise_task 意图（纠错、补充信息、指出拆解错误、追加背景、修正需求边界、调整原有系统信息）
        revise_keywords = [
            # 纠错类
            '不对', '错了', '错误', '有问题', '不准确', '不合理',
            # 补充类
            '补充', '追加', '还有', '另外', '加上', '新增', '添加',
            # 调整类
            '调整', '修改', '更改', '修正', '变更', '重算', '重新',
            # 质疑类
            '质疑', '反驳', '不同意', '不是这样',
            # 背景追加
            '背景', '原有', '之前', '原来', '历史',
        ]
        
        # 如果有历史对话或评估结果，且消息匹配修订关键词，则判定为 revise_task
        if (has_history or has_evaluation) and any(keyword in user_input for keyword in revise_keywords):
            return json.dumps({
                "intent": "revise_task",
                "reason": "存在历史对话/评估结果，且识别到纠错、补充或调整相关内容"
            })
        
        # 3. 默认识别为 new_task（全新需求拆解任务）
        return json.dumps({
            "intent": "new_task",
            "reason": "识别到需求拆解或工时评估相关内容，或无历史对话时的首次输入"
        })
    
    def _init_knowledge_manager(self):
        """延迟初始化知识库管理器"""
        if self.knowledge_manager is None:
            from agent.knowledge_manager import KnowledgeManager
            self.knowledge_manager = KnowledgeManager()
    
    def _analyze_from_knowledge_base(self, requirement_text: str) -> Dict:
        """通过知识库智能分析需求，识别模块和需求类型（强制读取业务知识库和代码知识库）"""
        self._init_knowledge_manager()
        
        result = {
            'module': '',
            'type': '',
            'confidence': 0.0,
            'related_features': [],
            'related_modules': []
        }
        
        try:
            # 调用知识库进行分析（强制读取业务知识库和代码知识库）
            requirement = {
                "feature": requirement_text,
                "detail": requirement_text,
                "module": ""
            }
            analysis = self.knowledge_manager.analyze_requirement(requirement)
            
            # 从分析结果中提取模块信息
            if analysis.get('related_modules'):
                result['module'] = analysis['related_modules'][0]
                result['related_modules'] = analysis['related_modules']
            
            # 根据知识库判断需求类型（新增/调整）
            if analysis.get('judgment'):
                if analysis['judgment'] == '新增':
                    result['type'] = '新增功能'
                else:
                    result['type'] = '调整优化'
            
            # 返回关联的现有功能（用于调整需求的拆解参考）
            if analysis.get('existing_features'):
                result['related_features'] = analysis['existing_features']
            
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
        """从对话历史中提取需求信息（强制结合知识库智能分析）"""
        info = {
            'requirement': '',
            'module': '',
            'type': '',
            'type_confirmed': False,
            'auto_detected': {
                'module': False,
                'type': False
            },
            'kb_analysis': None,
            'related_features': [],
        }

        # 收集所有用户消息
        user_messages = []
        for msg in conversation_history:
            if msg['role'] == 'user':
                user_messages.append(msg['content'])

        if not user_messages:
            return info

        # 获取最后一条用户消息（用于判断确认/纠正意图）
        last_user_msg = user_messages[-1]
        prev_messages = user_messages[:-1]

        # ============== 确定原始需求文本 ==============
        # 第一条有意义的消息作为原始需求，后续消息视为补充/纠正
        original_requirement = ''
        for msg in prev_messages:
            if self._is_requirement_description(msg):
                original_requirement = msg
                break

        # ============== 判断确认/纠正意图 ==============
        confirm_keywords = ['对', '是的', '是', '正确', '确认', '没错', '好的', '可以', 'ok', '嗯', '对，']
        deny_keywords = ['不对', '不是的', '错了', '错误', '不正确', '重新', '不是新增', '不是原有']

        is_confirm = any(keyword in last_user_msg for keyword in confirm_keywords)
        is_deny = any(keyword in last_user_msg for keyword in deny_keywords)

        # 如果用户在确认阶段主动提供了类型/模块信息，视为确认+纠正
        if not is_confirm and not is_deny and len(prev_messages) > 0:
            # 检查是否之前处于确认阶段（AI最后一条消息是确认请求）
            ai_msgs = [msg for msg in conversation_history if msg['role'] == 'assistant']
            if ai_msgs and ('请问以上识别是否正确' in ai_msgs[-1]['content'] or '识别是否正确' in ai_msgs[-1]['content']):
                type_from_msg = self._extract_type_by_keyword(last_user_msg)
                module_from_msg = self._extract_module_by_keyword(last_user_msg)
                if type_from_msg or module_from_msg:
                    is_confirm = True  # 视为已确认
                    info['type_confirmed'] = True

        # 如果是明确确认，设置确认状态
        if is_confirm and not is_deny:
            info['type_confirmed'] = True

        # ============== 确定最终需求文本 ==============
        # 如果是确认阶段的用户回复，使用原始需求 + 用户当前输入的信息
        if info['type_confirmed'] and original_requirement:
            # 用户可能在确认时补充了信息，需要提取类型/模块并合并
            requirement_text = original_requirement
            # 追加用户的纠正信息
            if last_user_msg != original_requirement:
                correction = last_user_msg.strip()
                # 过滤掉纯确认词
                pure_confirm = all(kw in correction for kw in ['是']) and len(correction) <= 20
                if not pure_confirm or self._extract_type_by_keyword(correction) or self._extract_module_by_keyword(correction):
                    requirement_text = f"{original_requirement} {correction}"
        else:
            # 新需求：使用最后一条有意义的需求描述
            requirement_text = last_user_msg if self._is_requirement_description(last_user_msg) else original_requirement

        # 检查是否是需求描述
        if not requirement_text or not self._is_requirement_description(requirement_text):
            return info

        info['requirement'] = requirement_text.strip()

        # ============== 提取类型/模块（从用户最新输入优先） ==============
        # 如果是确认阶段的纠正回复，优先从最后一条消息提取
        if info['type_confirmed'] and len(prev_messages) > 0:
            type_from_last = self._extract_type_by_keyword(last_user_msg)
            module_from_last = self._extract_module_by_keyword(last_user_msg)
            if type_from_last:
                info['type'] = type_from_last
                info['auto_detected']['type'] = True
            if module_from_last:
                info['module'] = module_from_last
                info['auto_detected']['module'] = True

        # ============== 强制：读取知识库并分析 ==============
        kb_analysis = self._analyze_from_knowledge_base(requirement_text)
        info['kb_analysis'] = kb_analysis

        # 使用知识库分析结果补充（不覆盖用户已确认的信息）
        if kb_analysis['confidence'] >= 0.5:
            if kb_analysis['module'] and not info['module']:
                info['module'] = kb_analysis['module']
                info['auto_detected']['module'] = True
            if kb_analysis['type'] and not info['type']:
                info['type'] = kb_analysis['type']
                info['auto_detected']['type'] = True
            if kb_analysis.get('related_features'):
                info['related_features'] = kb_analysis['related_features']

        # ============== 规则匹配（作为补充）==============
        if not info['module']:
            module_from_rule = self._extract_module_by_keyword(requirement_text)
            if module_from_rule:
                info['module'] = module_from_rule
                info['auto_detected']['module'] = True

        if not info['type']:
            type_from_rule = self._extract_type_by_keyword(requirement_text)
            if type_from_rule:
                info['type'] = type_from_rule
                info['auto_detected']['type'] = True

        # ============== 兜底 ==============
        if not info['module']:
            info['module'] = '未指定模块'
            info['auto_detected']['module'] = False
        if not info['type']:
            info['type'] = '新增功能'
            info['auto_detected']['type'] = False

        # 如果用户否认，清空信息
        if is_deny:
            info['module'] = ''
            info['type'] = ''
            info['type_confirmed'] = False
            info['kb_analysis'] = None
            info['related_features'] = []

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
    
    def generate_intelligent_question(self, info: Dict) -> str:
        """
        基于AI理解生成智能追问问题，而不是使用预设问题
        :param info: 已收集的需求信息
        :return: 智能生成的追问问题
        """
        requirement = info.get('requirement', '').strip()
        module = info.get('module', '').strip()
        req_type = info.get('type', '').strip()
        
        # 如果需求描述较短，请求更多细节
        if len(requirement) < 10:
            return f"您的需求描述比较简洁，能再详细描述一下吗？比如具体要实现什么功能、涉及哪些业务场景~"
        
        # 如果模块未识别，基于需求内容智能提问
        if not module:
            # 分析需求中提到的关键词，生成针对性问题
            keywords = ['订单', '用户', '商品', '支付', '报表', '权限', '消息', '通知']
            found_keywords = [k for k in keywords if k in requirement]
            
            if found_keywords:
                return f"根据您的描述，我注意到涉及{'、'.join(found_keywords)}等内容。请问这个需求主要属于哪个业务模块呢？（如：订单管理、用户管理、商品管理等）"
            else:
                return f"为了更好地拆解您的需求，我想了解一下：这个需求主要涉及哪个业务模块呢？例如订单管理、用户管理、商品管理等~"
        
        # 如果类型未识别，基于需求内容智能提问
        if not req_type:
            # 分析关键词判断可能的类型
            has_new_keywords = any(k in requirement for k in ['新增', '开发', '实现', '创建', '搭建'])
            has_modify_keywords = any(k in requirement for k in ['修改', '优化', '调整', '改进', '升级'])
            has_fix_keywords = any(k in requirement for k in ['修复', 'bug', '问题', '错误', '解决'])
            
            if has_new_keywords and not has_modify_keywords and not has_fix_keywords:
                return f"根据您描述的「{requirement[:50]}...」，看起来像是一个新增功能需求，对吗？如果不是，请告诉我具体是调整优化还是Bug修复~"
            elif has_modify_keywords:
                return f"根据您描述的「{requirement[:50]}...」，看起来像是一个调整优化需求，对吗？如果不是，请告诉我具体的需求类型~"
            elif has_fix_keywords:
                return f"根据您描述的「{requirement[:50]}...」，看起来像是一个Bug修复需求，对吗？如果不是，请告诉我具体的需求类型~"
            else:
                # 如果无法判断，使用通用但智能的提问
                return f"为了更准确地评估工时，我想确认一下：您描述的「{requirement[:50]}...」是新增功能、调整优化还是Bug修复呢？"
        
        # 默认追问
        return f"为了更好地帮您拆解需求，您能再补充一些信息吗？比如具体的业务场景或功能细节~"
    
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

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
    
    def extract_requirement_info(self, conversation_history: List[Dict]) -> Dict[str, str]:
        """从对话历史中提取需求信息（结合知识库智能分析）"""
        info = {
            'requirement': '',
            'module': '',
            'type': ''
        }
        
        for msg in conversation_history:
            if msg['role'] != 'user':
                continue
            
            content = msg['content']
            
            # 累积需求描述
            if content:
                if info['requirement']:
                    info['requirement'] += ' ' + content
                else:
                    info['requirement'] = content
        
        requirement_text = info['requirement']
        
        # 首先使用规则匹配提取模块和类型（优先级更高）
        # 尝试提取模块信息
        module_patterns = [
            r'(用户管理|订单管理|报表系统|权限管理|配置管理|数据分析|系统设置)',
            r'(模块|系统|功能)[:：]\s*(\w+)'
        ]
        for pattern in module_patterns:
            match = re.search(pattern, requirement_text)
            if match and not info['module']:
                info['module'] = match.group(1)
        
        # 尝试提取需求类型（规则匹配优先）
        if 'bug' in requirement_text.lower() or '修复' in requirement_text:
            info['type'] = 'Bug修复'
        elif '新增' in requirement_text:
            info['type'] = '新增功能'
        elif any(word in requirement_text for word in ['调整', '优化', '修改', '改进']):
            info['type'] = '调整优化'
        
        # 如果规则匹配未能识别，则通过知识库智能分析
        if info['requirement'] and (not info['module'] or not info['type']):
            kb_result = self._analyze_from_knowledge_base(info['requirement'])
            
            # 如果知识库分析有较高置信度，使用分析结果
            if kb_result['confidence'] >= 0.6:
                if kb_result['module'] and not info['module']:
                    info['module'] = kb_result['module']
                if kb_result['type'] and not info['type']:
                    info['type'] = kb_result['type']
        
        return info
    
    def check_info_complete(self, info: Dict) -> bool:
        """检查信息是否完整"""
        return all([
            info.get('requirement', '').strip(),
            info.get('module', '').strip(),
            info.get('type', '').strip()
        ])
    
    def get_next_question(self, info: Dict) -> Optional[str]:
        """获取下一个需要追问的问题（智能确认已识别信息）"""
        requirement = info.get('requirement', '').strip()
        module = info.get('module', '').strip()
        req_type = info.get('type', '').strip()
        
        # 如果需求描述为空
        if not requirement:
            return '好的，请描述一下具体的需求内容~'
        
        # 如果模块为空
        if not module:
            # 如果已有部分信息，先确认已识别的内容
            if req_type:
                return f'已识别需求类型为「{req_type}」。请问这个需求属于哪个业务模块呢？（比如：用户管理、订单管理、报表系统等）'
            return '请问这个需求属于哪个业务模块呢？（比如：用户管理、订单管理、报表系统等）'
        
        # 如果需求类型为空
        if not req_type:
            # 确认已识别的模块，并询问类型
            return f'已识别需求属于「{module}」模块。这是新增功能、调整优化还是Bug修复呢？'
        
        # 信息完整，返回None
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
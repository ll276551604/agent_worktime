# 代码知识库使用说明

将项目的代码结构、接口文档、数据模型等技术背景信息放到这个目录，
AI 在拆解需求时会自动检索并注入相关内容，从而产出更贴近现有实现的评估结果。

## 推荐的文件类型

- `*.md` — 接口文档、数据模型说明、技术规范
- `*.txt` — 模块说明、架构概览
- `*.json` — 数据库表结构、API schema

## 文件命名建议

以模块名或功能域命名，方便关键词匹配：
- `order_module.md` — 订单模块接口说明
- `user_auth.md` — 用户认证接口说明
- `db_schema.json` — 数据库表结构

## 示例文件格式（接口文档）

```markdown
# 订单模块接口

## 已有接口
- GET /api/orders — 订单列表（支持分页、状态筛选）
- POST /api/orders — 创建订单
- GET /api/orders/:id — 订单详情
- PATCH /api/orders/:id/status — 更新订单状态

## 数据模型
Order: { id, orderNo, supplierId, items[], status, totalAmount, createdAt }
OrderItem: { orderId, skuId, qty, price, subtotal }
```

## 注意事项

- 每个文件建议不超过 1000 行，超出部分会被截断
- 内容越具体（有接口路径、字段名），AI 注入效果越好
- 修改后立即生效，无需重启服务

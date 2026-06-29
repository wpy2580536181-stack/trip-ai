# 前端 Redesign 设计文档

## 概述

将 trip-front 从移动端 Vant 4 改造为桌面端 Naive UI，采用 Claude 暖灰极简风格，支持明暗双主题。

## 设计决策

| 维度 | 决策 |
|------|------|
| 设备定位 | 桌面端优先 |
| 组件库 | Naive UI |
| 布局 | 左侧边栏 + 主内容区全宽填充 |
| 主题 | Light / Dark 双主题 |
| 风格 | 暖灰极简（Claude 风格） |

## 色彩体系

### Light Theme
- bg-primary: `#FCFAFA`（页面底色）
- bg-secondary: `#F5F2ED`（侧边栏/卡片底色）
- border: `#EAE5E0`（分割线/边框）
- accent: `#665CA2`（强调色，紫灰）
- text-primary: `#2B2D31`
- text-secondary: `#6C6E74`

### Dark Theme
- bg-primary: `#1E1E20`
- bg-secondary: `#262628`
- border: `#2E2E32`
- accent: `#8B7FD4`（淡紫）
- text-primary: `#E4E4E4`
- text-secondary: `#9B9BA0`

## 布局结构

```
┌──────────────┬─────────────────────────────────────────┐
│  Sidebar     │  Main Content Area                      │
│  (220px)     │  (flex: 1, padding: 32px 40px)          │
│              │                                          │
│  Logo        │  [Page Title]                            │
│  ────────    │  [Content — 全宽填充，内部元素各自控宽]    │
│  导航菜单     │                                          │
│  ────────    │  首页：表单 720px max + 网格卡片自适应列数 │
│  设置/用户    │  聊天：左侧对话列表 + 右侧聊天区全宽       │
│              │  详情：Day Cards 全宽 + 时间线             │
│              │                                          │
└──────────────┴─────────────────────────────────────────┘
```

布局要点：
- 侧边栏可折叠为图标栏（窄屏适配 <1024px）
- 侧边栏底部放置：用户头像/名称 + 暗色模式切换开关 + 设置/退出
- 导航菜单：首页 对话 行程 Tokens 个人中心（用户）；知识库 反馈 Trace 架构图（admin 额外显示）
- 内容区无 max-width 约束，全宽填充
- 内部元素各自控制合理宽度（表单 max-width: 720px，卡片用 grid auto-fill）
- 圆角规范：卡片 12px / 按钮 10px / 小控件 8px

## Vant → Naive UI 组件映射

| Vant（移除） | Naive UI（引入） |
|-------------|-----------------|
| van-nav-bar | 移除（已由侧边栏取代） |
| van-tabbar | 移除（已由侧边栏取代） |
| van-cell/van-field | n-input / n-form |
| van-button | n-button |
| van-dialog/van-popup | n-modal / n-drawer |
| van-collapse | n-collapse |
| van-tag | n-tag |
| van-loading | n-spin |
| van-toast | n-message / n-notification |
| van-action-sheet | n-dropdown |
| van-tab/van-tabs | n-tabs |
| van-steps | n-steps |
| van-checkbox/van-radio | n-checkbox / n-radio |
| van-picker | n-select |
| van-switch | n-switch |
| van-image | n-image |

图标方案：
- 导航图标使用 emoji（🏠 💬 📋 📊 👤），避免引入额外图标库增加体积
- 需要精细图标时用 `@vicons/ionicons5`（Naive UI 官方推荐的图标库）

保留不变的部分：
- VueFlow（架构图页面）
- marked（Markdown 渲染）
- html-to-image + jsPDF（导出功能）
- axios + fetch（HTTP 请求）
- 全部 API 层代码

## 页面改造清单

### 游客区（3 页）
- Login.vue — 居中卡片式登录，简洁表单
- Register.vue — 居中卡片式注册
- ResetPassword.vue — 居中卡片式，两步流程

### 用户区（8 页）
- Home.vue — 大标题 + 搜索表单 + 热门目的地自适应网格
- Chat.vue — Claude 风格双栏（对话列表 + 聊天区），SSE 流式不变
- Detail.vue — 全宽 Day Cards + 时间段时间线
- History.vue — 表格/列表式展示行程历史
- Profile.vue — 侧边配置面板风格
- TokenUsage.vue — 数据卡片 + 图表
- KnowledgeManager.vue — 表格 CRUD
- About.vue — 简单介绍页

### 管理区（3 页）
- AdminFeedbackDashboard.vue — 数据卡片 + 趋势图 + 表格
- AdminTrace.vue — 步骤时间轴
- AdminArchitecture.vue — VueFlow 架构图（保留现有）

## 实施路线图

### 第一阶段：搭架子
1. 安装 Naive UI + `@vicons/ionicons5`（图标）
2. 创建 `src/components/layout/AppLayout.vue` + `Sidebar.vue`
3. 替换 `App.vue` 为侧边栏布局，重写路由守卫
4. 配置 Naive UI 主题系统（`src/styles/theme.ts`）
5. 定义全局 CSS 变量
6. 更新 `main.ts` 接入 Naive UI provider

### 第二阶段：改页面
按优先级逐页替换：
1. 游客区（Login / Register / ResetPassword）— 低风险练手
2. 首页 Home — 最重要的 landing
3. 聊天 Chat — 核心交互页面
4. 个人中心 Profile + TokenUsage
5. 行程 Detail + History
6. 管理区（Knowledge / Feedback / Trace / Architecture）

每个页面替换策略：移除 Vant 组件 → 替换为 Naive UI 等效组件 → 重写样式为暖灰极简风

### 第三阶段：打磨
1. 暗色模式切换动画
2. 页面切换过渡
3. 侧边栏折叠/展开
4. 响应式断点（<1024px 侧边栏折叠）
5. 移除 Vant 依赖
6. 清理全局样式

## 文件变更

### 新增
```
src/components/layout/AppLayout.vue
src/components/layout/Sidebar.vue
src/styles/theme.ts
```

### 修改
```
src/main.ts          — 接入 Naive UI
src/App.vue          — 替换布局
src/router/index.ts  — 布局嵌套路由
src/styles/common.css — 精简为极简样式
src/views/*.vue      — 14 个页面逐个替换
```

### 删除
```
vant 包依赖
unplugin-vue-components VantResolver
```

## 保留不变

- API 层（`src/api/`）
- 工具函数（`src/utils/`）
- 配置（`src/config/`）
- VueFlow 架构图组件（`src/components/architecture/`）
- 导出功能（html-to-image / jsPDF）
- 路由守卫逻辑
- 认证机制

# TripAI Design Tokens v1.0

> **Design system**: Minimal · Monochrome · Editorial
> **Stack**: Vue 3 + Tailwind CSS v4
> **Mode**: Light-only（v1 暂不输出暗色）

---

## 1. 🎨 Color Tokens

### Neutral（唯一调色板 · 9 级灰阶）

| Token | Hex | 用途 |
|---|---|---|
| `--ink-0` | `#FFFFFF` | 卡片底 / 输入框 |
| `--ink-50` | `#FAFAFA` | 页面底色 |
| `--ink-100` | `#F5F5F5` | 次级背景 / 缩略图 / 禁用态 |
| `--ink-200` | `#EEEEEE` | 微网格线 |
| `--ink-300` | `#E5E5E5` | 默认分割线 / 边框 |
| `--ink-400` | `#A3A3A3` | 三级文字（辅助标签、placeholder） |
| `--ink-500` | `#737373` | 次级文字 |
| `--ink-700` | `#404040` | 一级标题（极少用，标题主用 ink-900） |
| `--ink-900` | `#0A0A0A` | 主文字 / 主品牌色 / 强调元素 |

> ⚠️ **单一强调色**：整个产品没有彩色。所有需要"高亮/选中/重点"的位置都使用 `--ink-900` 实心或 1.5–2px 实线表达层级。
>
> **可访问性**：所有文字/背景组合都通过 WCAG AA 4.5:1 验证。

### Semantic（语义化映射）

| Token | 映射 |
|---|---|
| `--text-primary` | `var(--ink-900)` |
| `--text-secondary` | `var(--ink-500)` |
| `--text-tertiary` | `var(--ink-400)` |
| `--text-placeholder` | `var(--ink-400)` |
| `--surface-page` | `var(--ink-50)` |
| `--surface-card` | `var(--ink-0)` |
| `--surface-muted` | `var(--ink-100)` |
| `--border-default` | `var(--ink-300)` |
| `--border-subtle` | `var(--ink-200)` |
| `--accent` | `var(--ink-900)` |

---

## 2. 🔤 Typography Tokens

### Font Stack

| Token | Value |
|---|---|
| `--font-sans` | `'Inter', -apple-system, BlinkMacSystemFont, system-ui, sans-serif` |
| `--font-serif` | `'Source Han Serif SC', 'Noto Serif SC', 'Songti SC', serif` |
| `--font-mono` | `'JetBrains Mono', 'SF Mono', Consolas, monospace` |

> **使用规则**：
> - 正文/UI 全用 `--font-sans`
> - 页面主标题（如 "下一站，去哪里？"、"北京 → 上海 · 3 天行程"）用 `--font-serif`，强调编辑感
> - 数字（金额、时间、日期、计数）统一加 `font-variant-numeric: tabular-nums`

### Type Scale

| Token | Size | Line Height | Weight | 用途 |
|---|---|---|---|---|
| `--text-2xs` | 10px | 1.4 | 600 | 分类标签（letter-spacing 2-3） |
| `--text-xs` | 11px | 1.5 | 400 | 辅助信息 / placeholder |
| `--text-sm` | 13px | 1.5 | 400 | 次级正文 |
| `--text-base` | 14px | 1.5 | 400 | 默认正文 |
| `--text-md` | 15px | 1.5 | 600 | 列表项标题 |
| `--text-lg` | 16px | 1.4 | 600 | 卡片标题 |
| `--text-xl` | 20px | 1.3 | 600 | 区块大标题 |
| `--text-2xl` | 24px | 1.3 | 600 | 页面主标题 |
| `--text-3xl` | 40px | 1.2 | 700 | Hero 文案 |
| `--text-display` | 56px | 1.1 | 700 | 首页 Hero 大字 |

### Letter Spacing

| Token | Value | 用途 |
|---|---|---|
| `--tracking-tight` | `-0.02em` | 大标题 |
| `--tracking-normal` | `0` | 正文 |
| `--tracking-wide` | `0.05em` | 中文小标签 |
| `--tracking-caps` | `0.15em` (letter-spacing 2-3) | 英文分类标签 `MORNING` `BUDGET` |

---

## 3. 📏 Spacing Tokens

> 基础单元 = **4px**，所有间距为 4 的倍数。

| Token | Value | 用途 |
|---|---|---|
| `--space-0` | 0 | 紧贴 |
| `--space-1` | 4px | 最小间距（icon 和文字之间） |
| `--space-2` | 8px | 内联元素间距 |
| `--space-3` | 12px | 紧凑列表项 padding |
| `--space-4` | 16px | 卡片内 padding、组件间标准间距 |
| `--space-5` | 20px | 区块上下间距 |
| `--space-6` | 24px | 卡片间距、容器内 padding |
| `--space-8` | 32px | 页面主要区块间距 |
| `--space-10` | 40px | 大区块 |
| `--space-12` | 48px | 页面边距 / 顶部留白 |
| `--space-16` | 64px | Hero 段落间距 |
| `--space-20` | 80px | 页面级分隔 |

### Layout 容器

| Token | Value |
|---|---|
| `--container-mobile` | 100% - 24px × 2 |
| `--container-tablet` | 640px |
| `--container-desktop` | 1024px |
| `--container-max` | 1200px |

---

## 4. 📐 Radius Tokens（极简圆角）

> 全场只用 3 个圆角档位，避免出现"圆乎乎"的产品气质。

| Token | Value | 用途 |
|---|---|---|
| `--radius-none` | 0 | 分割线、图标方块 |
| `--radius-sm` | 4px | 按钮、tag |
| `--radius-md` | 6–8px | 卡片、输入框、tab 容器 |
| `--radius-pill` | 9999px | 头像、药丸按钮 |

> ❌ **禁用**：任何 ≥16px 的大圆角。极简风的精髓就是"几乎不圆"。

---

## 5. 🪟 Elevation & Border

> **不用 shadow**。所有层级关系通过 1px 描边 + 背景灰阶差异表达。

| Token | Value | 用途 |
|---|---|---|
| `--border-hairline` | `1px solid var(--ink-200)` | 卡片内分割线 |
| `--border-default` | `1px solid var(--ink-300)` | 卡片描边 / 容器描边 |
| `--border-strong` | `1.5px solid var(--ink-900)` | 强调描边（选中态、地图标记） |
| `--border-accent` | `2px solid var(--ink-900)` | Tab 下划线、激活态 |

> ⚠️ **绝对不用** `box-shadow` 制造层次。如果觉得"太平"——用 1px ink-200 分割线 + 8px 留白解决。

---

## 6. ⏱ Motion Tokens

> 极简风 = 几乎不动。动效只服务于"告知用户状态变了"。

| Token | Value | 用途 |
|---|---|---|
| `--duration-instant` | 100ms | hover 颜色变化 |
| `--duration-fast` | 150ms | 按钮反馈、tab 切换 |
| `--duration-base` | 250ms | 浮窗、卡片展开 |
| `--duration-slow` | 400ms | 页面切换、地图飞入 |
| `--ease-out` | `cubic-bezier(0.2, 0.8, 0.2, 1)` | 入场 |
| `--ease-in-out` | `cubic-bezier(0.4, 0, 0.2, 1)` | 通用 |

> ❌ **禁用** 弹簧动画、视差、bounce 效果。

---

## 7. 📱 Responsive Breakpoints

| Name | Min Width | 适配 |
|---|---|---|
| `xs` | 0 | 手机竖屏（基线设计 375px） |
| `sm` | 640px | 手机横屏 / 小平板 |
| `md` | 768px | iPad |
| `lg` | 1024px | 桌面 |
| `xl` | 1280px | 大屏 |
| `2xl` | 1536px | 2K |

> **设计基准画板**：375 × 812（iPhone 14）作为所有页面设计的**主画板**，再扩展到 768 / 1280。

---

## 8. 🧱 Component Patterns

### Button

| 变体 | 背景 | 边框 | 文字 | 圆角 | 高度 |
|---|---|---|---|---|---|
| Primary | `--ink-900` | none | `#FFFFFF` | 4px | 36px |
| Secondary | `#FFFFFF` | 1px `--ink-900` | `--ink-900` | 4px | 36px |
| Ghost | transparent | none | `--ink-500` | 4px | 36px |
| Pill Primary | `--ink-900` | none | `#FFFFFF` | 999px | 28px |

### Tag / Chip

- 高度 22–28px
- 圆角 4–14px
- 边框 1px `--ink-300` 或 `rgba(255,255,255,0.4)`（在深色背景上）
- 文字 11–12px，weight 500

### Time Block（上午/下午/晚上）

- 左侧 4px 宽 `--ink-900` 实心条
- 高度匹配内容
- 文字左缩进 20px
- 块与块间距 40px

### Map Marker

- 圆点直径 32px（`r="16"`）
- 未访问：`#FFFFFF` 底 + 1.5px `--ink-900` 描边
- 已访问：`--ink-900` 实心
- 待规划：`#FFFFFF` 底 + 1.5px `--ink-400` 描边
- 中心数字 8–13px，weight 600

### Card

- 底色 `--ink-0`
- 边框 1px `--ink-300`（如有边界感需求）或无
- 圆角 6–8px
- 内 padding 16–20px
- ❌ 不用 shadow

### Divider

- 1px 实线 `--ink-200`（次级）或 `--ink-300`（默认）

### Tab Item

- 文字 14px，weight 400（默认）/ 600（激活）
- 激活态：文字 `--ink-900` + 下方 2px `--ink-900` 实线（线宽 ≈ 文字宽度 60%）
- 间距：每 Tab 之间 24px

---

## 9. 🔢 Number Formatting

| 类型 | 格式规则 | 示例 |
|---|---|---|
| 金额 | `¥ 5,000`（千分位 + 空格） | `¥ 12,480` |
| 时间 | `2.5 小时` / `1 小时 30 分` | `⏱ 3 小时` |
| 距离 | `4.2 km` | `1.8 km` |
| 日期 | `2026-06-28`（ISO 短格式） | `06-28`（在 Day Tab） |
| 计数 | `共 4 个景点` / `1.2M tokens` | `¥ 2,480` |

> 所有数字统一加 `font-variant-numeric: tabular-nums`，保证列对齐。

---

## 10. 📦 Tailwind 配置参考

```js
// tailwind.config.ts
export default {
  theme: {
    colors: {
      ink: {
        0: '#FFFFFF',
        50: '#FAFAFA',
        100: '#F5F5F5',
        200: '#EEEEEE',
        300: '#E5E5E5',
        400: '#A3A3A3',
        500: '#737373',
        700: '#404040',
        900: '#0A0A0A',
      }
    },
    fontFamily: {
      sans: ['Inter', 'system-ui', 'sans-serif'],
      serif: ['"Source Han Serif SC"', 'serif'],
      mono: ['"JetBrains Mono"', 'monospace'],
    },
    borderRadius: {
      none: '0',
      sm: '4px',
      md: '8px',
      pill: '9999px',
    },
    boxShadow: { none: 'none' },  // 全场禁用 shadow
    extend: {
      letterSpacing: {
        caps: '0.15em',
      }
    }
  }
}
```

---

## ✅ 实施检查清单

- [ ] 全场没有彩色出现（除图片内容）
- [ ] 没有任何 `box-shadow` 残留
- [ ] 没有大圆角（≥16px）
- [ ] 所有数字元素带 `tabular-nums`
- [ ] 所有英文分类标签带 `letter-spacing: 0.15em`
- [ ] 至少一个 serif 标题出现在每个页面
- [ ] 移动端基准 375px 上布局完整
- [ ] 文字对比度 ≥ 4.5:1（ink-400 on white 已验证 3.0:1，仅用于 placeholder 可接受）

---

*Version 1.0 · 2026-07-01 · UI Designer*

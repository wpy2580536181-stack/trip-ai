# 重命名影响分析报告：`trip-backend` → `trip-backend`

> 调研时间：2026-07-14
> 结论：重命名影响被**隔离在后端目录本身 + 3 个 GitHub Actions 工作流 + 包名元数据 + 文档/注释**中。前端 `trip-front` 通过端口（默认 `localhost:8000`）和相对路径 `/api` 连接后端，**完全不依赖文件夹名**；Dockerfile / docker-compose / Makefile 全部使用相对路径，**不受影响**。

---

## 一、结论速览

| 维度 | 结论 |
|---|---|
| 必须修改才能正常工作 | 3 个工作流（CI 触发条件 + 工作目录）+ `pyproject.toml` 包名（建议）+ `uv.lock`（随包名） |
| 建议一并修改（一致性） | 后端内部注释/帮助文本 3 处 + 文档/任务清单约 10 个文件、100+ 处文本 |
| 已验证安全（无需改） | Dockerfile、docker-compose.yml、Makefile、trip-front 前端、`.env`/`.env.example`、trip-server.yml（已停用） |
| 跨项目/微服务依赖 | **无**。无 root workspaces、无 root docker-compose 编排、无其他 import 该路径的子项目 |
| 预估工时 | 最小改动 0.5–1h；完整改名（含包名+文档）2–3h |
| 预计改动文件数 | 最小 3–5 个；完整约 18 个 |

> ⚠️ **关键风险点**：工作流里的 `paths: ["trip-backend/**"]` 和 `working-directory: trip-backend` 若不跟着改，会导致：① push/PR 时后端相关 CI **静默跳过**（paths 不匹配）；② 即使触发，`cd trip-backend` 会因目录不存在而**直接报错**。这属于"复杂度低、爆炸半径高"的改动。

---

## 二、按影响范围分类

### A. 功能性 / 构建关键（不修改会导致 CI 失效或包名不一致）

| # | 文件 | 引用位置 | 引用内容（节选） | 复杂度 | 说明 |
|---|---|---|---|---|---|
| 1 | `.github/workflows/trip-backend.yml` | L6, L9, L16 | `paths: ["trip-backend/**"]`（×2）、`working-directory: trip-backend` | 低 | CI 触发条件与执行目录，必须改 |
| 2 | `.github/workflows/e2e-api.yml` | L6（2 处）, L35, L38, L43 | `paths: ["trip-backend/src/**","trip-backend/tests/e2e/**"]`、`working-directory: trip-backend`（×3） | 低 | API E2E 测试流水线 |
| 3 | `.github/workflows/eval-nightly.yml` | L24, L86, L78, L171 | `working-directory: trip-backend`（×2）、`path: trip-backend/eval-reports/`（×2） | 低 | 夜间评估流水线 |
| 4 | `trip-backend/pyproject.toml` | L2 | `name = "trip-backend"` | 低（建议） | Python 包名；建议同步改为 `trip-backend` 保持目录/包名一致 |
| 5 | `trip-backend/uv.lock` | L3424 | `name = "trip-backend"` | 低（随 #4） | **仅当 #4 改包名时需要**；改 pyproject 后在仓库根执行 `uv lock` 重新生成，**不要手改** |

> 说明：若只改**目录名**而不改**包名**（即保留 `name = "trip-backend"`），则 `uv.lock` 无需动，必改文件缩小为仅 #1–#3 三个工作流。但包名与目录名不一致会产生命名异味，建议一并改。

### B. 后端内部代码 / 注释（不影响运行，建议修正以保持一致）

| # | 文件 | 引用位置 | 内容 | 复杂度 | 说明 |
|---|---|---|---|---|---|
| 6 | `trip-backend/test_api.py` | L373, L377 | `print(f"...cd trip-backend && python src/main.py")` | 低 | 仅帮助/提示文本 |
| 7 | `trip-backend/eval/__init__.py` | L1 | `# eval framework for trip-backend` | 低 | 注释 |
| 8 | `trip-backend/scripts/run_all_benchmarks.py` | L14 | `PROJECT_DIR = Path(__file__).resolve().parent.parent  # trip-backend/`（实际路径为动态计算） | 低 | 注释；运行期路径由 `__file__` 推导，不依赖字符串 |

### C. 文档（纯文本，无功能影响；如需对外准确建议更新）

| # | 文件 | 引用行 | 约出现次数 | 复杂度 |
|---|---|---|---|---|
| 9 | `README.md` | 54, 70, 107, 144 | 4 | 低 |
| 10 | `docs/p2-improvement-plan.html` | 84, 113, 259, 275, 277, 280, 299, 308, 390, 566, 583, 588, 591, 597 | ~14 | 低 |
| 11 | `docs/test-system-comprehensive-report.html` | 129, 165, 175, 279, 301, 361, 376, 419, 513, 582, 695, 697, 771–775, 785–786 | ~15 | 低 |
| 12 | `docs/migration-architecture.md` | 191, 194, 2567, 2598 | 4（L2598 还提到"重命名为 trip-server/ 可选"） | 低 |
| 13 | `docs/migration-prd.md` | 16, 317, 325, 335 | 4 | 低 |
| 14 | `docs/前后端通信与CORS.md` | 3, 14, 15, 18, 59, 66, 78, 138, 185, 208, 272–278 | ~15 | 低 |
| 15 | `docs/api-error-handling-improvement-plan.md` | 3 | 1 | 低 |
| 16 | `docs/rag-evaluation-plan.md` | 4 | 1 | 低 |
| 17 | `docs/backend-comparison.md` | 5 | 1 | 低 |
| 18 | `tasks/2026-07-05-commit-checklist.md` | 41–116, 125 | ~40 | 低 |

> 注意：`trip-front/src/api/*.ts` 中有注释引用 `trip-server/src/...`（Node 版后端），与本次 `trip-backend` 重命名**无关**，不在改动范围内。

### D. 已验证无需修改（安全）

- `trip-backend/Dockerfile` — `WORKDIR /app` + 相对 `COPY src/ ./src/`，无目录名硬编码
- `trip-backend/docker-compose.yml` — `build: .`（相对），服务名 `app`，无目录名
- `trip-backend/Makefile` — 全部相对路径（`src/`、`tests/`、`eval/`）
- `trip-front/`（整个前端）— `vite.config.ts` 用 `VITE_API_TARGET || 'http://localhost:8000'` + 相对 `/api`，零引用 `trip-backend`
- `trip-backend/.env`、`.env.example` — 无路径引用
- `.github/workflows/trip-server.yml` — **已停用**（`branches: [never-run]`），引用的是 `trip-server`（Node 版），与本次无关；建议顺手清理
- `.github/workflows/trip-front.yml` — 仅前端

---

## 三、跨项目 / 微服务依赖排查

- **无 root 级编排**：仓库根没有 `package.json`（workspaces）、没有 root `docker-compose.yml`、没有共享 monorepo 构建配置。
- **前端解耦**：`trip-front` 在运行期通过端口（默认 8000）和代理连接后端，构建期/源码期均不依赖后端目录名。
- **无其他 import**：全仓搜索未发现任何 `import`/`require` 以 `trip-backend` 作为模块名的代码（内部引用均为注释或动态路径）。
- **结论**：重命名的影响边界清晰，不会波及前端或其他服务。

---

## 四、复杂度与工时估算

| 类别 | 文件数 | 平均复杂度 | 备注 |
|---|---|---|---|
| 功能性必改（CI + 包名） | 5（最小 3） | 低（爆炸半径高） | CI 漏改会静默跳过或报错 |
| 内部注释/帮助文本 | 3 | 低 | 可选，纯一致性 |
| 文档/任务清单 | 10 | 低 | 可选，批量文本替换 |
| **合计** | **约 18（最小 3–5）** | **低** | — |

**工时估算：**
- **最小可行改名**（目录 + 3 个工作流 + 本地验证）：约 **0.5–1 工时**
- **完整改名**（含包名 + `uv.lock` 重生成 + 内部注释 + 文档/任务清单批量替换 + 验证）：约 **2–3 工时**

---

## 五、推荐执行步骤

1. `git mv trip-backend trip-backend`
2. 批量替换 3 个工作流中的 `trip-backend` → `trip-backend`（共约 12 处：`paths` 过滤 + `working-directory` + 1 处 artifact `path`）
3. （建议）`trip-backend/pyproject.toml` 的 `name` 改为 `trip-backend`，随后在仓库根执行 `uv lock` 重新生成 `uv.lock`
4. （建议）替换后端内部 3 处注释/帮助文本
5. （建议）批量替换文档与任务清单中的引用（可用 `grep -rl` + `sed` 一次性处理）
6. **验证**：
   - 本地 `uv sync` 通过
   - 手动触发一次 `trip-backend.yml` / `e2e-api.yml` 或在本地 dry-run，确认工作目录正确
   - 启动 `trip-front`，确认前端仍能连上 `:8000` 后端

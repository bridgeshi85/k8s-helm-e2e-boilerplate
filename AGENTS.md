# obs-lab (k8s-helm-e2e-boilerplate)

Observability Helm Lab — 云原生可观测性与 Helm 试验田。

---

## 仓库结构

```
k8s-helm-e2e-boilerplate/
├── charts/        ← Helm charts
├── docs/          ← 文档
├── k6_load_test/  ← k6 性能/负载测试
├── scripts/       ← 工具脚本
└── src/           ← 源码
```

## 核心约束

- commit message 遵循 conventional commits（`fix:` / `feat:` / `chore:`）
- Helm chart 变更后必须执行 `helm lint` 验证
- 修改 k6 脚本后必须可用（不强制写 UT）
- 不做 spec 范围外的假设性改动，有疑问先确认

## 分支策略

- **禁止直接提交 main 分支**
- 所有修改必须按以下流程：
  1. 从 main 创建新分支（`fix/`、`feat/`、`chore/` 开头）
  2. 完成修改并提交
  3. 推送到 GitHub 后创建 PR
  4. 告知改动内容并附 PR 链接
- **例外**：如果当前已在其他非 main 分支上工作，可以直接在该分支上提交，无需新建分支或 PR
